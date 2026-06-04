#!/usr/bin/env python3
"""
TITAN HELIX · Standalone Synthetic Telemetry Generator
══════════════════════════════════════════════════════════════════════════════
A SINGLE FILE that generates realistic enterprise telemetry. No package
install, no docker, no monorepo. Just Python + pyyaml + requests.

QUICK START
───────────
    pip install pyyaml requests

    # 1. See events on stdout (no Splunk needed) — quick smoke test
    python3 synth_generator.py --stdout --duration 30

    # 2. Run a chaos scenario in stdout mode
    python3 synth_generator.py --stdout --duration 120 \\
        --scenario scenarios/checkout_collapse.yaml --speed 10

    # 3. Send to Splunk HEC
    python3 synth_generator.py \\
        --hec-url http://localhost:8088 \\
        --hec-token YOUR-UUID-TOKEN \\
        --scenario scenarios/checkout_collapse.yaml --speed 10

WHAT IT EMITS
─────────────
    • helix:metrics:cpu        — per-host CPU%
    • helix:metrics:mem        — per-host memory%
    • helix:metrics:net        — per-host network bytes
    • helix:metrics:k8s        — pod ready/phase/restarts
    • helix:metrics:business   — checkout completion, POS tx/min, auth success
    • helix:logs:app           — application logs (INFO/WARN/ERROR)
    • helix:traces:span        — distributed trace spans (W3C-shaped)
    • helix:incidents:servicenow — ITSM tickets
    • helix:deploy:event       — CI/CD events
    • helix:scenario:event     — audit of scenario phase transitions

TOPOLOGY
────────
A retail-payments enterprise with 28 services, ~250 hosts (k8s pods + VMs +
Lambda/Fargate ENIs), plus ~1,200 POS terminals across 6 cities.

Deterministic for a given --seed.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import math
import random
import secrets
import signal
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

try:
    import yaml
except ImportError:
    sys.exit("Missing dep: pip install pyyaml")

try:
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except ImportError:
    sys.exit("Missing dep: pip install requests")

log = logging.getLogger("helix.synth")


# ════════════════════════════════════════════════════════════════════════════
# WORLD MODEL
# ════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class Region:
    code: str
    cloud: Literal["aws", "azure", "gcp", "on-prem"]
    azs: tuple[str, ...]


@dataclass
class Service:
    name: str
    tier: Literal["edge", "api", "core", "data", "infra"]
    runtime: Literal["k8s", "vm", "lambda", "fargate"]
    region: Region
    replicas: int
    deps: list[str] = field(default_factory=list)
    criticality: int = 3


@dataclass
class Host:
    hostname: str
    kind: Literal["ec2", "vm", "pod", "pos", "edge", "cdn-node"]
    region: Region
    az: str
    runs: list[str] = field(default_factory=list)


class EnterpriseWorld:
    """Builds the hidden ground-truth topology of a retail-payments enterprise."""

    def __init__(self, seed: int = 42):
        self.rng = random.Random(seed)
        self.regions = self._build_regions()
        self.services = self._build_services()
        self.hosts = self._build_hosts()

    def _build_regions(self) -> list[Region]:
        return [
            Region("us-east-2",      "aws", ("use2-az1", "use2-az2", "use2-az3")),
            Region("us-west-2",      "aws", ("usw2-az1", "usw2-az2")),
            Region("eu-west-1",      "aws", ("euw1-az1", "euw1-az2", "euw1-az3")),
            Region("ap-south-1",     "aws", ("aps1-az1", "aps1-az2")),
            Region("ap-southeast-1", "aws", ("apse1-az1", "apse1-az2")),
        ]

    def _build_services(self) -> list[Service]:
        # name, tier, runtime, deps
        catalog = [
            ("cdn-edge",             "edge", "lambda",  ["waf"]),
            ("waf",                  "edge", "lambda",  ["api-gateway"]),
            ("api-gateway",          "edge", "k8s",     ["auth-service", "checkout-api", "catalog-api"]),
            ("auth-service",         "api",  "k8s",     ["session-store", "user-db", "mfa-broker"]),
            ("mfa-broker",           "api",  "k8s",     []),
            ("checkout-api",         "api",  "k8s",     ["cart-service", "pricing-engine",
                                                          "payment-orchestrator", "fraud-scoring",
                                                          "inventory-service"]),
            ("catalog-api",          "api",  "k8s",     ["catalog-db", "search-cluster", "cache-cluster"]),
            ("cart-service",         "api",  "k8s",     ["cache-cluster", "session-store"]),
            ("pricing-engine",       "api",  "k8s",     ["pricing-db", "promo-service"]),
            ("promo-service",        "api",  "k8s",     ["promo-db"]),
            ("inventory-service",    "api",  "k8s",     ["inventory-db"]),
            ("payment-orchestrator", "core", "k8s",     ["payment-gateway", "fraud-scoring",
                                                          "ledger-service"]),
            ("payment-gateway",      "core", "k8s",     []),
            ("fraud-scoring",        "core", "fargate", ["fraud-model-server", "feature-store"]),
            ("fraud-model-server",   "core", "fargate", ["feature-store"]),
            ("ledger-service",       "core", "k8s",     ["ledger-db"]),
            ("user-db",              "data", "vm",      []),
            ("catalog-db",           "data", "vm",      []),
            ("pricing-db",           "data", "vm",      []),
            ("promo-db",             "data", "vm",      []),
            ("inventory-db",         "data", "vm",      []),
            ("ledger-db",            "data", "vm",      []),
            ("session-store",        "data", "k8s",     []),
            ("cache-cluster",        "data", "k8s",     []),
            ("search-cluster",       "data", "vm",      []),
            ("feature-store",        "data", "k8s",     ["feature-store-db"]),
            ("feature-store-db",     "data", "vm",      []),
            ("pos-gateway",          "edge", "k8s",     ["api-gateway", "store-sync"]),
            ("store-sync",           "core", "k8s",     ["inventory-service", "ledger-service"]),
        ]
        services = []
        critical = {"payment-orchestrator", "payment-gateway", "checkout-api",
                    "auth-service", "ledger-service", "fraud-scoring"}
        for name, tier, runtime, deps in catalog:
            region = self.rng.choice(self.regions[:3])  # majority US/EU
            services.append(Service(
                name=name, tier=tier, runtime=runtime, region=region,
                replicas=self.rng.choice([3, 4, 6, 8]) if runtime == "k8s" else 1,
                deps=deps,
                criticality=1 if name in critical else 3,
            ))
        return services

    def _build_hosts(self) -> list[Host]:
        hosts: list[Host] = []
        for svc in self.services:
            if svc.runtime == "k8s":
                for _ in range(svc.replicas):
                    rs = ''.join(self.rng.choices("abcdef0123456789", k=10))
                    suffix = ''.join(self.rng.choices(
                        "abcdefghijklmnopqrstuvwxyz0123456789", k=5))
                    hosts.append(Host(
                        hostname=f"{svc.name}-{rs}-{suffix}",
                        kind="pod", region=svc.region,
                        az=self.rng.choice(svc.region.azs),
                        runs=[svc.name],
                    ))
            elif svc.runtime == "vm":
                # Clean region slug: az "use2-az1" -> "use2" (vs ugly "us-e")
                slug = svc.region.azs[0].split("-az")[0]
                for idx in range(1, 4):
                    hosts.append(Host(
                        hostname=f"{svc.name}-vm-{slug}-prod-{idx:02d}",
                        kind="vm", region=svc.region,
                        az=self.rng.choice(svc.region.azs),
                        runs=[svc.name],
                    ))
            else:
                hosts.append(Host(
                    hostname=f"ip-10-{self.rng.randint(10,99)}-"
                              f"{self.rng.randint(0,255)}-"
                              f"{self.rng.randint(1,254)}."
                              f"{svc.region.code}.compute.internal",
                    kind="ec2", region=svc.region,
                    az=self.rng.choice(svc.region.azs),
                    runs=[svc.name],
                ))
        # POS terminals
        cities = [("mumbai", "ap-south-1", 220), ("delhi", "ap-south-1", 198),
                  ("singapore", "ap-southeast-1", 256), ("london", "eu-west-1", 241),
                  ("nyc", "us-east-2", 214), ("austin", "us-east-2", 186)]
        for city, region_code, count in cities:
            region = next(r for r in self.regions if r.code == region_code)
            for i in range(1, count + 1):
                hosts.append(Host(
                    hostname=f"pos-terminal-{city}-{i:03d}",
                    kind="pos", region=region, az=region.azs[0],
                    runs=["pos-gateway"],
                ))
        return hosts


# ════════════════════════════════════════════════════════════════════════════
# SCENARIO MODEL
# ════════════════════════════════════════════════════════════════════════════

@dataclass
class ServiceModifier:
    cpu_boost: float = 0.0
    mem_boost: float = 0.0
    io_wait_boost: float = 0.0
    net_mult: float = 0.0
    error_rate: float | None = None
    latency_p99_ms: float | None = None
    request_rate_mult: float = 1.0
    not_ready: bool = False


@dataclass
class LogInjection:
    service: str
    level: str
    template: str
    fields: dict[str, Any]
    rate_per_min: float


@dataclass
class ScenarioFrame:
    t_seconds: float
    service_modifiers: dict[str, ServiceModifier] = field(default_factory=dict)
    pos_offline_pct: dict[str, float] = field(default_factory=dict)
    log_injections: list[LogInjection] = field(default_factory=list)
    new_incidents: list[dict] = field(default_factory=list)
    new_deploys: list[dict] = field(default_factory=list)
    business_kpis: list[dict] = field(default_factory=list)
    audit_events: list[dict] = field(default_factory=list)
    active_phase_names: list[str] = field(default_factory=list)


class Scenario:
    """YAML-driven scenario. Walks phases in temporal order, applies modifiers."""

    def __init__(self, yaml_path: str | Path | None = None):
        if yaml_path:
            self.spec = yaml.safe_load(Path(yaml_path).read_text())
            self.name = self.spec["name"]
            self.duration_seconds = self.spec.get("duration_seconds", 900)
            self.phases = sorted(self.spec.get("phases", []), key=lambda p: p["at"])
        else:
            self.spec = {}
            self.name = "baseline"
            self.duration_seconds = 999999
            self.phases = []
        self.t0: float | None = None
        self._fired: set[str] = set()

    def start(self, now: float):
        self.t0 = now

    def elapsed(self, now: float) -> float:
        return now - (self.t0 or now)

    def finished(self, now: float) -> bool:
        return self.elapsed(now) >= self.duration_seconds

    def tick(self, now: float) -> ScenarioFrame:
        t = self.elapsed(now)
        frame = ScenarioFrame(t_seconds=t)

        for ph in self.phases:
            at = ph["at"]
            duration = ph.get("duration", self.duration_seconds - at)
            if t < at or t >= at + duration:
                continue
            frame.active_phase_names.append(ph["name"])

            if self._fire_once(f"phase:{ph['name']}:start"):
                frame.audit_events.append({"type": "phase_started",
                                            "phase": ph["name"],
                                            "scenario": self.name})

            for effect in ph.get("affects", []) or []:
                self._apply_effect(effect, ph, t - at, frame)

        return frame

    def _fire_once(self, key: str) -> bool:
        if key in self._fired: return False
        self._fired.add(key)
        return True

    def _apply_effect(self, effect: dict, phase: dict,
                       phase_t: float, frame: ScenarioFrame):
        target = effect.get("target", {})
        kind = target.get("kind")
        if kind == "service":
            self._apply_service(effect, phase_t, frame)
        elif kind == "log":
            for item in effect.get("inject", []) or []:
                frame.log_injections.append(LogInjection(
                    service=target["service"], level=item.get("level", "INFO"),
                    template=item["template"], fields=item.get("fields", {}) or {},
                    rate_per_min=item.get("rate_per_min", 10),
                ))
        elif kind == "pos":
            mods = effect.get("modifiers", {}) or {}
            ramp = mods.get("ramp_seconds", 0)
            progress = min(1.0, phase_t / ramp) if ramp > 0 else 1.0
            frame.pos_offline_pct[target["region"]] = \
                mods.get("offline_pct", 0.0) * progress
        elif kind == "incident":
            if "create" in effect and self._fire_once(f"inc:{phase['name']}"):
                frame.new_incidents.append(effect["create"])
        elif kind == "deploy":
            if "create" in effect and self._fire_once(f"dep:{phase['name']}"):
                frame.new_deploys.append(effect["create"])
        elif kind == "business_kpi":
            frame.business_kpis.append({"metric": effect["metric"],
                                         "region": effect.get("region", "global"),
                                         **(effect.get("modify") or {})})

    def _apply_service(self, effect: dict, phase_t: float, frame: ScenarioFrame):
        name = effect["target"]["name"]
        m = effect.get("modifiers", {}) or {}
        ramp = m.get("ramp_seconds", 0)
        progress = min(1.0, phase_t / ramp) if ramp > 0 else 1.0
        mod = ServiceModifier(
            cpu_boost=m.get("cpu_boost", 0) * progress,
            mem_boost=m.get("mem_boost", 0) * progress,
            io_wait_boost=m.get("io_wait_boost", 0) * progress,
            net_mult=m.get("net_mult", 0) * progress,
            error_rate=m.get("error_rate"),
            latency_p99_ms=m.get("latency_p99_ms"),
            request_rate_mult=1.0 + (m.get("request_rate_mult", 1.0) - 1.0) * progress,
            not_ready=m.get("not_ready", False),
        )
        frame.service_modifiers[name] = mod


# ════════════════════════════════════════════════════════════════════════════
# SINKS
# ════════════════════════════════════════════════════════════════════════════

class Sink:
    def emit(self, sourcetype: str, index: str, event: dict): ...
    def flush(self): ...
    def close(self): ...


class StdoutSink(Sink):
    """Prints one JSON event per line. Great for testing without Splunk."""
    def __init__(self):
        self.count = 0
        self.last_summary = time.monotonic()

    def emit(self, sourcetype, index, event):
        out = {"time": event.get("ts", time.time()),
                "sourcetype": sourcetype, "index": index, "event": event}
        sys.stdout.write(json.dumps(out) + "\n")
        sys.stdout.flush()
        self.count += 1

    def flush(self): pass
    def close(self):
        sys.stderr.write(f"\n[stdout sink] emitted {self.count:,} events\n")


class FileSink(Sink):
    """Write HEC-envelope JSON lines to a file. Loadable later via load_to_splunk.py.

    Each line is a complete HEC event with a `time` field, so Splunk places the
    event at its (possibly historical) timestamp when the file is replayed.
    """
    def __init__(self, path: str):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.fh = open(path, "w")
        self.count = 0

    def emit(self, sourcetype, index, event):
        self.fh.write(json.dumps({
            "time": event.get("ts", time.time()),
            "host": event.get("host") or "helix-synth",
            "source": "helix-synth",
            "sourcetype": sourcetype,
            "index": index,
            "event": event,
        }) + "\n")
        self.count += 1

    def flush(self):
        self.fh.flush()

    def close(self):
        self.fh.flush()
        self.fh.close()
        sys.stderr.write(f"\n[file sink] wrote {self.count:,} events → {self.path}\n")


class HECSink(Sink):
    """Splunk HTTP Event Collector. Batches 200 events at a time."""
    def __init__(self, url: str, token: str, batch_size: int = 200,
                  flush_interval: float = 1.0, verify_ssl: bool = False):
        self.url = url.rstrip("/") + "/services/collector/event"
        self.token = token
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self.buf: list[str] = []
        self.last_flush = time.monotonic()
        self.session = requests.Session()
        retry = Retry(total=3, backoff_factor=0.3,
                      status_forcelist=(500, 502, 503, 504))
        self.session.mount("http://",  HTTPAdapter(max_retries=retry))
        self.session.mount("https://", HTTPAdapter(max_retries=retry))
        self.session.headers = {"Authorization": f"Splunk {token}"}
        self.session.verify = verify_ssl
        self.count = 0
        self.failed = 0

    def emit(self, sourcetype, index, event):
        self.buf.append(json.dumps({
            "time": event.get("ts", time.time()),
            "host": event.get("host") or "helix-synth",
            "source": "helix-synth",
            "sourcetype": sourcetype,
            "index": index,
            "event": event,
        }))
        if (len(self.buf) >= self.batch_size or
                time.monotonic() - self.last_flush >= self.flush_interval):
            self.flush()

    def flush(self):
        if not self.buf: return
        body = "\n".join(self.buf)
        try:
            r = self.session.post(self.url, data=body, timeout=10)
            r.raise_for_status()
            self.count += len(self.buf)
        except Exception as e:
            self.failed += len(self.buf)
            log.warning("HEC flush failed (dropped %d): %s", len(self.buf), e)
        self.buf.clear()
        self.last_flush = time.monotonic()

    def close(self):
        self.flush()
        sys.stderr.write(f"\n[hec sink] sent {self.count:,} events"
                          f" · failed {self.failed:,}\n")


class FanoutSink(Sink):
    """Emit to multiple sinks at once (e.g. stdout AND hec)."""
    def __init__(self, sinks: list[Sink]):
        self.sinks = sinks
    def emit(self, *a, **kw):
        for s in self.sinks: s.emit(*a, **kw)
    def flush(self):
        for s in self.sinks: s.flush()
    def close(self):
        for s in self.sinks: s.close()


# ════════════════════════════════════════════════════════════════════════════
# ORCHESTRATOR
# ════════════════════════════════════════════════════════════════════════════

def resolve_fields(fields: dict[str, Any], rng: random.Random) -> dict[str, Any]:
    """Resolve {placeholders} in log templates."""
    out = {}
    for k, v in fields.items():
        if isinstance(v, dict):
            if "random_between" in v:
                lo, hi = v["random_between"]
                out[k] = rng.randint(int(lo), int(hi))
            elif "generated" in v:
                kind = v["generated"]
                if kind == "hex16":   out[k] = secrets.token_hex(16)
                elif kind == "hex12": out[k] = secrets.token_hex(12)
                elif kind == "uuid":
                    import uuid; out[k] = str(uuid.uuid4())
                else: out[k] = secrets.token_hex(8)
            elif "choice" in v:
                out[k] = rng.choice(v["choice"])
            else:
                out[k] = str(v)
        else:
            out[k] = v
    return out


class Orchestrator:
    """The conductor."""

    def __init__(self, world: EnterpriseWorld, scenario: Scenario, sink: Sink,
                  tick_hz: float = 4.0, speed: float = 1.0, seed: int = 1,
                  start_time: float | None = None):
        self.world = world
        self.scenario = scenario
        self.sink = sink
        self.tick_hz = tick_hz
        self.speed = speed
        self.rng = random.Random(seed)
        self.tick_count = 0
        self.running = False
        self.sim_now = start_time if start_time is not None else time.time()
        self.log_credits: dict[tuple, float] = {}
        self.event_count = 0

    def run(self):
        self.running = True
        self.scenario.start(self.sim_now)
        tick_interval = 1.0 / self.tick_hz
        sys.stderr.write(
            f"[orchestrator] starting · scenario={self.scenario.name} · "
            f"tick={tick_interval:.2f}s · speed={self.speed:.1f}x · "
            f"hosts={len(self.world.hosts):,}\n")
        last_progress = time.monotonic()

        while self.running:
            t0 = time.monotonic()
            self._tick()
            elapsed = time.monotonic() - t0
            time.sleep(max(0, tick_interval - elapsed))
            self.sim_now += tick_interval * self.speed

            # Progress line every 5s real-time
            if time.monotonic() - last_progress >= 5.0:
                self._progress()
                last_progress = time.monotonic()

            if self.scenario.finished(self.sim_now):
                sys.stderr.write("\n[orchestrator] scenario finished\n")
                self.running = False
        self.sink.flush()

    def stop(self): self.running = False

    def _progress(self):
        t = self.scenario.elapsed(self.sim_now)
        phases = ",".join(self.scenario.tick(self.sim_now).active_phase_names) or "-"
        sys.stderr.write(f"\r[t+{int(t):>4}s] phase={phases:<40s} "
                          f"events={self.event_count:>7,}")
        sys.stderr.flush()

    def _tick(self):
        self.tick_count += 1
        frame = self.scenario.tick(self.sim_now)

        for a in frame.audit_events:
            self._emit("helix:scenario:event", "helix_audit",
                       {**a, "ts": self.sim_now})

        self._tick_metrics(frame)
        self._tick_logs(frame)
        self._tick_traces(frame)
        for inc in frame.new_incidents: self._emit_incident(inc)
        for d in frame.new_deploys: self._emit_deploy(d)
        if self.tick_count % int(self.tick_hz * 5) == 0:
            self._tick_business(frame)

    # ─── per-tick emitters ──────────────────────────────────────────────────

    def _tick_metrics(self, frame: ScenarioFrame):
        for host in self.world.hosts:
            svc = host.runs[0] if host.runs else None
            mod = frame.service_modifiers.get(svc, ServiceModifier()) if svc else ServiceModifier()
            cpu = self._noisy(host, 28) + mod.cpu_boost
            mem = self._noisy(host, 55) + mod.mem_boost
            rx  = self._noisy(host, 110) * (1 + mod.net_mult)
            tx  = self._noisy(host, 85)  * (1 + mod.net_mult)
            common = {"ts": self.sim_now, "host": host.hostname, "service": svc,
                      "region": host.region.code, "az": host.az, "kind": host.kind}
            self._emit("helix:metrics:cpu", "helix_metrics",
                        {**common, "cpu_pct": round(min(cpu, 99.9), 2)})
            self._emit("helix:metrics:mem", "helix_metrics",
                        {**common, "mem_pct": round(min(mem, 99.9), 2)})
            self._emit("helix:metrics:net", "helix_metrics",
                        {**common, "rx_kbps": round(rx, 1), "tx_kbps": round(tx, 1)})
            if host.kind == "pod":
                not_ready = mod.not_ready
                self._emit("helix:metrics:k8s", "helix_metrics",
                            {**common, "restarts": 0,
                             "ready": not not_ready,
                             "phase": "Running" if not not_ready else "CrashLoopBackOff"})
            elif host.kind == "pos":
                offline = self.rng.random() < frame.pos_offline_pct.get(host.region.code, 0.0)
                self._emit("helix:metrics:k8s", "helix_metrics",
                            {**common, "ready": not offline,
                             "phase": "Offline" if offline else "Running"})

    def _noisy(self, host: Host, base: float) -> float:
        offset = (hash(host.hostname) % 100) / 100.0 * 10 - 5
        noise = self.rng.gauss(0, base * 0.07)
        hour = (self.sim_now // 3600) % 24
        diurnal = 0.5 + 0.4 * math.sin((hour - 14) * math.pi / 12)
        return max(0, base * diurnal + offset + noise)

    def _tick_logs(self, frame: ScenarioFrame):
        # Scale by speed: each real tick advances (tick_seconds * speed) sim-seconds,
        # so rate-based emissions must reflect that many sim-seconds of activity.
        tick_seconds = (1.0 / self.tick_hz) * self.speed
        for svc in self.world.services:
            mod = frame.service_modifiers.get(svc.name, ServiceModifier())
            error_rate = mod.error_rate if mod.error_rate is not None else 0.001
            rate = 30 / 60.0 * tick_seconds   # 30 logs/min baseline per service
            n = self._poisson(rate)
            host = self._pick_host(svc)
            for _ in range(n):
                is_err = self.rng.random() < error_rate
                level = "ERROR" if is_err else self.rng.choices(
                    ["INFO", "DEBUG", "WARN"], weights=[70, 20, 10])[0]
                self._emit("helix:logs:app", "helix_logs", {
                    "ts": self.sim_now, "service": svc.name,
                    "host": host.hostname if host else None,
                    "region": svc.region.code, "level": level,
                    "trace_id": secrets.token_hex(16),
                    "span_id":  secrets.token_hex(12),
                    "message": self._baseline_msg(svc, level),
                    "deployment": f"{svc.name}@v1.{self.rng.randint(0,99)}.{self.rng.randint(0,9)}",
                })

        for inj in frame.log_injections:
            key = (inj.service, inj.template)
            credit = self.log_credits.get(key, 0.0)
            credit += inj.rate_per_min / 60.0 * tick_seconds
            n = int(credit)
            self.log_credits[key] = credit - n
            for _ in range(n):
                svc = next((s for s in self.world.services
                            if s.name == inj.service), None)
                if not svc: continue
                host = self._pick_host(svc)
                fields = resolve_fields(inj.fields, self.rng)
                if "{pos_hostname}" in inj.template:
                    pos = [h for h in self.world.hosts
                           if h.kind == "pos" and
                              h.region.code == fields.get("region", "")]
                    if pos: fields["pos_hostname"] = self.rng.choice(pos).hostname
                msg = inj.template.format(**fields)
                self._emit("helix:logs:app", "helix_logs", {
                    "ts": self.sim_now, "service": svc.name,
                    "host": host.hostname if host else None,
                    "region": svc.region.code, "level": inj.level,
                    "message": msg,
                    **{k: v for k, v in fields.items() if k != "pos_hostname"},
                })

    def _tick_traces(self, frame: ScenarioFrame):
        tick_seconds = (1.0 / self.tick_hz) * self.speed
        for svc in self.world.services:
            if not svc.deps: continue
            mod = frame.service_modifiers.get(svc.name, ServiceModifier())
            rate = 200 / 60.0 * tick_seconds * mod.request_rate_mult
            n = self._poisson(rate)
            for _ in range(n):
                downstream = self.rng.choice(svc.deps)
                ds_mod = frame.service_modifiers.get(downstream, ServiceModifier())
                duration = (ds_mod.latency_p99_ms or
                            self._sample_latency(downstream))
                duration *= 0.6 + self.rng.random() * 0.8
                error = self.rng.random() < (ds_mod.error_rate or 0.001)
                host = self._pick_host(svc)
                self._emit("helix:traces:span", "helix_traces", {
                    "ts": self.sim_now,
                    "trace_id": secrets.token_hex(16),
                    "span_id": secrets.token_hex(12),
                    "parent_span_id": secrets.token_hex(12),
                    "service": downstream, "parent_service": svc.name,
                    "host": host.hostname if host else None,
                    "operation": f"call_{downstream}",
                    "duration_ms": round(duration, 2),
                    "status": "ERROR" if error else "OK",
                    "tags": {"region": svc.region.code,
                             "user_tier": self.rng.choice(["free","gold","platinum"])},
                })

    def _sample_latency(self, downstream: str) -> float:
        p50 = {"data": 35, "core": 80, "api": 45, "edge": 12, "infra": 8}
        svc = next((s for s in self.world.services if s.name == downstream), None)
        base = p50.get(svc.tier, 50) if svc else 50
        return base * (1 + abs(self.rng.gauss(0, 0.6)) ** 2)

    def _emit_incident(self, c: dict):
        number = f"INC{self.rng.randint(1_000_000, 9_999_999)}"
        self._emit("helix:incidents:servicenow", "helix_incidents", {
            "ts": self.sim_now, "number": number,
            "short_description": c.get("short_description", ""),
            "category": c.get("category", "Application"),
            "subcategory": c.get("subcategory", "Availability"),
            "priority": str(c.get("priority", "3")),
            "severity": str(c.get("severity", "3")),
            "state": c.get("state", "New"),
            "assignment_group": c.get("assignment_group", "Platform-SRE"),
            "cmdb_ci": c.get("cmdb_ci"),
            "u_source": c.get("u_source", "helix-synth"),
            "u_confidence": float(c.get("u_confidence", 1.0)),
        })

    def _emit_deploy(self, d: dict):
        self._emit("helix:deploy:event", "helix_deploy", {
            "ts": self.sim_now, "service": d.get("service"),
            "version": d.get("version"), "previous": d.get("previous", "unknown"),
            "rollout": d.get("rollout", "rolling"),
            "actor": d.get("actor", "ci-bot"),
            "pipeline": d.get("pipeline", ""),
            "change_id": d.get("change_id", ""),
        })

    def _tick_business(self, frame: ScenarioFrame):
        overrides = {(k["metric"], k["region"]): k for k in frame.business_kpis}
        baseline = [
            ("checkout_completion_rate", "us-east-2", 0.972),
            ("checkout_completion_rate", "eu-west-1", 0.968),
            ("pos_transactions_per_min", "ap-south-1", 14200),
            ("pos_transactions_per_min", "us-east-2", 21800),
            ("auth_success_rate", "global", 0.994),
        ]
        for metric, region, base in baseline:
            ov = overrides.get((metric, region))
            if ov:
                if ov.get("absolute") is not None: value = ov["absolute"]
                elif ov.get("mult") is not None:   value = base * ov["mult"]
                else: value = base
            else:
                value = base * (1 + self.rng.gauss(0, 0.02))
            self._emit("helix:metrics:business", "helix_business", {
                "ts": self.sim_now, "metric": metric, "region": region,
                "value": round(value, 4), "baseline": base,
            })

    # ─── helpers ────────────────────────────────────────────────────────────

    def _emit(self, sourcetype: str, index: str, event: dict):
        self.sink.emit(sourcetype, index, event)
        self.event_count += 1

    def _pick_host(self, svc: Service):
        hosts = [h for h in self.world.hosts if svc.name in (h.runs or [])]
        return self.rng.choice(hosts) if hosts else None

    def _poisson(self, lam: float) -> int:
        if lam <= 0: return 0
        L = math.exp(-lam); k = 0; p = 1
        while p > L:
            k += 1; p *= self.rng.random()
        return k - 1

    def _baseline_msg(self, svc: Service, level: str) -> str:
        msgs = {
            "INFO":  ["served request", "request completed", "health check ok"],
            "DEBUG": ["span recorded", "cache hit", "preflight passed"],
            "WARN":  ["retry after backoff", "slow path engaged"],
            "ERROR": ["downstream unavailable", "deadline exceeded",
                      "schema validation failed"],
        }
        return self.rng.choice(msgs.get(level, ["event"]))


# ════════════════════════════════════════════════════════════════════════════
# CLI
# ════════════════════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser(
        description="TITAN HELIX synthetic telemetry generator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("WHAT IT EMITS")[0],
    )
    ap.add_argument("--scenario", type=str, default=None,
                    help="Path to scenario YAML (omit for baseline-only)")
    ap.add_argument("--stdout", action="store_true",
                    help="Emit events as JSON lines on stdout")
    ap.add_argument("--hec-url", type=str, default=None,
                    help="Splunk HEC URL, e.g. http://localhost:8088")
    ap.add_argument("--hec-token", type=str, default=None,
                    help="Splunk HEC token")
    ap.add_argument("--output", type=str, default=None,
                    help="Write events as HEC-envelope JSONL to this file "
                          "(loadable later via load_to_splunk.py)")
    ap.add_argument("--start-offset-hours", type=float, default=0.0,
                    help="Start the simulation clock this many hours in the past "
                          "(for historical backfill)")
    ap.add_argument("--verify-ssl", action="store_true",
                    help="Verify SSL when posting to HEC")
    ap.add_argument("--duration", type=int, default=0,
                    help="Stop after this many real-time seconds (0=run until "
                          "scenario completes or Ctrl-C)")
    ap.add_argument("--speed", type=float, default=1.0,
                    help="Simulated-time speed multiplier (10 = 10x faster)")
    ap.add_argument("--tick-hz", type=float, default=4.0,
                    help="Generator tick rate")
    ap.add_argument("--seed", type=int, default=42,
                    help="Deterministic seed")
    ap.add_argument("--quiet", action="store_true", help="Suppress info logs")
    args = ap.parse_args()

    logging.basicConfig(level=logging.WARNING if args.quiet else logging.INFO,
                         format="%(asctime)s [%(name)s] %(message)s")

    # Build sink
    sinks: list[Sink] = []
    if args.stdout: sinks.append(StdoutSink())
    if args.output: sinks.append(FileSink(args.output))
    if args.hec_url:
        if not args.hec_token:
            sys.exit("--hec-url requires --hec-token")
        sinks.append(HECSink(args.hec_url, args.hec_token,
                              verify_ssl=args.verify_ssl))
    if not sinks:
        sinks.append(StdoutSink())   # default
    sink = sinks[0] if len(sinks) == 1 else FanoutSink(sinks)

    # Build world + scenario
    world = EnterpriseWorld(seed=args.seed)
    scenario = Scenario(args.scenario)

    # Historical backfill: start the clock in the past
    start_time = time.time() - args.start_offset_hours * 3600 \
                 if args.start_offset_hours > 0 else None

    sys.stderr.write(
        f"[world] regions={len(world.regions)} "
        f"services={len(world.services)} "
        f"hosts={len(world.hosts):,} "
        f"(pods={sum(1 for h in world.hosts if h.kind=='pod')} "
        f"vms={sum(1 for h in world.hosts if h.kind=='vm')} "
        f"pos={sum(1 for h in world.hosts if h.kind=='pos')})\n")
    if start_time:
        import datetime as _dt
        sys.stderr.write(f"[historical] sim clock starts at "
                          f"{_dt.datetime.fromtimestamp(start_time).isoformat()} "
                          f"({args.start_offset_hours}h ago)\n")

    orch = Orchestrator(world, scenario, sink,
                         tick_hz=args.tick_hz, speed=args.speed, seed=args.seed,
                         start_time=start_time)

    # Ctrl-C handling
    def _stop(*_):
        sys.stderr.write("\n[orchestrator] stopping…\n")
        orch.stop()
    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    # Hard duration cap
    if args.duration > 0:
        import threading
        def kill():
            time.sleep(args.duration); orch.stop()
        threading.Thread(target=kill, daemon=True).start()

    try:
        orch.run()
    finally:
        sink.close()


if __name__ == "__main__":
    main()
