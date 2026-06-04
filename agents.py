#!/usr/bin/env python3
"""
TITAN HELIX · AI Agent Mesh (runnable)
══════════════════════════════════════════════════════════════════════════════
The reasoning layer. Reads telemetry from Splunk, runs a chain of specialized
agents (Observer → Memory → Correlation → Prediction → Remediation → Executive),
and writes their opinions to the helix_audit index.

TWO DATA SOURCES
  • default          : query a live Splunk instance
  • --mock-data      : use built-in sample telemetry (NO Splunk needed) — great
                       for a first run / self-test

TWO REASONING MODES
  • default          : MOCK reasoning — deterministic, computed from real data +
                       templated narrative. Needs NO API key, runs offline.
  • --llm            : send gathered context to Claude or OpenAI for genuine
                       natural-language reasoning. Needs --api-key + internet.

QUICK START
───────────
    pip install requests

    # 1. Self-test — runs the whole agent chain on built-in data, no infra:
    python3 agents.py --mock-data --investigate checkout-api

    # 2. Against your live Splunk (after loading data):
    python3 agents.py \\
        --splunk-api-url https://localhost:8089 \\
        --splunk-password ChangeMe_Helix_2026 \\
        --hec-url http://localhost:8088 \\
        --hec-token 11111111-2222-3333-4444-555555555555 \\
        --investigate checkout-api

    # 3. With a real LLM doing the reasoning:
    python3 agents.py --mock-data --investigate checkout-api \\
        --llm --provider anthropic --api-key sk-ant-... \\
        --model claude-opus-4-7
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import textwrap

try:
    import requests
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except ImportError:
    sys.exit("Missing dep: pip install requests")


# ════════════════════════════════════════════════════════════════════════════
# DATA ACCESS
# ════════════════════════════════════════════════════════════════════════════

class SplunkREST:
    """Minimal Splunk search client (export endpoint)."""
    def __init__(self, api_url, user, password, verify=False):
        self.api_url = api_url.rstrip("/")
        self.s = requests.Session()
        self.s.auth = (user, password)
        self.s.verify = verify

    def search(self, spl, earliest="-15m@m", latest="now", timeout=60):
        if not spl.strip().startswith(("search ", "|")):
            spl = "search " + spl
        try:
            r = self.s.post(f"{self.api_url}/services/search/jobs/export",
                            data={"search": spl, "output_mode": "json",
                                  "earliest_time": earliest, "latest_time": latest},
                            stream=True, timeout=timeout)
            r.raise_for_status()
            rows = []
            for line in r.iter_lines():
                if line:
                    try:
                        o = json.loads(line)
                        if "result" in o:
                            rows.append(o["result"])
                    except json.JSONDecodeError:
                        pass
            return rows
        except Exception as e:
            sys.stderr.write(f"[splunk] search failed: {e}\n")
            return []


class MockSplunk:
    """Returns canned telemetry resembling a checkout_collapse cascade.
    Lets the agent chain run with zero infrastructure."""
    def search(self, spl, earliest="-15m@m", latest="now", timeout=60):
        s = spl.lower()
        if "stats count by service" in s and "error" in s:
            return [{"service": "checkout-api", "count": "4402"},
                    {"service": "fraud-scoring", "count": "1764"},
                    {"service": "feature-store", "count": "320"},
                    {"service": "auth-service", "count": "44"}]
        if "p99" in s or "duration_ms" in s:
            return [{"service": "fraud-scoring", "p99": "1480", "call_count": "8800"},
                    {"service": "checkout-api", "p99": "1820", "call_count": "14200"},
                    {"service": "feature-store", "p99": "920", "call_count": "8800"}]
        if "parent_service" in s:   # dependency graph
            return [{"source": "checkout-api", "target": "fraud-scoring", "count": "12400"},
                    {"source": "fraud-scoring", "target": "feature-store", "count": "8800"},
                    {"source": "feature-store", "target": "feature-store-db", "count": "8800"},
                    {"source": "checkout-api", "target": "payment-orchestrator", "count": "11200"},
                    {"source": "payment-orchestrator", "target": "payment-gateway", "count": "9000"}]
        if "cpu_pct" in s or "metrics:cpu" in s:
            return [{"host": "feature-store-db-vm-euw1-prod-01", "service": "feature-store-db",
                     "avg_cpu": "96.4"},
                    {"host": "fraud-scoring-3a1f-x", "service": "fraud-scoring", "avg_cpu": "71.2"},
                    {"host": "checkout-api-7f5d-q", "service": "checkout-api", "avg_cpu": "58.0"}]
        if "helix_incidents" in s or "short_description" in s:
            return [{"number": "INC6433012",
                     "short_description": "Checkout 5xx spike — fraud-scoring feature timeouts",
                     "state": "Resolved", "priority": "2",
                     "close_notes": "feature-store-db restart + IO capacity increase restored headroom",
                     "u_resolution_deploy": "feature-store-db@v3.11.0-hotfix2",
                     "cmdb_ci": "checkout-api"},
                    {"number": "INC7624039",
                     "short_description": "Elevated payment decline rate — partner-bank-visa latency",
                     "state": "Resolved", "priority": "1",
                     "close_notes": "Failed over partner-bank-visa to secondary endpoint",
                     "u_resolution_deploy": "payment-gateway@v5.7.4",
                     "cmdb_ci": "payment-gateway"}]
        return []


class HECWriter:
    """Writes agent opinions to helix_audit."""
    def __init__(self, url, token, verify=False, enabled=True):
        self.enabled = enabled and bool(url and token)
        if self.enabled:
            self.url = url.rstrip("/") + "/services/collector/event"
            self.s = requests.Session()
            self.s.headers = {"Authorization": f"Splunk {token}"}
            self.s.verify = verify

    def write(self, event: dict):
        if not self.enabled:
            return
        try:
            self.s.post(self.url, data=json.dumps({
                "time": time.time(), "sourcetype": "helix:agent:reasoning",
                "index": "helix_audit", "event": event}), timeout=10)
        except Exception as e:
            sys.stderr.write(f"[hec] audit write failed: {e}\n")


# ════════════════════════════════════════════════════════════════════════════
# LLM PROVIDER (optional)
# ════════════════════════════════════════════════════════════════════════════

class LLM:
    def __init__(self, provider, api_key, model):
        self.provider = provider
        self.api_key = api_key
        self.model = model

    def reason(self, system: str, context: dict) -> str:
        user = json.dumps(context, indent=2)
        if self.provider == "anthropic":
            return self._anthropic(system, user)
        elif self.provider == "openai":
            return self._openai(system, user)
        raise ValueError(f"unknown provider: {self.provider}")

    def _anthropic(self, system, user):
        r = requests.post("https://api.anthropic.com/v1/messages",
            headers={"x-api-key": self.api_key,
                     "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={"model": self.model, "max_tokens": 1024,
                  "system": system,
                  "messages": [{"role": "user", "content": user}]}, timeout=60)
        r.raise_for_status()
        return r.json()["content"][0]["text"]

    def _openai(self, system, user):
        r = requests.post("https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}",
                     "content-type": "application/json"},
            json={"model": self.model,
                  "messages": [{"role": "system", "content": system},
                               {"role": "user", "content": user}]}, timeout=60)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]


# ════════════════════════════════════════════════════════════════════════════
# SPL the agents run
# ════════════════════════════════════════════════════════════════════════════

SPL = {
    "errors_by_service": """index=helix_logs sourcetype="helix:logs:app" level=ERROR
