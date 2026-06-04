"""
TITAN HELIX · Backend API
══════════════════════════════════════════════════════════════════════════════
FastAPI service that reads telemetry from Splunk and serves:
    GET  /                  → the visual demo (demo.html)
    GET  /health            → liveness + Splunk reachability
    GET  /api/graph         → service dependency graph (nodes + edges from traces)
    GET  /api/incidents     → recent ServiceNow-shaped incidents
    GET  /api/summary       → error counts + p99 by service
    GET  /api/timeline      → error volume over time (for replay)

If Splunk is unreachable, endpoints return SAMPLE data so the frontend still
demos. Every response includes "source": "splunk" | "sample".

RUN
───
    pip install -r backend/requirements.txt
    export HELIX_SPLUNK_API_URL=https://localhost:8089
    export HELIX_SPLUNK_API_PASSWORD=ChangeMe_Helix_2026
    uvicorn backend.app:app --host 0.0.0.0 --port 8080 --reload

    open http://localhost:8080
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from backend.splunk_client import SplunkClient

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(name)s] %(message)s")
log = logging.getLogger("helix.api")

app = FastAPI(title="TITAN HELIX API", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])

splunk = SplunkClient.from_env()

DEMO_HTML = Path(__file__).resolve().parent.parent / "demo.html"


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
"""

SPL_SERVICE_HEALTH = """
index=helix_logs sourcetype="helix:logs:app"
| stats count as total,
        sum(eval(if(level="ERROR",1,0))) as errors by service
| eval error_rate = round(errors/total, 4)
| sort - error_rate
"""

SPL_INCIDENTS = """
index=helix_incidents sourcetype="helix:incidents:servicenow"
| sort - _time
| table _time, number, short_description, priority, severity, state,
        assignment_group, cmdb_ci
| head 25
"""

SPL_TIMELINE = """
index=helix_logs sourcetype="helix:logs:app" level=ERROR
| timechart span=1m count by service limit=8
"""


# ════════════════════════════════════════════════════════════════════════════
# Routes
# ════════════════════════════════════════════════════════════════════════════

@app.get("/")
def root():
    if DEMO_HTML.exists():
        return FileResponse(str(DEMO_HTML))
    return JSONResponse({"message": "TITAN HELIX API", "demo": "demo.html not found"})


@app.get("/health")
def health():
    up = splunk.ping()
    return {"status": "ok", "splunk_reachable": up,
            "api_url": splunk.api_url}


@app.get("/api/graph")
def graph(earliest: str = "-15m@m"):
    rows = splunk.search(SPL_DEPS, earliest=earliest)
    if not rows:
        return {"source": "sample", **_sample_graph()}

    # Build nodes + edges
    health_rows = splunk.search(SPL_SERVICE_HEALTH, earliest=earliest)
    health = {r["service"]: r for r in health_rows}

    nodes: dict[str, dict] = {}
    edges = []

    def ensure_node(name: str):
        if name not in nodes:
            h = health.get(name, {})
            err = float(h.get("error_rate", 0) or 0)
            nodes[name] = {
                "id": f"svc:{name}", "label": name,
                "error_rate": err,
                "state": ("critical" if err > 0.2 else
                          "degraded" if err > 0.03 else "healthy"),
            }

    for r in rows:
        s, t = r["source"], r["target"]
        ensure_node(s)
        ensure_node(t)
        err = float(r.get("error_rate", 0) or 0)
        edges.append({
            "id": f"e:{s}->{t}",
            "source": f"svc:{s}", "target": f"svc:{t}",
            "calls": int(float(r.get("calls", 0))),
            "avg_ms": round(float(r.get("avg_ms", 0) or 0), 1),
            "error_rate": err,
            "layer": "L1_observed",
            "confidence": round(min(0.99, 0.5 + 0.05 *
                                    (int(float(r.get("calls", 1))) ** 0.3)), 2),
        })

    return {"source": "splunk", "nodes": list(nodes.values()), "edges": edges}


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


# ════════════════════════════════════════════════════════════════════════════
# Sample fallbacks — so the frontend works with no Splunk
# ════════════════════════════════════════════════════════════════════════════

def _sample_graph():
    nodes = [
        {"id": "svc:checkout-api", "label": "checkout-api",
         "error_rate": 0.31, "state": "degraded"},
        {"id": "svc:fraud-scoring", "label": "fraud-scoring",
         "error_rate": 0.18, "state": "degraded"},
        {"id": "svc:feature-store-db", "label": "feature-store-db",
         "error_rate": 0.04, "state": "critical"},
        {"id": "svc:payment-orchestrator", "label": "payment-orchestrator",
         "error_rate": 0.02, "state": "healthy"},
    ]
    edges = [
        {"id": "e1", "source": "svc:checkout-api", "target": "svc:fraud-scoring",
         "calls": 12400, "error_rate": 0.22, "layer": "L1_observed",
         "confidence": 0.97},
        {"id": "e2", "source": "svc:fraud-scoring", "target": "svc:feature-store-db",
         "calls": 8800, "error_rate": 0.31, "layer": "L1_observed",
         "confidence": 0.91},
    ]
    return {"nodes": nodes, "edges": edges}


def _sample_incidents():
    return [
        {"number": "INC0123456", "short_description":
         "Elevated checkout API errors in us-east-2", "priority": "2",
         "state": "New", "assignment_group": "Payments-SRE",
         "cmdb_ci": "checkout-api"},
    ]
