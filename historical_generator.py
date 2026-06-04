#!/usr/bin/env python3
"""
TITAN HELIX · Historical Telemetry Backfill Generator
══════════════════════════════════════════════════════════════════════════════
Produces a DUMP FILE of past telemetry you load into Splunk once, so the
platform has history: baselines for anomaly detection, past incidents for the
Memory agent to recall, and a graph that "evolved over time".

Unlike synth_generator.py (which streams the live firehose), this walks backward
in time in coarse buckets (default 5 min) and emits a DOWNSAMPLED, realistic
history with diurnal + weekly patterns and a handful of embedded past incidents.

QUICK START
───────────
    pip install pyyaml requests

    # Generate 7 days of history into a dump file
    python3 historical_generator.py --days 7 --output data/history.jsonl

    # Then load it into Splunk (see load_to_splunk.py)
    python3 load_to_splunk.py data/history.jsonl \\
        --hec-url http://localhost:8088 --hec-token YOUR-TOKEN

OUTPUT FORMAT
─────────────
HEC-envelope JSON, one event per line:
    {"time": <epoch>, "host": ..., "sourcetype": ..., "index": ..., "event": {...}}
Splunk honors the `time` field, so each event lands at its historical timestamp.

This reuses the world model from synth_generator.py (must be in the same dir).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import random
import secrets
import sys
import time
from pathlib import Path

# Reuse the world model + service catalog from the live generator.
try:
    from synth_generator import EnterpriseWorld, Service, Host
except ImportError:
    sys.exit("historical_generator.py must sit next to synth_generator.py")


# ─── Past incidents to embed ────────────────────────────────────────────────
# Each becomes a burst of errors + an INC record + (later) a resolving deploy.
# These give the Memory agent real history to recall. Times are "days ago".

PAST_INCIDENTS = [
    {
        "days_ago": 5.4,
        "origin": "feature-store-db",
        "affected": ["feature-store", "fraud-scoring", "checkout-api"],
        "short_description": "Checkout 5xx spike — fraud-scoring feature timeouts",
        "priority": "2", "severity": "2",
        "assignment_group": "Payments-SRE",
        "cmdb_ci": "checkout-api",
        "duration_min": 38,
        "resolution_deploy": ("feature-store-db", "v3.11.0", "v3.11.0-hotfix2"),
        "resolution_note": "feature-store-db restart + IO capacity increase restored headroom",
    },
    {
        "days_ago": 3.1,
        "origin": "auth-service",
        "affected": ["auth-service", "api-gateway"],
        "short_description": "Login failures in eu-west-1 — session-store eviction storm",
        "priority": "2", "severity": "3",
        "assignment_group": "Identity-SRE",
        "cmdb_ci": "auth-service",
        "duration_min": 22,
        "resolution_deploy": ("session-store", "v2.4.1", "v2.4.2"),
        "resolution_note": "Raised session-store maxmemory + tuned eviction policy",
    },
    {
        "days_ago": 1.2,
        "origin": "payment-gateway",
        "affected": ["payment-gateway", "payment-orchestrator"],
        "short_description": "Elevated payment decline rate — partner-bank-visa latency",
        "priority": "1", "severity": "1",
        "assignment_group": "Payments-SRE",
        "cmdb_ci": "payment-gateway",
        "duration_min": 51,
        "resolution_deploy": ("payment-gateway", "v5.7.3", "v5.7.4"),
        "resolution_note": "Failed over partner-bank-visa to secondary endpoint; raised circuit-breaker threshold",
    },
]

# Routine past deploys scattered through the week (no incident attached).
ROUTINE_DEPLOYS = [
    ("catalog-api",   "v8.2.0",  "v8.3.0",  6.8),
    ("checkout-api",  "v2.40.9", "v2.41.0", 6.2),
    ("pricing-engine","v3.1.4",  "v3.1.5",  4.9),
    ("checkout-api",  "v2.41.0", "v2.41.2", 4.0),
    ("inventory-service","v1.9.0","v1.9.1", 2.7),
    ("fraud-scoring", "v4.2.0",  "v4.3.0",  2.1),
    ("checkout-api",  "v2.41.2", "v2.41.3", 0.6),
]


class HistoricalGenerator:
    def __init__(self, world: EnterpriseWorld, days: float = 7.0,
                 bucket_seconds: int = 300, seed: int = 7):
        self.world = world
        self.days = days
        self.bucket = bucket_seconds
        self.rng = random.Random(seed)
        self.count = 0
        self.emitted_incidents = 0
        self._buf: list[str] = []

    # ─── Public ──────────────────────────────────────────────────────────────

    def generate(self, out_path: str):
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        now = time.time()
        start = now - self.days * 86400
        n_buckets = int((now - start) / self.bucket)

        sys.stderr.write(
            f"[historical] generating {self.days} days "
            f"({n_buckets:,} × {self.bucket}s buckets)\n")

        # Precompute incident time windows
        incident_windows = self._build_incident_windows(now)

        with open(out_path, "w") as fh:
            self._fh = fh
            for i in range(n_buckets):
                ts = start + i * self.bucket
                load = self._load_factor(ts)
                active = [w for w in incident_windows
                          if w["start"] <= ts < w["end"]]
                self._emit_bucket(ts, load, active)
                if i % 200 == 0:
                    self._flush()
                    pct = 100 * i / n_buckets
                    sys.stderr.write(f"\r[historical] {pct:5.1f}% "
                                      f"· {self.count:,} events")
                    sys.stderr.flush()

            # One-shot records: incidents, resolutions, routine deploys
            for w in incident_windows:
                self._emit_incident_record(w)
                self._emit_resolution(w)
            self.emitted_incidents = len(incident_windows)
            for svc, prev, ver, days_ago in ROUTINE_DEPLOYS:
                if days_ago > self.days:
                    continue
                self._emit_deploy(now - days_ago * 86400, svc, prev, ver,
                                   actor="ci-bot", change_id=self._chg())
            self._flush()

        sys.stderr.write(f"\n[historical] done · {self.count:,} events → {out_path}\n")

    # ─── Bucket emission ──────────────────────────────────────────────────────

    def _emit_bucket(self, ts: float, load: float, active_incidents: list[dict]):
        affected = {s for w in active_incidents for s in w["affected"]}
        origins = {w["origin"] for w in active_incidents}

        # 1. Downsampled metrics — one CPU/MEM sample per service (representative host)
        for svc in self.world.services:
            host = self._representative_host(svc)
            if not host:
                continue
            boosted = svc.name in origins
            degraded = svc.name in affected
            cpu = self._noisy(28 * load) + (40 if boosted else 0)
            mem = self._noisy(55 + 10 * load) + (15 if boosted else 0)
            common = {"ts": ts, "host": host.hostname, "service": svc.name,
                      "region": svc.region.code, "az": host.az, "kind": host.kind}
            self._w("helix:metrics:cpu", "helix_metrics",
                    {**common, "cpu_pct": round(min(cpu, 99.9), 2)})
            self._w("helix:metrics:mem", "helix_metrics",
                    {**common, "mem_pct": round(min(mem, 99.9), 2)})

        # 2. Logs — sparse baseline, error bursts for affected services
        for svc in self.world.services:
            host = self._representative_host(svc)
            if not host:
                continue
            err_rate = 0.001
            if svc.name in affected:
                err_rate = 0.22 if svc.name in origins else 0.12
            # ~6 log samples per service per bucket
            for _ in range(6):
                is_err = self.rng.random() < err_rate
                level = "ERROR" if is_err else self.rng.choices(
                    ["INFO", "DEBUG", "WARN"], weights=[72, 18, 10])[0]
                msg = self._incident_message(svc, active_incidents) if (
                    is_err and svc.name in affected) else self._baseline_msg(level)
                self._w("helix:logs:app", "helix_logs", {
                    "ts": ts + self.rng.uniform(0, self.bucket),
                    "service": svc.name, "host": host.hostname,
                    "region": svc.region.code, "level": level,
                    "trace_id": secrets.token_hex(16),
                    "span_id": secrets.token_hex(12),
                    "message": msg,
                })

        # 3. Trace samples — feed the L1 dependency graph
        for svc in self.world.services:
            if not svc.deps:
                continue
            for _ in range(3):
                downstream = self.rng.choice(svc.deps)
                degraded = downstream in affected
                base = {"data": 35, "core": 80, "api": 45,
                        "edge": 12, "infra": 8}
                ds = next((s for s in self.world.services
                           if s.name == downstream), None)
                p50 = base.get(ds.tier, 50) if ds else 50
                duration = p50 * (1 + abs(self.rng.gauss(0, 0.6)) ** 2)
                if degraded:
                    duration *= self.rng.uniform(8, 16)
                error = self.rng.random() < (0.18 if degraded else 0.001)
                self._w("helix:traces:span", "helix_traces", {
                    "ts": ts + self.rng.uniform(0, self.bucket),
                    "trace_id": secrets.token_hex(16),
                    "span_id": secrets.token_hex(12),
                    "parent_span_id": secrets.token_hex(12),
                    "service": downstream, "parent_service": svc.name,
                    "operation": f"call_{downstream}",
                    "duration_ms": round(duration, 2),
                    "status": "ERROR" if error else "OK",
                    "tags": {"region": svc.region.code},
                })

        # 4. Business KPIs — every other bucket
        if int(ts // self.bucket) % 2 == 0:
            self._emit_business(ts, load, affected)

    # ─── One-shot records ─────────────────────────────────────────────────────

    def _emit_incident_record(self, w: dict):
        self._w("helix:incidents:servicenow", "helix_incidents", {
            "ts": w["start"], "number": w["number"],
            "short_description": w["short_description"],
            "category": "Application", "subcategory": "Availability",
            "priority": w["priority"], "severity": w["severity"],
            "state": "New", "assignment_group": w["assignment_group"],
            "cmdb_ci": w["cmdb_ci"], "u_source": "monitoring",
            "u_confidence": 1.0,
        })

    def _emit_resolution(self, w: dict):
        svc, prev, ver = w["resolution_deploy"]
        # resolving deploy lands near the end of the incident
        deploy_ts = w["end"] - 120
        self._emit_deploy(deploy_ts, svc, prev, ver,
                          actor="sre-oncall", change_id=self._chg())
        # incident resolution record
        self._w("helix:incidents:servicenow", "helix_incidents", {
            "ts": w["end"], "number": w["number"],
            "short_description": w["short_description"],
            "priority": w["priority"], "severity": w["severity"],
            "state": "Resolved",
            "close_code": "Solved (Permanently)",
            "close_notes": w["resolution_note"],
            "assignment_group": w["assignment_group"],
            "cmdb_ci": w["cmdb_ci"],
            "u_resolved_by": "sre-oncall",
            "u_resolution_deploy": f"{svc}@{ver}",
        })

    def _emit_deploy(self, ts: float, svc: str, prev: str, ver: str,
                     actor: str, change_id: str):
        self._w("helix:deploy:event", "helix_deploy", {
            "ts": ts, "service": svc, "version": ver, "previous": prev,
            "rollout": self.rng.choice(["rolling", "canary"]),
            "actor": actor, "pipeline": f"{svc}-prod", "change_id": change_id,
        })

    def _emit_business(self, ts: float, load: float, affected: set):
        baseline = [
            ("checkout_completion_rate", "us-east-2", 0.972),
            ("checkout_completion_rate", "eu-west-1", 0.968),
            ("pos_transactions_per_min", "ap-south-1", 14200),
            ("pos_transactions_per_min", "us-east-2", 21800),
            ("auth_success_rate", "global", 0.994),
        ]
        for metric, region, base in baseline:
            value = base * load if "rate" not in metric else base
            # Degrade KPIs during incidents touching checkout/auth/payment
            if "checkout" in metric and "checkout-api" in affected:
                value = base * self.rng.uniform(0.70, 0.85)
            elif "auth" in metric and "auth-service" in affected:
                value = base * self.rng.uniform(0.88, 0.95)
            elif "pos" in metric and "checkout-api" in affected:
                value = base * self.rng.uniform(0.55, 0.75)
            else:
                value = value * (1 + self.rng.gauss(0, 0.015))
            self._w("helix:metrics:business", "helix_business", {
                "ts": ts, "metric": metric, "region": region,
                "value": round(value, 4), "baseline": base,
            })

    # ─── Helpers ──────────────────────────────────────────────────────────────

    def _build_incident_windows(self, now: float) -> list[dict]:
        windows = []
        for spec in PAST_INCIDENTS:
            # Skip incidents that fall outside the generated history window
            if spec["days_ago"] > self.days:
                continue
            start = now - spec["days_ago"] * 86400
            end = start + spec["duration_min"] * 60
            windows.append({
                **spec, "start": start, "end": end,
                "number": f"INC{self.rng.randint(1_000_000, 9_999_999)}",
            })
        return windows

    def _load_factor(self, ts: float) -> float:
        """Diurnal (24h) × weekly (lower weekends) demand factor, ~0.3..1.1."""
        d = dt.datetime.fromtimestamp(ts)
        hour = d.hour + d.minute / 60.0
        diurnal = 0.55 + 0.45 * math.sin((hour - 14) * math.pi / 12)
        weekly = 0.7 if d.weekday() >= 5 else 1.0          # Sat/Sun lighter
        return max(0.3, diurnal * weekly)

    def _representative_host(self, svc: Service) -> Host | None:
        hosts = [h for h in self.world.hosts if svc.name in (h.runs or [])]
        # stable choice per service so the same host carries the series
        return hosts[hash(svc.name) % len(hosts)] if hosts else None

    def _noisy(self, base: float) -> float:
        return max(0, base + self.rng.gauss(0, base * 0.06))

    def _incident_message(self, svc: Service, active: list[dict]) -> str:
        for w in active:
            if svc.name == w["origin"]:
                return self.rng.choice([
                    f"resource saturation detected on {svc.name}",
                    f"{svc.name} p99 exceeds SLO; throttling",
                    "io wait elevated; queue depth growing",
                ])
            if svc.name in w["affected"]:
                return self.rng.choice([
                    f"downstream {w['origin']} timeout; circuit-breaker engaged",
                    f"deadline exceeded calling {w['origin']}",
                    "returning 503 to upstream; retries exhausted",
                ])
        return "downstream unavailable"

    def _baseline_msg(self, level: str) -> str:
        msgs = {
            "INFO":  ["served request", "request completed", "health check ok"],
            "DEBUG": ["span recorded", "cache hit", "preflight passed"],
            "WARN":  ["retry after backoff", "slow path engaged"],
            "ERROR": ["transient downstream blip", "deadline exceeded"],
        }
        return self.rng.choice(msgs.get(level, ["event"]))

    def _chg(self) -> str:
        return f"CHG{self.rng.randint(100000, 999999):07d}"

    def _w(self, sourcetype: str, index: str, event: dict):
        self._buf.append(json.dumps({
            "time": event["ts"], "host": event.get("host") or "helix-synth",
            "source": "helix-historical", "sourcetype": sourcetype,
            "index": index, "event": event,
        }))
        self.count += 1

    def _flush(self):
        if self._buf:
            self._fh.write("\n".join(self._buf) + "\n")
            self._buf.clear()


def main():
    ap = argparse.ArgumentParser(
        description="TITAN HELIX historical telemetry backfill generator")
    ap.add_argument("--days", type=float, default=7.0,
                    help="How many days of history to generate (default 7)")
    ap.add_argument("--bucket-seconds", type=int, default=300,
                    help="Time granularity per sample (default 300 = 5 min)")
    ap.add_argument("--output", type=str, default="data/history.jsonl",
                    help="Output dump file path")
    ap.add_argument("--seed", type=int, default=7, help="Deterministic seed")
    args = ap.parse_args()

    world = EnterpriseWorld(seed=42)   # same topology seed as live generator
    gen = HistoricalGenerator(world, days=args.days,
                              bucket_seconds=args.bucket_seconds, seed=args.seed)
    gen.generate(args.output)

    # Quick summary
    size_mb = Path(args.output).stat().st_size / 1e6
    sys.stderr.write(
        f"[historical] file size: {size_mb:.1f} MB\n"
        f"[historical] embedded incidents: {gen.emitted_incidents}\n"
        f"[historical] next: python3 load_to_splunk.py {args.output} "
        f"--hec-url http://localhost:8088 --hec-token YOUR-TOKEN\n")


if __name__ == "__main__":
    main()
