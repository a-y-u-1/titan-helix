"""
TITAN HELIX · Backend API
══════════════════════════════════════════════════════════════════════════════
FastAPI service that reads telemetry from Splunk and serves the interactive
console + a JSON API.

    GET  /                      → interactive console (console.html)
    GET  /demo                  → scripted cinematic demo (demo.html)
    GET  /health                → liveness + Splunk reachability
    GET  /api/graph             → service dependency graph (nodes + edges)
    GET  /api/service/{name}    → deep detail for one service (drill-down)
    GET  /api/incidents         → recent ServiceNow-shaped incidents
    GET  /api/summary           → error counts + p99 by service
    GET  /api/timeline          → error volume over time
    GET  /api/spl               → catalog of SPL queries the UI runs (provenance)
    POST /api/simulate          → inject the checkout_collapse cascade into Splunk

If Splunk is unreachable, endpoints return SAMPLE data so the frontend still
demos. Every response includes "source": "splunk" | "sample".

RUN
───
    pip install -r backend/requirements.txt
    export HELIX_SPLUNK_API_URL=https://localhost:8089
    export HELIX_SPLUNK_API_PASSWORD=ChangeMe_Helix_2026
    # for the Inject button to inject live data, also:
    export HELIX_HEC_URL=https://localhost:8088
    export HELIX_HEC_TOKEN=11111111-2222-3333-4444-555555555555
    uvicorn backend.app:app --host 0.0.0.0 --port 8080 --reload
    open http://localhost:8080
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from backend.splunk_client import SplunkClient

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(name)s] %(message)s")
log = logging.getLogger("helix.api")

app = FastAPI(title="TITAN HELIX API", version="1.1")
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])

splunk = SplunkClient.from_env()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONSOLE_HTML = PROJECT_ROOT / "console.html"
DEMO_HTML = PROJECT_ROOT / "demo.html"
STAGE_HTML = PROJECT_ROOT / "stage.html"

# service-name guard (prevents SPL injection via the drill-down path param)
SAFE_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")

# track a running simulation so we don't spawn dozens
_sim_proc: subprocess.Popen | None = None


# ════════════════════════════════════════════════════════════════════════════
# SPL templates
# ════════════════════════════════════════════════════════════════════════════

SPL_DEPS = """
index=helix_traces sourcetype="helix:traces:span"
| stats count as calls,
        avg(duration_ms) as avg_ms,
        sum(eval(if(status="ERROR",1,0))) as errors
        by parent_service, service
| where calls > 5
| eval error_rate = round(errors/calls, 4)
| rename parent_service as source, service as target
| table source, target, calls, avg_ms, error_rate
""".strip()

SPL_SERVICE_HEALTH = """
index=helix_logs sourcetype="helix:logs:app"
| stats count as total,
        sum(eval(if(level="ERROR",1,0))) as errors by service
| eval error_rate = round(errors/total, 4)
| sort - error_rate
""".strip()

SPL_INCIDENTS = """
index=helix_incidents sourcetype="helix:incidents:servicenow"
| sort - _time
| table _time, number, short_description, priority, severity, state,
        assignment_group, cmdb_ci
| head 25
""".strip()

SPL_TIMELINE = """
index=helix_logs sourcetype="helix:logs:app" level=ERROR
| timechart span=1m count by service limit=8
""".strip()

SPL_SERVICE_CPU = """
index=helix_metrics sourcetype="helix:metrics:cpu"
| stats avg(cpu_pct) as cpu, max(cpu_pct) as max_cpu by service
""".strip()

# ── per-service drill-down (use .format(service=...)) ──
SPL_SVC_LATENCY = """
index=helix_traces sourcetype="helix:traces:span" service="{service}"
| stats count as calls, avg(duration_ms) as avg_ms,
        perc50(duration_ms) as p50, perc95(duration_ms) as p95,
        perc99(duration_ms) as p99,
        sum(eval(if(status="ERROR",1,0))) as errors