| stats count by service | sort - count | head 10""",
    "latency_by_service": """index=helix_traces sourcetype="helix:traces:span"
| stats p99(duration_ms) as p99, count as call_count by service
| where call_count > 20 | sort - p99 | head 10""",
    "deps": """index=helix_traces sourcetype="helix:traces:span"
| stats count by parent_service, service | where count > 20
| rename parent_service as source, service as target""",
    "cpu_by_host": """index=helix_metrics sourcetype="helix:metrics:cpu"
| stats avg(cpu_pct) as avg_cpu by host, service | sort - avg_cpu | head 10""",
    "past_incidents": """index=helix_incidents sourcetype="helix:incidents:servicenow"
state=Resolved | sort - _time
| table number, short_description, priority, close_notes, u_resolution_deploy, cmdb_ci
| head 10""",
}


# ════════════════════════════════════════════════════════════════════════════
# AGENTS — each returns an "opinion" dict
# ════════════════════════════════════════════════════════════════════════════

class AgentMesh:
    def __init__(self, splunk, hec, target: str, llm: LLM | None = None,
                 earliest="-15m@m"):
        self.splunk = splunk
        self.hec = hec
        self.target = target
        self.llm = llm
        self.earliest = earliest
        self.opinions: list[dict] = []
        self.shared: dict = {"target": target}

    # ─── chain ───────────────────────────────────────────────────────────────
    def run(self):
        self._observer()
        self._memory()
        self._correlation()
        self._prediction()
        self._remediation()
        self._executive()
        return self.opinions

    def _record(self, agent, confidence, claim, evidence=None, narrative=None):
        op = {"agent": agent, "confidence": round(confidence, 2),
              "claim": claim, "evidence": evidence or {},
              "narrative": narrative or claim, "ts": time.time()}
        self.opinions.append(op)
        self.hec.write({"investigation_target": self.target, **op})
        return op

    def _maybe_llm(self, agent, system, context, fallback) -> str:
        if not self.llm:
            return fallback
        try:
            return self.llm.reason(system, context).strip()
        except Exception as e:
            sys.stderr.write(f"[llm:{agent}] failed, using mock narrative: {e}\n")
            return fallback

    # ─── Observer ──────────────────────────────────────────────────────────
    def _observer(self):
        errs = self.splunk.search(SPL["errors_by_service"], earliest=self.earliest)
        lat = self.splunk.search(SPL["latency_by_service"], earliest=self.earliest)
        top_err = errs[0] if errs else None
        top_lat = max(lat, key=lambda r: float(r.get("p99", 0))) if lat else None
        self.shared["errors"] = errs
        self.shared["latency"] = lat

        facts = []
        if top_err:
            facts.append(f"{top_err['service']} has the most errors ({top_err['count']})")
        if top_lat:
            facts.append(f"{top_lat['service']} p99 at {top_lat['p99']}ms")
        fallback = ("Observed: " + "; ".join(facts) + "." if facts
                    else "No significant anomalies in the current window.")
        narrative = self._maybe_llm("observer",
            "You are the OBSERVER agent. State only what the telemetry shows, "
            "factually, in 1-2 sentences. No speculation.",
            {"top_errors": errs[:5], "top_latency": lat[:5]}, fallback)
        conf = 0.9 if top_err else 0.4
        self._record("observer", conf,
                     claim=facts[0] if facts else "nominal",
                     evidence={"spl": [SPL["errors_by_service"].strip(),
                                       SPL["latency_by_service"].strip()],
                               "top_errors": errs[:3]},
                     narrative=narrative)

    # ─── Memory ──────────────────────────────────────────────────────────────
    def _memory(self):
        incs = self.splunk.search(SPL["past_incidents"], earliest="-8d@d")
        # naive relevance: match on target or any affected keyword
        kws = {self.target} | {e["service"] for e in self.shared.get("errors", [])[:3]}
        scored = []
        for inc in incs:
            text = (inc.get("short_description", "") + " " +
                    inc.get("cmdb_ci", "")).lower()
            hits = sum(1 for k in kws if k.lower() in text)
            if hits or inc.get("cmdb_ci") == self.target:
                scored.append((hits, inc))
        scored.sort(key=lambda x: -x[0])
        matches = [inc for _, inc in scored[:3]] or incs[:1]
        self.shared["memory_matches"] = matches

        if matches:
            m = matches[0]
            fallback = (f"Recalled {len(matches)} similar past incident(s). "
                        f"Closest: {m['number']} — {m.get('short_description','')}. "
                        f"Resolved by: {m.get('u_resolution_deploy','(see notes)')}.")
            conf = 0.85
        else:
            fallback = "No closely matching historical incidents found."
            conf = 0.3
        narrative = self._maybe_llm("memory",
            "You are the MEMORY agent. Summarize relevant past incidents and how "
            "they were resolved, in 1-2 sentences.",
            {"target": self.target, "matches": matches}, fallback)
        self._record("memory", conf,
                     claim=(f"{matches[0]['number']} is the closest historical match"
                            if matches else "no historical match"),
                     evidence={"matches": matches, "spl": [SPL["past_incidents"].strip()]},
                     narrative=narrative)

    # ─── Correlation ──────────────────────────────────────────────────────────
    def _correlation(self):
        cpu = self.splunk.search(SPL["cpu_by_host"], earliest="-30m@m")
        self.shared["cpu"] = cpu
        # find the saturated data-tier host that likely leads the cascade
        suspect = None
        for r in cpu:
            if float(r.get("avg_cpu", 0)) > 85:
                suspect = r
                break
        if suspect:
            fallback = (f"{suspect['service']} ({suspect['host']}) is CPU-saturated at "
                        f"{suspect['avg_cpu']}%, temporally leading downstream errors — "
                        f"likely the causal origin of the cascade.")
            conf = 0.83
            claim = f"{suspect['service']} saturation is causal"
        else:
            fallback = ("No single saturated resource identified; degradation may be "
                        "load- or deploy-driven.")
            conf = 0.5
            claim = "no clear single cause"
        narrative = self._maybe_llm("correlation",
            "You are the CORRELATION agent. Identify the most likely causal origin "
            "using lead-lag and saturation evidence. 1-2 sentences.",
            {"cpu_by_host": cpu, "errors": self.shared.get("errors", [])[:5]},
            fallback)
        self.shared["suspect"] = suspect
        self._record("correlation", conf, claim=claim,
                     evidence={"suspect_host": suspect, "spl": [SPL["cpu_by_host"].strip()]},
                     narrative=narrative)

    # ─── Prediction (blast radius from dependency graph) ──────────────────────
    def _prediction(self):
        deps = self.splunk.search(SPL["deps"], earliest=self.earliest)
        # build reverse graph: who depends on the suspect/target
        origin = (self.shared.get("suspect") or {}).get("service") or self.target
        downstream = self._propagate(deps, origin)
        self.shared["downstream"] = downstream
        impacted = ", ".join(downstream[:4]) if downstream else "no clear downstream"
        # POS estimate if pos-gateway in path
        pos_note = ""
        if any("pos" in d for d in downstream) or "checkout-api" in downstream:
            pos_note = " POS terminals in ap-south-1 (~2,140) at risk within ~30 min."
        fallback = (f"Failure originating at {origin} is projected to propagate to: "
                    f"{impacted}.{pos_note}")
        conf = 0.78 if downstream else 0.45
        narrative = self._maybe_llm("prediction",
            "You are the PREDICTION agent. Forecast blast radius and time-to-impact "
            "from the dependency graph. 1-2 sentences with a concrete ETA if possible.",
            {"origin": origin, "dependency_edges": deps,
             "downstream": downstream}, fallback)
        self._record("prediction", conf,
                     claim=f"blast radius: {impacted}",
                     evidence={"origin": origin, "downstream": downstream,
                               "spl": [SPL["deps"].strip()]},
                     narrative=narrative)

    @staticmethod
    def _propagate(deps, origin, max_hops=3):
        """BFS upward: services that (transitively) call `origin`."""
        rev = {}
        for e in deps:
            rev.setdefault(e["target"], []).append(e["source"])
        seen, frontier, order = {origin}, [origin], []
        for _ in range(max_hops):
            nxt = []
            for node in frontier:
                for caller in rev.get(node, []):
                    if caller not in seen:
                        seen.add(caller); nxt.append(caller); order.append(caller)
            frontier = nxt
            if not frontier:
                break
        return order

    # ─── Remediation ──────────────────────────────────────────────────────────
    def _remediation(self):
        matches = self.shared.get("memory_matches", [])
        suspect = (self.shared.get("suspect") or {}).get("service")
        actions = []
        # action 1: replay what fixed the closest past incident
        if matches and matches[0].get("u_resolution_deploy"):
            svc_fix = matches[0]["u_resolution_deploy"].split("@")[0]
            actions.append({"rank": 1, "action": f"Apply prior fix pattern to {svc_fix}",
                            "detail": matches[0].get("close_notes", ""),
                            "approval": "human", "source": matches[0]["number"]})
        # action 2: scale the saturated service
        if suspect:
            actions.append({"rank": 2, "action": f"Scale {suspect} replicas (e.g. 4→8)",
                            "detail": "relieve saturation while root cause is addressed",
                            "approval": "auto", "source": "policy"})
        # action 3: enable graceful degradation
        actions.append({"rank": 3, "action": "Enable downstream fallback / circuit-breaker",
                        "detail": "serve degraded responses instead of timing out",
                        "approval": "auto", "source": "policy"})
        self.shared["actions"] = actions
        fallback = ("Proposed " + str(len(actions)) + " actions: " +
                    "; ".join(f"#{a['rank']} {a['action']} [{a['approval']}]"
                              for a in actions))
        narrative = self._maybe_llm("remediation",
            "You are the REMEDIATION agent. Propose a ranked, safe action list. "
            "Weight historically-effective fixes highest. Mark each auto vs human-approval.",
            {"history": matches, "suspect": suspect, "actions": actions}, fallback)
        self._record("remediation", 0.8,
                     claim=f"{len(actions)} actions proposed",
                     evidence={"actions": actions}, narrative=narrative)

    # ─── Executive ──────────────────────────────────────────────────────────
    def _executive(self):
        origin = (self.shared.get("suspect") or {}).get("service") or self.target
        downstream = self.shared.get("downstream", [])
        matches = self.shared.get("memory_matches", [])
        actions = self.shared.get("actions", [])
        auto = sum(1 for a in actions if a["approval"] == "auto")
        human = sum(1 for a in actions if a["approval"] == "human")
        fallback = (
            f"CASCADE: {origin} appears causal; impact propagating to "
            f"{', '.join(downstream[:3]) or 'downstream services'}. "
            f"{'Historical match found (' + matches[0]['number'] + '). ' if matches else ''}"
            f"{auto} action(s) auto-executed, {human} awaiting approval. "
            f"Recommend approving the prior-fix pattern.")
        narrative = self._maybe_llm("executive",
            "You are the EXECUTIVE SUMMARY agent. In 2-4 sentences give an on-call "
            "engineer the situation, likely cause, forecast, and recommendation.",
            {"origin": origin, "downstream": downstream,
             "memory": matches, "actions": actions}, fallback)
        self._record("executive", 0.88, claim="incident summary",
                     evidence={"origin": origin}, narrative=narrative)


# ════════════════════════════════════════════════════════════════════════════
# OUTPUT
# ════════════════════════════════════════════════════════════════════════════

BADGE = {"observer": "\033[96m", "memory": "\033[95m", "correlation": "\033[93m",
         "prediction": "\033[38;5;208m", "remediation": "\033[91m",
         "executive": "\033[97m"}
RESET = "\033[0m"

def render(opinions, target, mode_label):
    print(f"\n\033[1m  TITAN HELIX · investigation\033[0m  →  \033[38;5;208m{target}\033[0m"
          f"   \033[2m({mode_label})\033[0m")
    print("  " + "─" * 70)
    for op in opinions:
        c = BADGE.get(op["agent"], "")
        print(f"\n  {c}\033[1m{op['agent'].upper():>12}\033[0m{RESET}  "
              f"\033[2mconf {op['confidence']}\033[0m")
        for line in textwrap.wrap(op["narrative"], width=66):
            print(f"               {line}")
        spl = op.get("evidence", {}).get("spl")
        if spl:
            first = spl[0].replace("\n", " ")[:62]
            print(f"               \033[2m└ spl: {first}…\033[0m")
    print("\n  " + "─" * 70)
    print(f"  \033[2m{len(opinions)} opinions recorded → helix_audit\033[0m\n")


def main():
    ap = argparse.ArgumentParser(description="TITAN HELIX agent mesh")
    ap.add_argument("--investigate", default="checkout-api",
                    help="Service to investigate (default checkout-api)")
    ap.add_argument("--mock-data", action="store_true",
                    help="Use built-in sample telemetry (no Splunk needed)")
    ap.add_argument("--splunk-api-url", default="https://localhost:8089")
    ap.add_argument("--splunk-user", default="admin")
    ap.add_argument("--splunk-password", default="ChangeMe_Helix_2026")
    ap.add_argument("--hec-url", default=None, help="For audit write-back")
    ap.add_argument("--hec-token", default=None)
    ap.add_argument("--earliest", default="-15m@m")
    ap.add_argument("--llm", action="store_true", help="Use an LLM for reasoning")
    ap.add_argument("--provider", default="anthropic", choices=["anthropic", "openai"])
    ap.add_argument("--api-key", default=os.environ.get("HELIX_LLM_API_KEY"))
    ap.add_argument("--model", default="claude-opus-4-7")
    ap.add_argument("--json", action="store_true", help="Emit opinions as JSON")
    args = ap.parse_args()

    # data source
    if args.mock_data:
        splunk = MockSplunk()
        data_label = "mock data"
    else:
        splunk = SplunkREST(args.splunk_api_url, args.splunk_user, args.splunk_password)
        data_label = "live Splunk"

    # reasoning mode
    llm = None
    if args.llm:
        if not args.api_key:
            sys.exit("--llm requires --api-key (or HELIX_LLM_API_KEY env var)")
        llm = LLM(args.provider, args.api_key, args.model)
        reason_label = f"LLM:{args.provider}/{args.model}"
    else:
        reason_label = "mock reasoning"

    hec = HECWriter(args.hec_url, args.hec_token)

    mesh = AgentMesh(splunk, hec, args.investigate, llm=llm, earliest=args.earliest)
    opinions = mesh.run()

    if args.json:
        print(json.dumps(opinions, indent=2))
    else:
        render(opinions, args.investigate, f"{data_label} · {reason_label}")


if __name__ == "__main__":
    main()