| eval error_rate = round(errors/calls, 4)
""".strip()

SPL_SVC_UPSTREAM = """
index=helix_traces sourcetype="helix:traces:span" service="{service}" parent_service=*
| stats count as calls, avg(duration_ms) as avg_ms by parent_service
| sort - calls | rename parent_service as service | head 12
""".strip()

SPL_SVC_DOWNSTREAM = """
index=helix_traces sourcetype="helix:traces:span" parent_service="{service}"
| stats count as calls, avg(duration_ms) as avg_ms,
        sum(eval(if(status="ERROR",1,0))) as errors by service
| eval error_rate = round(errors/calls, 4)
| sort - calls | head 12
""".strip()

SPL_SVC_ERRORS = """
index=helix_logs sourcetype="helix:logs:app" service="{service}" level=ERROR
| sort - _time
| table _time, level, message, http_status, trace_id | head 12
""".strip()

SPL_SVC_HOSTS = """
index=helix_metrics sourcetype="helix:metrics:cpu" service="{service}"
| stats avg(cpu_pct) as avg_cpu, max(cpu_pct) as max_cpu by host
| sort - avg_cpu | head 12
""".strip()

SPL_SVC_MEM = """
index=helix_metrics sourcetype="helix:metrics:mem" service="{service}"
| stats avg(mem_pct) as avg_mem by host | sort - avg_mem | head 12
""".strip()

SPL_SVC_INCIDENTS = """
index=helix_incidents sourcetype="helix:incidents:servicenow" cmdb_ci="{service}"
| sort - _time
| table _time, number, short_description, priority, state, close_notes | head 10
""".strip()


# ════════════════════════════════════════════════════════════════════════════
# Pages
# ════════════════════════════════════════════════════════════════════════════

@app.get("/")
def root():
    if CONSOLE_HTML.exists():
        return FileResponse(str(CONSOLE_HTML))
    if DEMO_HTML.exists():
        return FileResponse(str(DEMO_HTML))
    return JSONResponse({"message": "TITAN HELIX API",
                         "note": "console.html not found"})

@app.get("/demo")
def demo():
    if DEMO_HTML.exists():
        return FileResponse(str(DEMO_HTML))
    return JSONResponse({"message": "demo.html not found"})

@app.get("/stage")
def stage():
    """Presenter shell — toggles between the live console and the scripted demo."""
    if STAGE_HTML.exists():
        return FileResponse(str(STAGE_HTML))
    return JSONResponse({"message": "stage.html not found"})


@app.get("/health")
def health():
    up = splunk.ping()
    return {"status": "ok", "splunk_reachable": up, "api_url": splunk.api_url,
            "hec_configured": bool(os.environ.get("HELIX_HEC_TOKEN"))}


# ════════════════════════════════════════════════════════════════════════════
# Graph
# ════════════════════════════════════════════════════════════════════════════

@app.get("/api/graph")
def graph(earliest: str = "-15m@m"):
    rows = splunk.search(SPL_DEPS, earliest=earliest)
    if not rows:
        return {"source": "sample", **_sample_graph()}

    health_rows = splunk.search(SPL_SERVICE_HEALTH, earliest=earliest)
    health = {r["service"]: r for r in health_rows}
    cpu_rows = splunk.search(SPL_SERVICE_CPU, earliest=earliest)
    cpu = {r["service"]: r for r in cpu_rows}

    nodes: dict[str, dict] = {}
    edges = []

    def ensure_node(name: str):
        if name not in nodes:
            h = health.get(name, {})
            err = float(h.get("error_rate", 0) or 0)
            c = cpu.get(name, {})
            cpu_avg = float(c.get("cpu", 0) or 0)
            cpu_max = float(c.get("max_cpu", 0) or 0)
            # a node is unhealthy if EITHER errors OR cpu saturation is high —
            # this is what lets the root cause (a saturating DB with no errors
            # yet) turn red before the downstream error cascade begins.
            state = ("critical" if (err > 0.2 or cpu_max > 90) else
                     "degraded" if (err > 0.03 or cpu_max > 75) else "healthy")
            nodes[name] = {
                "id": f"svc:{name}", "label": name,
                "error_rate": err, "cpu": round(cpu_avg, 1),
                "cpu_max": round(cpu_max, 1),
                "calls_total": int(float(h.get("total", 0) or 0)),
                "state": state,
            }

    for r in rows:
        s, t = r["source"], r["target"]
        ensure_node(s); ensure_node(t)
        err = float(r.get("error_rate", 0) or 0)
        edges.append({
            "id": f"e:{s}->{t}", "source": f"svc:{s}", "target": f"svc:{t}",
            "calls": int(float(r.get("calls", 0))),
            "avg_ms": round(float(r.get("avg_ms", 0) or 0), 1),
            "error_rate": err, "layer": "L1_observed",
            "confidence": round(min(0.99, 0.5 + 0.05 *
                                    (int(float(r.get("calls", 1))) ** 0.3)), 2),
        })

    return {"source": "splunk", "ts": time.time(),
            "nodes": list(nodes.values()), "edges": edges}


# ════════════════════════════════════════════════════════════════════════════
# Service drill-down
# ════════════════════════════════════════════════════════════════════════════

@app.get("/api/service/{name}")
def service_detail(name: str, earliest: str = "-15m@m"):
    if not SAFE_NAME.match(name):
        return JSONResponse({"error": "invalid service name"}, status_code=400)

    lat = splunk.search(SPL_SVC_LATENCY.format(service=name), earliest=earliest)
    if not lat:
        return {"source": "sample", **_sample_service(name)}

    up = splunk.search(SPL_SVC_UPSTREAM.format(service=name), earliest=earliest)
    down = splunk.search(SPL_SVC_DOWNSTREAM.format(service=name), earliest=earliest)
    errs = splunk.search(SPL_SVC_ERRORS.format(service=name), earliest=earliest)
    hosts = splunk.search(SPL_SVC_HOSTS.format(service=name), earliest="-30m@m")
    mem = splunk.search(SPL_SVC_MEM.format(service=name), earliest="-30m@m")
    incs = splunk.search(SPL_SVC_INCIDENTS.format(service=name), earliest="-8d@d")

    mem_by_host = {m["host"]: m.get("avg_mem") for m in mem}
    for h in hosts:
        h["avg_mem"] = mem_by_host.get(h["host"])

    m = lat[0] if lat else {}
    return {
        "source": "splunk", "service": name,
        "latency": {
            "calls": int(float(m.get("calls", 0) or 0)),
            "avg_ms": round(float(m.get("avg_ms", 0) or 0), 1),
            "p50": round(float(m.get("p50", 0) or 0), 1),
            "p95": round(float(m.get("p95", 0) or 0), 1),
            "p99": round(float(m.get("p99", 0) or 0), 1),
            "error_rate": float(m.get("error_rate", 0) or 0),
        },
        "upstream": up, "downstream": down, "errors": errs,
        "hosts": hosts, "incidents": incs,
        "spl": {
            "latency": SPL_SVC_LATENCY.format(service=name),
            "upstream": SPL_SVC_UPSTREAM.format(service=name),
            "downstream": SPL_SVC_DOWNSTREAM.format(service=name),
            "errors": SPL_SVC_ERRORS.format(service=name),
            "hosts": SPL_SVC_HOSTS.format(service=name),
            "incidents": SPL_SVC_INCIDENTS.format(service=name),
        },
    }


# ════════════════════════════════════════════════════════════════════════════
# Other reads
# ════════════════════════════════════════════════════════════════════════════

@app.get("/api/incidents")
def incidents():
    rows = splunk.search(SPL_INCIDENTS, earliest="-8d@d")
    if not rows:
        return {"source": "sample", "incidents": _sample_incidents()}
    return {"source": "splunk", "incidents": rows}


@app.get("/api/summary")
def summary(earliest: str = "-15m@m"):
    rows = splunk.search(SPL_SERVICE_HEALTH, earliest=earliest)
    if not rows:
        return {"source": "sample",
                "services": [{"service": "checkout-api", "error_rate": 0.31,
                              "total": 14200, "errors": 4402},
                             {"service": "fraud-scoring", "error_rate": 0.18,
                              "total": 9800, "errors": 1764}]}
    return {"source": "splunk", "services": rows}


@app.get("/api/timeline")
def timeline():
    rows = splunk.search(SPL_TIMELINE, earliest="-60m@m")
    if not rows:
        return {"source": "sample", "timeline": []}
    return {"source": "splunk", "timeline": rows}


@app.get("/api/spl")
def spl_catalog():
    """Provenance: the SPL the UI runs, for the right-rail panel."""
    return {
        "graph_dependencies": SPL_DEPS,
        "service_health": SPL_SERVICE_HEALTH,
        "incidents": SPL_INCIDENTS,
        "error_timeline": SPL_TIMELINE,
        "service_latency": SPL_SVC_LATENCY,
        "service_upstream": SPL_SVC_UPSTREAM,
        "service_downstream": SPL_SVC_DOWNSTREAM,
        "service_errors": SPL_SVC_ERRORS,
        "service_hosts": SPL_SVC_HOSTS,
    }


# ════════════════════════════════════════════════════════════════════════════
# Inject the cascade (real — spawns the generator against Splunk)
# ════════════════════════════════════════════════════════════════════════════

@app.post("/api/simulate")
def simulate(scenario: str = "checkout_collapse", speed: float = 10.0,
             duration: int = 120):
    """Spawn synth_generator to inject the scenario into Splunk."""
    global _sim_proc

    hec_url = os.environ.get("HELIX_HEC_URL", "https://localhost:8088")
    hec_token = os.environ.get("HELIX_HEC_TOKEN")
    if not hec_token:
        return JSONResponse({
            "status": "unavailable",
            "reason": "HELIX_HEC_TOKEN not set in the backend environment. "
                      "Export it before starting uvicorn to enable live injection.",
        }, status_code=503)

    if _sim_proc and _sim_proc.poll() is None:
        return {"status": "already_running",
                "message": "a simulation is already in progress"}

    scen_file = PROJECT_ROOT / "scenarios" / f"{scenario}.yaml"
    if not scen_file.exists():
        return JSONResponse({"status": "error",
                             "reason": f"scenario not found: {scen_file.name}"},
                            status_code=404)

    cmd = [sys.executable, str(PROJECT_ROOT / "synth_generator.py"),
           "--hec-url", hec_url, "--hec-token", hec_token,
           "--scenario", str(scen_file),
           "--speed", str(speed), "--duration", str(duration), "--quiet"]
    try:
        _sim_proc = subprocess.Popen(
            cmd, cwd=str(PROJECT_ROOT),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        return JSONResponse({"status": "error", "reason": str(e)},
                            status_code=500)

    log.info("simulate: spawned %s (pid %s)", scenario, _sim_proc.pid)
    return {"status": "started", "scenario": scenario, "speed": speed,
            "duration_s": duration, "pid": _sim_proc.pid,
            "message": "cascade injecting — keep Live polling on to watch it unfold"}


@app.get("/api/simulate/status")
def simulate_status():
    running = bool(_sim_proc and _sim_proc.poll() is None)
    return {"running": running, "pid": _sim_proc.pid if _sim_proc else None}


# ════════════════════════════════════════════════════════════════════════════
# AI investigation — runs the agent mesh over live Splunk
# ════════════════════════════════════════════════════════════════════════════

@app.get("/api/investigate/{name}")
def investigate(name: str, earliest: str = "-15m@m"):
    """Run the multi-agent reasoning chain on a service. Uses a real LLM if
    HELIX_LLM_API_KEY is set, otherwise deterministic reasoning from the data."""
    if not SAFE_NAME.match(name):
        return JSONResponse({"error": "invalid service name"}, status_code=400)

    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    try:
        from agents import AgentMesh, HECWriter, LLM
    except Exception as e:
        return JSONResponse({"error": f"agent module unavailable: {e}"},
                            status_code=500)

    hec = HECWriter(os.environ.get("HELIX_HEC_URL"),
                    os.environ.get("HELIX_HEC_TOKEN"))
    key = os.environ.get("HELIX_LLM_API_KEY")
    provider = os.environ.get("HELIX_LLM_PROVIDER", "anthropic")
    model = os.environ.get("HELIX_LLM_MODEL",
                           "claude-opus-4-7" if provider == "anthropic" else "gpt-4o")
    llm = LLM(provider, key, model) if key else None

    # the backend's SplunkClient already exposes .search() — feed it to the mesh
    mesh = AgentMesh(splunk, hec, name, llm=llm, earliest=earliest)
    try:
        opinions = mesh.run()
    except Exception as e:
        log.warning("investigation failed: %s", e)
        return JSONResponse({"error": str(e)}, status_code=500)

    return {"service": name, "ts": time.time(),
            "reasoning_mode": (f"llm:{provider}/{model}" if llm else "deterministic"),
            "opinions": opinions}


# ════════════════════════════════════════════════════════════════════════════
# Sample fallbacks
# ════════════════════════════════════════════════════════════════════════════

def _sample_graph():
    chain = [("cdn-edge", "waf", 0.0), ("waf", "api-gateway", 0.0),
             ("api-gateway", "checkout-api", 0.04),
             ("checkout-api", "fraud-scoring", 0.22),
             ("fraud-scoring", "feature-store", 0.05),
             ("feature-store", "feature-store-db", 0.31),
             ("checkout-api", "payment-orchestrator", 0.0),
             ("payment-orchestrator", "payment-gateway", 0.0)]
    err = {"feature-store-db": 0.31, "fraud-scoring": 0.18, "checkout-api": 0.31}
    cpu = {"feature-store-db": 97.0, "fraud-scoring": 71.0}
    nodes, seen = [], set()
    for s, t, _ in chain:
        for n in (s, t):
            if n not in seen:
                seen.add(n)
                e = err.get(n, 0.0)
                cmax = cpu.get(n, 22.0)
                nodes.append({"id": f"svc:{n}", "label": n, "error_rate": e,
                              "cpu": round(cmax * 0.9, 1), "cpu_max": cmax,
                              "calls_total": 5000,
                              "state": ("critical" if (e > 0.2 or cmax > 90) else
                                        "degraded" if (e > 0.03 or cmax > 75) else "healthy")})
    edges = [{"id": f"e:{s}->{t}", "source": f"svc:{s}", "target": f"svc:{t}",
              "calls": 8000, "avg_ms": 120.0, "error_rate": er,
              "layer": "L1_observed", "confidence": 0.95}
             for s, t, er in chain]
    return {"nodes": nodes, "edges": edges, "ts": time.time()}


def _sample_service(name: str):
    return {
        "service": name,
        "latency": {"calls": 8800, "avg_ms": 322.7, "p50": 110.0,
                    "p95": 1240.0, "p99": 1820.0, "error_rate": 0.29},
        "upstream": [{"service": "checkout-api", "calls": 628, "avg_ms": 322.7}],
        "downstream": [{"service": "feature-store", "calls": 1603,
                        "avg_ms": 48.1, "error_rate": 0.0006}],
        "errors": [{"_time": "now", "level": "ERROR",
                    "message": "feature store call timeout after 1534ms",
                    "http_status": "503", "trace_id": "295ded8d0161"}],
        "hosts": [{"host": f"{name}-7f5d8b-x", "avg_cpu": "71.2",
                   "max_cpu": "88.0", "avg_mem": "63.0"}],
        "incidents": [{"number": "INC6433012",
                       "short_description": "Checkout 5xx spike",
                       "state": "Resolved", "priority": "2"}],
        "spl": {"latency": SPL_SVC_LATENCY.format(service=name)},
    }


def _sample_incidents():
    return [{"number": "INC0123456",
             "short_description": "Elevated checkout API errors in us-east-2",
             "priority": "2", "state": "New",
             "assignment_group": "Payments-SRE", "cmdb_ci": "checkout-api"}]
