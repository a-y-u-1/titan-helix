# TITAN HELIX
## Autonomous AI Operational Intelligence Mesh

> **Architecture Document · Implementation Blueprint · Product Strategy · Hackathon Execution Plan**
> Status: v1.0 — Foundational Design
> Audience: Engineering team, hackathon judges, product strategy review
> Authoring stance: Principal Product Architect / Distinguished AI Systems Engineer

---

## 0. Executive Summary

**TITAN HELIX** is an AI-native operational intelligence platform. It is not a dashboard. It is an autonomous operational nervous system that:

1. **Generates** continuous, production-realistic synthetic enterprise telemetry across cloud, Kubernetes, POS, payments, auth, CDN, and security planes.
2. **Ingests** all of it into **Splunk Enterprise** as the durable telemetry backbone.
3. **Reasons** over the live operational state using a **multi-agent AI mesh** (Observer, Correlation, Prediction, Security, Topology, Memory, Remediation, Governance, Executive Summary).
4. **Discovers and renders** a **live, AI-inferred operational topology graph** with confidence-weighted edges — not a static CMDB diagram.
5. **Predicts** failure propagation: *"Payment outage projected in 34 minutes; blast radius covers checkout-api, fraud-scoring, partner-bank-gateway, and 11,400 active POS terminals across APAC-South."*
6. **Acts** through MCP-compatible tool invocation — autonomous SPL generation, runbook execution, and AI-safe remediation orchestration.

The hero metaphor: **a neural network for your enterprise.** Telemetry is the signal. Agents are the neurons. The graph is the cortex. The simulator is the dream-state where the system rehearses futures before they happen.

This document goes to **system-design-review depth**. Read it end-to-end before writing a single line of code.

---

## 1. Product Vision & Differentiation

### 1.1 The thesis

Splunk, Datadog, New Relic, and Dynatrace are all *passive correlation engines* dressed in dashboards. They assume a human asks the question. TITAN HELIX inverts the model: **the platform asks its own questions**, generates its own SPL, debates its own conclusions, and proposes its own actions. Humans approve outcomes, not investigate symptoms.

### 1.2 Differentiators

| Capability | Splunk ITSI | Datadog | New Relic | **TITAN HELIX** |
|---|---|---|---|---|
| Static service maps | ✅ | ✅ | ✅ | ❌ (replaced) |
| AI-inferred topology with confidence edges | ❌ | partial | ❌ | ✅ core |
| Multi-agent reasoning (debate, dissent, consensus) | ❌ | ❌ | ❌ | ✅ |
| Autonomous SPL generation | ❌ | n/a | n/a | ✅ |
| Future-state blast radius simulation | partial | ❌ | ❌ | ✅ |
| MCP-native tool orchestration | ❌ | ❌ | ❌ | ✅ |
| Operational memory (RAG over past incidents) | partial | ❌ | partial | ✅ first-class |
| Synthetic chaos rehearsal | ❌ | ❌ | ❌ | ✅ |

### 1.3 Narrative pitch (90 seconds)

> Every modern enterprise sits on a graph it cannot see. Services depend on services that depend on services that nobody documented since 2019. When something breaks, three war rooms spin up, six tools get queried, and the answer arrives 47 minutes later. TITAN HELIX rebuilds that graph every 30 seconds from raw telemetry, runs a multi-agent debate over what's actually wrong, simulates where the failure is heading next, and hands the on-call engineer a ranked action list with an SPL trail showing exactly why. It uses Splunk as its long-term memory and MCP as its nervous system. It's what operational intelligence looks like when the AI does the work.

---

## 2. System Architecture — Macro View

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                            TITAN HELIX CONTROL PLANE                          │
└──────────────────────────────────────────────────────────────────────────────┘
                                      │
   ┌──────────────────┬───────────────┼──────────────────┬───────────────────┐
   │                  │               │                  │                   │
┌──▼──────────┐  ┌────▼─────┐  ┌──────▼──────┐  ┌────────▼────────┐  ┌──────▼──────┐
│  SYNTHETIC  │  │  SPLUNK  │  │  AI AGENT    │  │  GRAPH          │  │  FRONTEND   │
│  ENTERPRISE │─▶│  HEC +   │◀─│  MESH        │─▶│  INTELLIGENCE   │─▶│  COMMAND    │
│  GENERATOR  │  │  INDEX   │  │ (LangGraph)  │  │  ENGINE         │  │  CENTER     │
└─────────────┘  └─────┬────┘  └──────┬───────┘  └────────┬────────┘  └──────▲──────┘
   (faker++         │SPL│           │MCP│              │NetworkX│             │WS│
    scenarios)     └────┘           └───┘              └────────┘             └──┘
                       │                                    │                   │
                       │            ┌───────────────────────┼───────────────────┘
                       │            │                       │
                  ┌────▼────────────▼───┐         ┌─────────▼────────┐
                  │  MCP TOOL REGISTRY  │         │  EVENT BUS       │
                  │  (Splunk · K8s ·    │◀───────▶│  (Redis Streams) │
                  │   ServiceNow · AWS) │         └──────────────────┘
                  └─────────────────────┘
```

### 2.1 Layer responsibilities

- **L1 — Synthesis Layer:** generates realistic telemetry, fault scenarios, deployment events.
- **L2 — Ingestion Layer:** HEC into Splunk; raw events also land in Redis Streams for hot-path agent reads.
- **L3 — Reasoning Layer:** the agent mesh. Reads Splunk via MCP, writes back inferences, opinions, and actions.
- **L4 — Intelligence Layer:** graph engine, blast-radius simulator, memory RAG.
- **L5 — Experience Layer:** React command center, WebSocket streaming, cinematic UX.

### 2.2 Why this split matters

Each layer is **replaceable**. Drop the synthetic generator, point at production HEC, the rest works. Swap Splunk for OTel + ClickHouse, only L2 changes. Replace OpenAI with Claude, only the agent adapter changes. This is the difference between a hackathon demo and a product.

---

## 3. Monorepo Folder Structure

```
titan-helix/
├── README.md
├── docker-compose.yml                    # Splunk + Redis + backend + frontend + agents
├── .env.example
├── Makefile                              # `make seed`, `make demo`, `make storm`
│
├── packages/
│   ├── core/                             # shared types, schemas, constants
│   │   ├── pyproject.toml
│   │   └── src/helix_core/
│   │       ├── schemas/                  # pydantic models: Telemetry, GraphNode, Incident
│   │       ├── events.py                 # canonical event envelope
│   │       ├── topics.py                 # Redis stream / pubsub topic names
│   │       └── config.py                 # pydantic-settings, env-driven
│   │
│   ├── synth/                            # MODULE 1: Synthetic Enterprise Generator
│   │   ├── pyproject.toml
│   │   └── src/helix_synth/
│   │       ├── world/                    # enterprise world model
│   │       │   ├── topology.py           # generates the "true" hidden graph
│   │       │   ├── entities.py           # hosts, pods, VMs, POS, services
│   │       │   ├── regions.py            # cloud regions, AZs, DCs
│   │       │   └── catalog.py            # service catalog, business units
│   │       ├── generators/
│   │       │   ├── metrics.py            # infra + container + business KPIs
│   │       │   ├── logs.py               # application logs with realistic noise
│   │       │   ├── traces.py             # W3C trace context, spans
│   │       │   ├── incidents.py          # ServiceNow-shaped tickets
│   │       │   ├── deployments.py        # CI/CD events
│   │       │   ├── auth.py               # SSO, MFA, anomalies
│   │       │   └── security.py           # IDS, DLP, suspicious patterns
│   │       ├── scenarios/                # deterministic chaos
│   │       │   ├── base.py               # Scenario abstract class
│   │       │   ├── checkout_collapse.py
│   │       │   ├── dns_brownout.py
│   │       │   ├── pos_region_isolation.py
│   │       │   ├── cert_expiry.py
│   │       │   └── noisy_neighbor.py
│   │       ├── orchestrator.py           # scenario scheduler, time dilation
│   │       ├── hec_sink.py               # Splunk HEC writer w/ batching, backpressure
│   │       └── cli.py                    # `helix-synth run --scenario=checkout_collapse`
│   │
│   ├── splunk/                           # MODULE 2: Splunk Integration Layer
│   │   ├── pyproject.toml
│   │   └── src/helix_splunk/
│   │       ├── hec.py                    # async HEC client
│   │       ├── spl/
│   │       │   ├── library.py            # canonical SPL templates
│   │       │   ├── generator.py          # AI-generated SPL with safety lint
│   │       │   └── validator.py          # AST-level SPL validation
│   │       ├── search.py                 # search/jobs sync + async wrappers
│   │       ├── kvstore.py                # KV store: graph snapshots, memory
│   │       └── sourcetypes.py            # sourcetype definitions
│   │
│   ├── agents/                           # MODULE 3: AI Agent Mesh
│   │   ├── pyproject.toml
│   │   └── src/helix_agents/
│   │       ├── runtime/
│   │       │   ├── graph.py              # LangGraph state machine
│   │       │   ├── state.py              # shared MeshState TypedDict
│   │       │   ├── router.py             # supervisor routing
│   │       │   └── memory.py             # episodic + semantic memory
│   │       ├── agents/
│   │       │   ├── base.py               # Agent ABC, contract
│   │       │   ├── observer.py
│   │       │   ├── correlation.py
│   │       │   ├── prediction.py
│   │       │   ├── security.py
│   │       │   ├── topology.py
│   │       │   ├── remediation.py
│   │       │   ├── governance.py
│   │       │   ├── memory_agent.py
│   │       │   └── executive.py
│   │       ├── llm/
│   │       │   ├── provider.py           # ProviderABC; OpenAI, Anthropic adapters
│   │       │   └── prompts/              # prompts as jinja2 templates
│   │       └── debate.py                 # multi-agent debate protocol
│   │
│   ├── mcp/                              # MODULE 9: MCP Integration
│   │   ├── pyproject.toml
│   │   └── src/helix_mcp/
│   │       ├── server.py                 # exposes Splunk + graph as MCP server
│   │       ├── client.py                 # MCP client used by agents
│   │       ├── tools/                    # individual MCP tools
│   │       │   ├── splunk_search.py
│   │       │   ├── splunk_index_stats.py
│   │       │   ├── graph_query.py
│   │       │   ├── blast_radius_sim.py
│   │       │   ├── k8s_describe.py       # mocked but realistic
│   │       │   ├── servicenow_create.py  # mocked ITSM
│   │       │   └── runbook_execute.py
│   │       └── registry.py               # discovery, capability negotiation
│   │
│   ├── graph/                            # MODULE 4: Operational Graph Engine
│   │   ├── pyproject.toml
│   │   └── src/helix_graph/
│   │       ├── store.py                  # NetworkX in-process + Redis snapshots
│   │       ├── inference.py              # AI-driven edge inference
│   │       ├── confidence.py             # edge confidence scoring
│   │       ├── temporal.py               # time-windowed graph snapshots
│   │       ├── propagation.py            # blast-radius BFS w/ decay
│   │       ├── enrichment.py             # MCP tool enrichment
│   │       └── exporters.py              # react-flow JSON, GraphML, Cytoscape
│   │
│   └── api/                              # MODULE 6: Backend
│       ├── pyproject.toml
│       └── src/helix_api/
│           ├── main.py                   # FastAPI app
│           ├── routes/
│           │   ├── telemetry.py
│           │   ├── graph.py
│           │   ├── agents.py
│           │   ├── incidents.py
│           │   ├── simulate.py
│           │   └── memory.py
│           ├── ws/
│           │   ├── manager.py            # connection manager, channel pubsub
│           │   ├── reasoning.py          # streams agent token-by-token
│           │   └── graph_stream.py       # streams graph deltas
│           ├── services/                 # composition layer
│           └── deps.py                   # FastAPI dependency injection
│
├── apps/
│   └── web/                              # MODULE 5: Frontend
│       ├── package.json
│       ├── vite.config.ts
│       └── src/
│           ├── main.tsx
│           ├── app/
│           │   ├── routes.tsx
│           │   └── theme.ts              # editorial-terminal theme
│           ├── features/
│           │   ├── command-center/       # main hero view
│           │   ├── mesh-graph/           # React Flow canvas
│           │   ├── agent-stream/         # live agent debate
│           │   ├── timeline/             # operational replay
│           │   ├── simulate/             # future-state mode
│           │   └── memory/               # incident RAG search
│           ├── lib/
│           │   ├── ws.ts                 # typed WS client
│           │   ├── api.ts                # typed REST client
│           │   └── store/                # zustand slices
│           └── components/
│               └── primitives/           # buttons, cards, tokens
│
├── infra/
│   ├── splunk/
│   │   ├── default/                      # indexes.conf, props.conf, transforms.conf
│   │   ├── dashboards/                   # bootstrap dashboards
│   │   └── savedsearches.conf
│   ├── grafana/                          # optional infra dashboards
│   └── compose/
│
├── scenarios/                            # YAML-defined chaos scenarios
│   ├── checkout_collapse.yaml
│   ├── dns_brownout.yaml
│   └── cert_expiry.yaml
│
└── docs/
    ├── ARCHITECTURE.md
    ├── AGENTS.md
    ├── GRAPH.md
    ├── MCP.md
    └── DEMO_SCRIPT.md
```

**Design intent of this layout:**
- `packages/` is Python-side, every package independently installable. This is a *monorepo of libraries*, not a monolith. Each module has its own `pyproject.toml` so a future productization can pull `helix_agents` into a different runtime.
- `apps/` houses runnable surfaces; today just `web`. Tomorrow: `cli`, `slackbot`, `mobile`.
- `scenarios/` is declarative — non-engineers can author chaos.
- `infra/splunk/default/` ships as a Splunk app so the demo is one `docker-compose up`.

---

## 4. Module 1 — Synthetic Enterprise Generator

This is the foundation. If telemetry feels fake, the entire platform feels fake. We don't generate random data; we **simulate an enterprise.**

### 4.1 The world model

Before generating a single event, the generator builds a **hidden ground-truth graph** of an enterprise. The AI agents must *rediscover* this graph from telemetry alone — that's the demo's emotional payoff.

```python
# packages/synth/src/helix_synth/world/topology.py
from __future__ import annotations
import random
from dataclasses import dataclass, field
from typing import Literal

@dataclass(frozen=True)
class Region:
    code: str          # "us-east-2", "ap-south-1"
    cloud: Literal["aws", "azure", "gcp", "on-prem"]
    azs: tuple[str, ...]

@dataclass
class Service:
    name: str
    tier: Literal["edge", "api", "core", "data", "infra"]
    runtime: Literal["k8s", "vm", "lambda", "fargate"]
    region: Region
    replicas: int
    deps: list[str] = field(default_factory=list)   # downstream service names
    business_unit: str = "platform"
    criticality: int = 3                             # 1=mission-critical, 5=batch

@dataclass
class Host:
    hostname: str
    kind: Literal["ec2", "vm", "pod", "pos", "edge", "cdn-node"]
    region: Region
    az: str
    runs: list[str] = field(default_factory=list)    # service names

class EnterpriseWorld:
    """Generates and owns the hidden ground-truth topology."""

    def __init__(self, seed: int = 42):
        self.rng = random.Random(seed)
        self.regions = self._build_regions()
        self.services = self._build_services()
        self.hosts = self._build_hosts()
        self.deps = self._wire_dependencies()

    def _build_regions(self) -> list[Region]:
        return [
            Region("us-east-2", "aws", ("use2-az1", "use2-az2", "use2-az3")),
            Region("us-west-2", "aws", ("usw2-az1", "usw2-az2")),
            Region("eu-west-1", "aws", ("euw1-az1", "euw1-az2", "euw1-az3")),
            Region("ap-south-1", "aws", ("aps1-az1", "aps1-az2")),
            Region("ap-southeast-1", "aws", ("apse1-az1", "apse1-az2")),
        ]

    def _build_services(self) -> list[Service]:
        # An opinionated retail-payments-platform topology
        catalog = [
            # Edge tier
            ("cdn-edge",        "edge", "lambda",  ["waf"]),
            ("waf",             "edge", "lambda",  ["api-gateway"]),
            ("api-gateway",     "edge", "k8s",     ["auth-service", "checkout-api", "catalog-api"]),
            # Identity
            ("auth-service",    "api",  "k8s",     ["session-store", "user-db", "mfa-broker"]),
            ("mfa-broker",      "api",  "k8s",     ["partner-sms", "partner-totp"]),
            # Commerce
            ("checkout-api",    "api",  "k8s",     ["cart-service", "pricing-engine",
                                                    "payment-orchestrator", "fraud-scoring",
                                                    "inventory-service"]),
            ("catalog-api",     "api",  "k8s",     ["catalog-db", "search-cluster", "cache-cluster"]),
            ("cart-service",    "api",  "k8s",     ["cache-cluster", "session-store"]),
            ("pricing-engine",  "api",  "k8s",     ["pricing-db", "promo-service"]),
            ("promo-service",   "api",  "k8s",     ["promo-db"]),
            ("inventory-service","api", "k8s",     ["inventory-db", "warehouse-sync"]),
            # Payments
            ("payment-orchestrator", "core", "k8s", ["payment-gateway", "fraud-scoring",
                                                     "ledger-service"]),
            ("payment-gateway", "core", "k8s",     ["partner-bank-visa", "partner-bank-mc",
                                                    "partner-upi"]),
            ("fraud-scoring",   "core", "fargate", ["fraud-model-server", "feature-store"]),
            ("ledger-service",  "core", "k8s",     ["ledger-db"]),
            # Data
            ("user-db",         "data", "vm",      []),
            ("catalog-db",      "data", "vm",      []),
            ("pricing-db",      "data", "vm",      []),
            ("promo-db",        "data", "vm",      []),
            ("inventory-db",    "data", "vm",      []),
            ("ledger-db",       "data", "vm",      []),
            ("session-store",   "data", "k8s",     []),
            ("cache-cluster",   "data", "k8s",     []),
            ("search-cluster",  "data", "vm",      []),
            ("feature-store",   "data", "k8s",     ["feature-store-db"]),
            ("feature-store-db","data", "vm",      []),
            ("fraud-model-server","core","fargate",["feature-store"]),
            # POS plane
            ("pos-gateway",     "edge", "k8s",     ["api-gateway", "store-sync"]),
            ("store-sync",      "core", "k8s",     ["inventory-service", "ledger-service"]),
        ]
        services = []
        for name, tier, runtime, deps in catalog:
            region = self.rng.choice(self.regions[:3])  # majority US/EU
            services.append(Service(
                name=name, tier=tier, runtime=runtime, region=region,
                replicas=self.rng.choice([3, 4, 6, 8, 12]) if runtime == "k8s" else 1,
                deps=deps,
                criticality=1 if name in ("payment-orchestrator","payment-gateway",
                                          "checkout-api","auth-service") else 3,
            ))
        return services

    def _build_hosts(self) -> list[Host]:
        hosts: list[Host] = []
        for svc in self.services:
            if svc.runtime == "k8s":
                for _ in range(svc.replicas):
                    suffix = ''.join(self.rng.choices(
                        "abcdefghijklmnopqrstuvwxyz0123456789", k=5))
                    rs = ''.join(self.rng.choices(
                        "abcdef0123456789", k=10))
                    hosts.append(Host(
                        hostname=f"{svc.name}-{rs}-{suffix}",
                        kind="pod",
                        region=svc.region,
                        az=self.rng.choice(svc.region.azs),
                        runs=[svc.name],
                    ))
            elif svc.runtime == "vm":
                env = self.rng.choice(["prod", "prod"])  # prod-heavy
                idx = self.rng.randint(1, 8)
                hosts.append(Host(
                    hostname=f"{svc.name}-vm-{svc.region.code[:4]}-{env}-{idx:02d}",
                    kind="vm",
                    region=svc.region,
                    az=self.rng.choice(svc.region.azs),
                    runs=[svc.name],
                ))
            elif svc.runtime in ("lambda", "fargate"):
                hosts.append(Host(
                    hostname=f"ip-10-{self.rng.randint(10,99)}-"
                             f"{self.rng.randint(0,255)}-{self.rng.randint(1,254)}."
                             f"{svc.region.code}.compute.internal",
                    kind="ec2",
                    region=svc.region,
                    az=self.rng.choice(svc.region.azs),
                    runs=[svc.name],
                ))
        # POS terminals — thousands of them
        cities = [("mumbai", "ap-south-1"), ("delhi", "ap-south-1"),
                  ("singapore", "ap-southeast-1"), ("london", "eu-west-1"),
                  ("nyc", "us-east-2"), ("austin", "us-east-2")]
        for city, region_code in cities:
            region = next(r for r in self.regions if r.code == region_code)
            for i in range(1, self.rng.randint(180, 280)):
                hosts.append(Host(
                    hostname=f"pos-terminal-{city}-{i:03d}",
                    kind="pos",
                    region=region,
                    az=region.azs[0],
                    runs=["pos-gateway"],
                ))
        return hosts

    def _wire_dependencies(self) -> dict[str, list[str]]:
        return {s.name: s.deps for s in self.services}
```

This is the **single source of truth** the platform pretends not to know. Every generator below reads from `EnterpriseWorld`. Every agent is graded against it. The "wow" moment of the demo is the inferred graph matching the hidden one with >90% edge recall.

### 4.2 Realistic naming conventions

Your memories show you live in this world — the naming has to feel right:

- **EC2:** `ip-10-12-44-8.us-east-2.compute.internal`
- **K8s pod:** `checkout-api-7f5d8b6f9c-lx92q` (deployment-replicaset-pod)
- **VM:** `payment-vm-eus2-prod-04`
- **POS:** `pos-terminal-mumbai-221`
- **Service:** `payment-orchestrator`, `fraud-scoring`
- **Region:** `us-east-2`, `ap-south-1`
- **AZ:** `use2-az1`

### 4.3 Generators — metrics example

```python
# packages/synth/src/helix_synth/generators/metrics.py
import time, math, random
from helix_core.events import TelemetryEvent
from helix_synth.world.topology import EnterpriseWorld, Host

class MetricsGenerator:
    """Emits infra + container metrics with realistic noise floor + diurnal patterns."""

    def __init__(self, world: EnterpriseWorld, rng_seed: int = 1):
        self.world = world
        self.rng = random.Random(rng_seed)

    def _diurnal(self, ts: float) -> float:
        """Returns 0.3..1.0 — load follows business hours per region."""
        hour = (ts // 3600) % 24
        # Smooth sine, peak at 14:00 local
        return 0.5 + 0.4 * math.sin((hour - 14) * math.pi / 12)

    def _noise(self, base: float, jitter: float = 0.08) -> float:
        return max(0.0, base + self.rng.gauss(0, base * jitter))

    def emit_host(self, host: Host, ts: float, fault_modifier: dict | None = None) -> list[TelemetryEvent]:
        fm = fault_modifier or {}
        load = self._diurnal(ts)
        cpu = self._noise(35 * load) + fm.get("cpu_boost", 0)
        mem = self._noise(58 + 12 * load) + fm.get("mem_boost", 0)
        net_in = self._noise(120 * load) * (1 + fm.get("net_mult", 0))
        net_out = self._noise(90 * load) * (1 + fm.get("net_mult", 0))

        base = {
            "host": host.hostname,
            "region": host.region.code,
            "az": host.az,
            "kind": host.kind,
            "service": host.runs[0] if host.runs else None,
            "ts": ts,
        }
        events = [
            TelemetryEvent(sourcetype="helix:metrics:cpu",
                           index="helix_metrics",
                           data={**base, "cpu_pct": round(cpu, 2)}),
            TelemetryEvent(sourcetype="helix:metrics:mem",
                           index="helix_metrics",
                           data={**base, "mem_pct": round(min(mem, 99.9), 2)}),
            TelemetryEvent(sourcetype="helix:metrics:net",
                           index="helix_metrics",
                           data={**base, "rx_kbps": round(net_in, 1),
                                 "tx_kbps": round(net_out, 1)}),
        ]
        if host.kind == "pod":
            events.append(TelemetryEvent(
                sourcetype="helix:metrics:k8s",
                index="helix_metrics",
                data={**base,
                      "restarts": fm.get("restarts", 0),
                      "ready": fm.get("not_ready", False) is False,
                      "phase": fm.get("phase", "Running")}))
        return events
```

### 4.4 Scenario engine — `checkout_collapse.yaml`

```yaml
# scenarios/checkout_collapse.yaml
name: checkout_collapse
description: Fraud-scoring feature-store latency cascades into checkout outage
duration_seconds: 900
phases:
  - at: 0
    name: baseline
    affects: []
  - at: 120
    name: feature_store_db_io_pressure
    affects:
      - target: { kind: service, name: feature-store-db }
        modifiers: { cpu_boost: 25, io_wait_boost: 40 }
      - target: { kind: log, service: feature-store }
        inject:
          - level: WARN
            message: "feature lookup p99 {latency_ms}ms exceeds SLO 80ms"
            rate_per_min: 40
  - at: 240
    name: fraud_scoring_timeouts
    affects:
      - target: { kind: service, name: fraud-scoring }
        modifiers: { error_rate: 0.18, latency_p99_ms: 1400 }
      - target: { kind: log, service: fraud-scoring }
        inject:
          - level: ERROR
            message: "feature store call timeout after 1500ms — falling back to heuristic"
            rate_per_min: 90
  - at: 360
    name: checkout_partial_outage
    affects:
      - target: { kind: service, name: checkout-api }
        modifiers: { error_rate: 0.31, request_rate_mult: 0.7 }
      - target: { kind: incident, severity: SEV2 }
        create:
          title: "Elevated checkout API errors in us-east-2"
          assignment_group: "Payments-SRE"
  - at: 540
    name: pos_terminal_failures
    affects:
      - target: { kind: pos, region: ap-south-1 }
        modifiers: { offline_pct: 0.22 }
  - at: 720
    name: recovery
    affects:
      - target: { kind: service, name: feature-store-db }
        modifiers: { cpu_boost: 0, io_wait_boost: 0 }
```

The orchestrator reads this, applies modifiers per tick, and emits telemetry that *looks like a real cascading failure*. The agents don't know the script. They have to figure it out.

### 4.5 HEC sink with batching

```python
# packages/synth/src/helix_synth/hec_sink.py
import asyncio, json, time
import httpx
from helix_core.events import TelemetryEvent

class HECSink:
    def __init__(self, url: str, token: str, batch_size: int = 200,
                 flush_interval: float = 1.0):
        self.url = url.rstrip("/") + "/services/collector/event"
        self.headers = {"Authorization": f"Splunk {token}"}
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self._queue: asyncio.Queue[TelemetryEvent] = asyncio.Queue(maxsize=10_000)
        self._client = httpx.AsyncClient(http2=False, timeout=10.0,
                                          headers=self.headers, verify=False)
        self._task: asyncio.Task | None = None

    async def start(self):
        self._task = asyncio.create_task(self._run())

    async def emit(self, ev: TelemetryEvent):
        await self._queue.put(ev)

    async def _run(self):
        buf: list[TelemetryEvent] = []
        last_flush = time.time()
        while True:
            timeout = max(0.05, self.flush_interval - (time.time() - last_flush))
            try:
                ev = await asyncio.wait_for(self._queue.get(), timeout=timeout)
                buf.append(ev)
            except asyncio.TimeoutError:
                pass
            if buf and (len(buf) >= self.batch_size
                        or time.time() - last_flush >= self.flush_interval):
                await self._flush(buf)
                buf.clear()
                last_flush = time.time()

    async def _flush(self, batch: list[TelemetryEvent]):
        payload = "\n".join(
            json.dumps({
                "time": e.data.get("ts", time.time()),
                "host": e.data.get("host"),
                "source": "helix-synth",
                "sourcetype": e.sourcetype,
                "index": e.index,
                "event": e.data,
            }) for e in batch
        )
        try:
            r = await self._client.post(self.url, content=payload)
            r.raise_for_status()
        except Exception as exc:
            # backpressure: drop with logging — never block the simulator
            print(f"[hec] flush failed: {exc} (dropping {len(batch)} events)")
```

Note: `http2=False`. Your memories show you've hit the same HTTP/2-on-HEC trap on real Splunk — this preempts it.

---

## 5. Module 2 — Splunk Integration Layer

Splunk is the **substrate**. Everything else is ephemeral. If we crash, Splunk still has the history.

### 5.1 Index & sourcetype strategy

```
# infra/splunk/default/indexes.conf
[helix_metrics]
homePath   = $SPLUNK_DB/helix_metrics/db
coldPath   = $SPLUNK_DB/helix_metrics/colddb
thawedPath = $SPLUNK_DB/helix_metrics/thaweddb
maxDataSize = auto_high_volume
frozenTimePeriodInSecs = 2592000

[helix_logs]
homePath   = $SPLUNK_DB/helix_logs/db
coldPath   = $SPLUNK_DB/helix_logs/colddb
thawedPath = $SPLUNK_DB/helix_logs/thaweddb

[helix_traces]
[helix_incidents]
[helix_security]
[helix_business]
[helix_audit]            # agent actions, SPL provenance, decisions
```

**Sourcetypes** (verb-shaped for discoverability):
- `helix:metrics:cpu`, `helix:metrics:mem`, `helix:metrics:net`, `helix:metrics:k8s`, `helix:metrics:business`
- `helix:logs:app`, `helix:logs:auth`, `helix:logs:security`
- `helix:traces:span`
- `helix:incidents:servicenow`
- `helix:deploy:event`
- `helix:agent:reasoning` ← agents write back here; the audit trail of the AI's mind

### 5.2 Canonical SPL library

```python
# packages/splunk/src/helix_splunk/spl/library.py
SPL = {

"errors_per_service_last_15m": """
index=helix_logs sourcetype=helix:logs:app level=ERROR earliest=-15m@m
| stats count by service, region
| sort - count
""",

"latency_p99_by_service": """
index=helix_traces sourcetype=helix:traces:span earliest=-15m@m
| stats p99(duration_ms) as p99_ms, count as call_count by service
| where call_count > 50
| sort - p99_ms
""",

"deps_inferred_from_traces": """
index=helix_traces sourcetype=helix:traces:span earliest=-30m@m
| stats count by parent_service, service
| where count > 20
| rename parent_service as source, service as target
""",

"cascading_error_chains": """
index=helix_logs level=ERROR earliest=-30m@m
| bin _time span=30s
| stats values(service) as services, dc(service) as svc_count by _time
| where svc_count >= 3
| sort _time
""",

"pos_offline_by_region": """
index=helix_metrics sourcetype=helix:metrics:k8s kind=pos earliest=-5m@m
| stats latest(ready) as ready by host, region
| where ready=0
| stats count as offline_count by region
""",

"recent_deployments_correlated_with_errors": """
index=helix_deploy earliest=-2h@h
| eval deploy_time=_time
| join service [
    search index=helix_logs level=ERROR earliest=-2h@h
    | stats count as errors, min(_time) as first_error by service
  ]
| where first_error > deploy_time AND first_error - deploy_time < 600
| table service, deploy_time, first_error, errors
""",
}
```

### 5.3 AI-generated SPL with safety validation

Agents will write SPL. That's dangerous. We need a **validator** before execution:

```python
# packages/splunk/src/helix_splunk/spl/validator.py
import re

DANGEROUS = re.compile(r"\b(delete|outputlookup|sendemail|script|"
                        r"sendalert|collect|tscollect|outputcsv)\b", re.I)
FORBIDDEN_INDEXES = {"_internal", "_audit", "_introspection"}
REQUIRE_TIME_BOUND = re.compile(r"\b(earliest|latest)\s*=", re.I)
INDEX_RE = re.compile(r"\bindex\s*=\s*([A-Za-z0-9_\*]+)", re.I)

class SPLValidationError(ValueError): ...

def validate_spl(spl: str, *, allow_indexes: set[str], max_time_window_min: int = 240) -> str:
    s = spl.strip()
    if not s.startswith(("search ", "|", "index", "tstats", "datamodel")) and "index=" not in s[:120]:
        raise SPLValidationError("SPL must begin with a search or scope an index")
    if DANGEROUS.search(s):
        raise SPLValidationError("SPL contains a forbidden command")
    indexes = {m.group(1) for m in INDEX_RE.finditer(s)}
    if indexes & FORBIDDEN_INDEXES:
        raise SPLValidationError(f"Forbidden index: {indexes & FORBIDDEN_INDEXES}")
    if allow_indexes and not indexes.issubset(allow_indexes | {"*"}):
        raise SPLValidationError(f"Disallowed indexes: {indexes - allow_indexes}")
    if not REQUIRE_TIME_BOUND.search(s):
        raise SPLValidationError("SPL must include earliest/latest time bound")
    return s
```

Agents never call Splunk directly — they call the `splunk_search` MCP tool, which calls the validator first, logs to `helix_audit`, then executes. **Provenance is mandatory.**

### 5.4 Sample HEC payload — the shape on the wire

```json
{
  "time": 1730462400.412,
  "host": "checkout-api-7f5d8b6f9c-lx92q",
  "source": "helix-synth",
  "sourcetype": "helix:logs:app",
  "index": "helix_logs",
  "event": {
    "ts": 1730462400.412,
    "service": "checkout-api",
    "region": "us-east-2",
    "az": "use2-az2",
    "level": "ERROR",
    "trace_id": "8a31f9e0c2b14a5e9d7f6e3a2b1c0d4e",
    "span_id": "f3e2d1c0b9a8",
    "message": "downstream fraud-scoring timeout after 1500ms; circuit-breaker OPEN",
    "http_status": 503,
    "user_id_hash": "a7c2…",
    "request_id": "req_01HRPK4N7T",
    "downstream": "fraud-scoring",
    "deployment": "checkout-api@v2.41.3"
  }
}
```

---

## 6. Module 3 — AI Agent Mesh

This is where TITAN HELIX stops being observability and starts being intelligence.

### 6.1 Why multi-agent, not one big prompt

A single prompt that "diagnoses an incident" fails because incidents have multiple analytical *modes*: correlation is statistical, prediction is causal, security is adversarial, governance is procedural. Forcing one model into all modes produces mediocre everything. Specialized agents let each prompt be sharp.

The harder question: **how do agents share context without becoming a chat group of stochastic parrots?** Answer: a **structured shared state** with strict slots, plus a **supervisor router** that decides who speaks next based on state deltas. LangGraph's `StateGraph` is the natural fit.

### 6.2 The shared mesh state

```python
# packages/agents/src/helix_agents/runtime/state.py
from typing import Annotated, TypedDict
from operator import add
from helix_core.schemas import GraphSnapshot, Incident, AgentOpinion, RemediationPlan

class MeshState(TypedDict):
    # Incoming trigger
    trigger: dict                       # the event/alert that woke the mesh

    # Observations — append-only
    observations: Annotated[list[dict], add]

    # Each agent's opinion, with confidence
    opinions: Annotated[list[AgentOpinion], add]

    # Current best graph snapshot
    graph: GraphSnapshot

    # Active hypotheses (rotated as the debate evolves)
    hypotheses: list[dict]

    # Predicted future incidents
    forecast: list[dict]

    # Memory hits — past similar incidents
    memory_hits: list[Incident]

    # Proposed remediations
    remediations: list[RemediationPlan]

    # Executive narrative (final)
    summary: str | None

    # Debate transcript for UI streaming
    transcript: Annotated[list[dict], add]
```

### 6.3 Agent contract

```python
# packages/agents/src/helix_agents/agents/base.py
from abc import ABC, abstractmethod
from helix_agents.runtime.state import MeshState
from helix_agents.llm.provider import LLMProvider
from helix_mcp.client import MCPClient

class Agent(ABC):
    name: str
    role: str
    speaks_when: list[str]               # state keys whose mutation should wake this agent

    def __init__(self, llm: LLMProvider, mcp: MCPClient):
        self.llm = llm
        self.mcp = mcp

    @abstractmethod
    async def __call__(self, state: MeshState) -> dict:
        """Returns a partial-state update."""
        ...
```

### 6.4 The Observer agent

```python
# packages/agents/src/helix_agents/agents/observer.py
from helix_agents.agents.base import Agent
from helix_agents.runtime.state import MeshState

OBSERVER_SYSTEM = """\
You are the OBSERVER agent in the TITAN HELIX operational mesh.
Your job: turn raw telemetry into structured, *bounded* observations.
You do NOT speculate. You do NOT correlate. You only report what you see.

Available tools (MCP):
  - splunk_search(spl, earliest, latest)
  - splunk_index_stats(index, window)
  - graph_query(node|edge filters)

Output a JSON object with this shape:
{
  "summary": "<=160 chars, factual",
  "metrics": [ {"name": str, "value": number, "context": str} ],
  "anomalies": [ {"signal": str, "where": str, "severity": "low|med|high"} ],
  "confidence": float (0..1),
  "spl_used": [ str ]
}
Do not invent fields. Do not include explanation prose outside the JSON.
"""

class ObserverAgent(Agent):
    name = "observer"
    role = "Reports raw operational state"
    speaks_when = ["trigger"]

    async def __call__(self, state: MeshState) -> dict:
        trigger = state["trigger"]
        # Pull 3 quick views via MCP
        errs = await self.mcp.call("splunk_search", {
            "spl": "index=helix_logs level=ERROR earliest=-15m@m "
                   "| stats count by service | sort - count | head 10",
            "earliest": "-15m@m", "latest": "now"
        })
        lat = await self.mcp.call("splunk_search", {
            "spl": "index=helix_traces earliest=-15m@m "
                   "| stats p99(duration_ms) as p99 by service "
                   "| where p99>500 | sort - p99 | head 10",
            "earliest": "-15m@m", "latest": "now"
        })
        ctx = {"trigger": trigger, "top_errors": errs, "top_latency": lat}
        out = await self.llm.json(system=OBSERVER_SYSTEM, user=str(ctx))
        return {
            "observations": [{"agent": "observer", **out}],
            "transcript": [{"agent": "observer", "kind": "report", "content": out}]
        }
```

### 6.5 LangGraph topology — supervisor + specialists

```python
# packages/agents/src/helix_agents/runtime/graph.py
from langgraph.graph import StateGraph, END
from helix_agents.runtime.state import MeshState
from helix_agents.agents import (ObserverAgent, CorrelationAgent, TopologyAgent,
                                  PredictionAgent, SecurityAgent, MemoryAgent,
                                  RemediationAgent, GovernanceAgent, ExecutiveAgent)
from helix_agents.runtime.router import supervisor_route

def build_mesh(llm, mcp):
    g = StateGraph(MeshState)

    g.add_node("observer",    ObserverAgent(llm, mcp))
    g.add_node("memory",      MemoryAgent(llm, mcp))
    g.add_node("topology",    TopologyAgent(llm, mcp))
    g.add_node("correlation", CorrelationAgent(llm, mcp))
    g.add_node("prediction",  PredictionAgent(llm, mcp))
    g.add_node("security",    SecurityAgent(llm, mcp))
    g.add_node("remediation", RemediationAgent(llm, mcp))
    g.add_node("governance",  GovernanceAgent(llm, mcp))
    g.add_node("executive",   ExecutiveAgent(llm, mcp))

    g.set_entry_point("observer")

    # Observer always goes to memory + topology in parallel
    g.add_edge("observer", "memory")
    g.add_edge("observer", "topology")

    # Then supervisor decides — correlation, prediction, security, or executive
    g.add_conditional_edges("memory",   supervisor_route)
    g.add_conditional_edges("topology", supervisor_route)
    g.add_conditional_edges("correlation", supervisor_route)
    g.add_conditional_edges("prediction",  supervisor_route)
    g.add_conditional_edges("security",    supervisor_route)
    g.add_conditional_edges("remediation", supervisor_route)
    g.add_conditional_edges("governance",  supervisor_route)

    g.add_edge("executive", END)
    return g.compile()
```

The `supervisor_route` function is a tiny pure-Python function (no LLM call) that inspects state and decides next hop based on what's *still missing*. This is critical for cost: the supervisor itself is free.

```python
# packages/agents/src/helix_agents/runtime/router.py
def supervisor_route(state) -> str:
    opinions = {o["agent"] for o in state.get("opinions", [])}
    obs = state.get("observations", [])
    has_security_signal = any(o.get("kind") == "security" for o in obs)

    if "correlation" not in opinions and len(obs) >= 2:
        return "correlation"
    if has_security_signal and "security" not in opinions:
        return "security"
    if "correlation" in opinions and "prediction" not in opinions:
        return "prediction"
    if state.get("forecast") and "remediation" not in opinions:
        return "remediation"
    if state.get("remediations") and "governance" not in opinions:
        return "governance"
    return "executive"
```

### 6.6 The debate protocol

When two agents disagree (e.g., Correlation says "DB", Topology says "fraud-scoring"), we trigger a bounded debate:

```python
# packages/agents/src/helix_agents/debate.py
DEBATE_TURNS = 3

async def debate(claim_a: AgentOpinion, claim_b: AgentOpinion, llm) -> AgentOpinion:
    """
    Two opinions enter, one synthesis leaves.
    Each side presents reasoning + evidence (SPL queries used).
    A third 'judge' prompt picks a winner OR synthesizes a unified view.
    """
    transcript = []
    for turn in range(DEBATE_TURNS):
        rebuttal_a = await llm.json(
            system="You are agent A. Rebut agent B's claim using evidence only.",
            user={"yours": claim_a, "theirs": claim_b, "history": transcript})
        transcript.append({"side": "A", **rebuttal_a})
        rebuttal_b = await llm.json(
            system="You are agent B. Rebut agent A's claim using evidence only.",
            user={"yours": claim_b, "theirs": claim_a, "history": transcript})
        transcript.append({"side": "B", **rebuttal_b})

    synthesis = await llm.json(
        system="You are the JUDGE. Either declare a winner with reasoning, "
               "or synthesize a higher-order claim. Return AgentOpinion JSON.",
        user={"a": claim_a, "b": claim_b, "transcript": transcript})
    return synthesis
```

This is the UX gold: streaming this transcript to the frontend looks like **two AIs arguing about your prod environment**. Judges remember demos like that.

### 6.7 Provider abstraction

```python
# packages/agents/src/helix_agents/llm/provider.py
from abc import ABC, abstractmethod
import os, json
import httpx

class LLMProvider(ABC):
    @abstractmethod
    async def json(self, *, system: str, user: str | dict, model: str | None = None) -> dict: ...
    @abstractmethod
    async def stream(self, *, system: str, user: str | dict, model: str | None = None): ...

class AnthropicProvider(LLMProvider):
    def __init__(self, default_model: str = "claude-opus-4-7"):
        self.key = os.environ["ANTHROPIC_API_KEY"]
        self.default_model = default_model
        self.client = httpx.AsyncClient(timeout=60.0)

    async def json(self, *, system, user, model=None):
        body = {
            "model": model or self.default_model,
            "max_tokens": 2048,
            "system": system + "\n\nReturn ONLY valid JSON. No markdown.",
            "messages": [{"role": "user",
                          "content": user if isinstance(user, str) else json.dumps(user)}]
        }
        r = await self.client.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": self.key, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json=body)
        r.raise_for_status()
        text = r.json()["content"][0]["text"]
        return json.loads(text)

    async def stream(self, *, system, user, model=None):
        # SSE stream — yields token deltas; used for UI reasoning panel
        ...
```

OpenAI adapter is structurally identical. Switching providers is a config flip.

### 6.8 Memory — episodic + semantic

The Memory Agent is the long-term cortex. Two stores:

1. **Episodic** — every incident, every remediation, stored in Splunk index `helix_audit` and embedded into a vector store (pgvector or Chroma).
2. **Semantic** — a knowledge graph of `(service → failure_mode → effective_remediation)` triples, rebuilt nightly from episodic data.

```python
# packages/agents/src/helix_agents/runtime/memory.py
class OperationalMemory:
    async def remember(self, incident: dict, resolution: dict):
        # 1. Splunk audit
        await self.splunk.hec_emit("helix_audit", "helix:agent:memory",
            {"type": "incident_resolved", **incident, **resolution})
        # 2. Embed + store
        text = self._narrative(incident, resolution)
        vec = await self.embedder.embed(text)
        self.vectors.upsert(id=incident["id"], vec=vec, meta=incident)

    async def recall(self, query: str, k: int = 5) -> list[dict]:
        vec = await self.embedder.embed(query)
        return self.vectors.search(vec, k=k)
```

When a new incident lands, the Memory Agent fires `recall("checkout 5xx fraud timeout us-east-2")` and the top-5 matching historical incidents *with their resolutions* get injected into the Remediation Agent's context. **This is how the platform learns.**

---

## 7. Module 4 — AI-Generated Operational Graph (Hero feature)

The graph is the **face** of TITAN HELIX. Everything else exists to feed it.

### 7.1 Why static topology fails

CMDBs are perpetually wrong. Service catalogs lag deployments by weeks. The only ground truth is the *runtime behavior* — who actually called whom in the last 15 minutes. That's an inferred graph, not a documented one.

### 7.2 Three-layer graph model

| Layer | Source | Updates | Confidence |
|---|---|---|---|
| **L1 Observed** | Traces (parent_service → service) | every 30s | 0.95+ |
| **L2 Inferred** | Logs co-occurrence, error correlation, deployment timing | every 60s | 0.5–0.9 |
| **L3 Hypothesized** | AI agent claim ("checkout depends on fraud-scoring per their debate") | on agent action | 0.3–0.7 |

The frontend renders all three with different edge styles: solid (L1), dashed (L2), pulsing dotted (L3). The user can see the **AI thinking** in the topology itself.

### 7.3 Node schema

```json
{
  "id": "svc:checkout-api",
  "kind": "service",
  "label": "checkout-api",
  "tier": "api",
  "runtime": "k8s",
  "region": "us-east-2",
  "business_unit": "commerce",
  "criticality": 1,
  "metrics": {
    "error_rate": 0.31,
    "p99_ms": 1820,
    "request_rate_rpm": 14200,
    "replicas_ready": 6,
    "replicas_desired": 8
  },
  "state": "degraded",
  "incidents": ["INC0123456"],
  "anomaly_score": 0.78,
  "last_deploy": "2026-05-28T13:42:11Z"
}
```

### 7.4 Edge schema

```json
{
  "id": "edge:checkout-api->fraud-scoring",
  "source": "svc:checkout-api",
  "target": "svc:fraud-scoring",
  "kind": "calls",
  "layer": "L1_observed",
  "confidence": 0.97,
  "metrics": {
    "calls_per_min": 12400,
    "error_rate": 0.22,
    "p99_ms": 1480
  },
  "evidence": {
    "trace_sample_ids": ["8a31f9e0…", "b2c4d6e8…"],
    "spl_used": "index=helix_traces parent_service=checkout-api service=fraud-scoring earliest=-15m@m | stats count by service"
  },
  "blast_radius_role": "carrier"
}
```

`evidence` is non-negotiable. **Every AI-generated edge must be clickable to its proof.** No proof, no edge.

### 7.5 Inference pipeline

```python
# packages/graph/src/helix_graph/inference.py
import networkx as nx
from helix_core.schemas import GraphSnapshot
from helix_splunk.search import SplunkSearch
from helix_splunk.spl.library import SPL

class GraphInferencer:
    def __init__(self, splunk: SplunkSearch):
        self.splunk = splunk

    async def infer(self, window_min: int = 15) -> GraphSnapshot:
        g = nx.DiGraph()

        # --- L1: traces ---
        rows = await self.splunk.run(SPL["deps_inferred_from_traces"])
        for r in rows:
            s, t = f"svc:{r['source']}", f"svc:{r['target']}"
            g.add_node(s, kind="service")
            g.add_node(t, kind="service")
            g.add_edge(s, t,
                       layer="L1_observed",
                       confidence=min(0.99, 0.5 + 0.05 * (int(r["count"]) ** 0.3)),
                       kind="calls",
                       metrics={"calls": int(r["count"])})

        # --- L2: log co-occurrence (services failing together) ---
        chains = await self.splunk.run(SPL["cascading_error_chains"])
        for chain in chains:
            services = chain["services"]
            for i, a in enumerate(services):
                for b in services[i+1:]:
                    sa, sb = f"svc:{a}", f"svc:{b}"
                    if not g.has_edge(sa, sb):
                        g.add_edge(sa, sb, layer="L2_inferred",
                                   confidence=0.45, kind="co_failing")

        # --- enrichment: tier, region, criticality from latest graph snapshot ---
        await self._enrich(g)
        return GraphSnapshot.from_networkx(g)
```

### 7.6 Blast radius — the temporal propagation engine

This is what gives the graph its predictive power.

```python
# packages/graph/src/helix_graph/propagation.py
import networkx as nx
from helix_core.schemas import GraphSnapshot

def simulate_blast_radius(g: nx.DiGraph, origin: str, *, horizon_min: int = 60,
                          tick_min: int = 5) -> list[dict]:
    """
    Returns a list of timeline frames, each a dict of node_id -> impact_prob.
    Propagation uses edge confidence × edge fragility × tier susceptibility.
    """
    timeline = []
    state = {n: 0.0 for n in g.nodes}
    state[origin] = 1.0

    ticks = horizon_min // tick_min
    for t in range(ticks):
        new_state = dict(state)
        for node, prob in state.items():
            if prob < 0.05:
                continue
            for _, succ, data in g.out_edges(node, data=True):
                edge_conf = data.get("confidence", 0.5)
                fragility = data.get("metrics", {}).get("error_rate", 0.0) + 0.1
                susceptibility = 1.0 - 0.15 * (g.nodes[succ].get("criticality", 3) - 1)
                contagion = prob * edge_conf * fragility * susceptibility * 0.6
                new_state[succ] = min(1.0, new_state[succ] + contagion)
        state = new_state
        timeline.append({
            "t_minutes": (t + 1) * tick_min,
            "impacts": {n: round(p, 3) for n, p in state.items() if p > 0.05}
        })
    return timeline
```

UI side: scrub a timeline slider, watch the graph light up in waves. *"Projected payment outage in 34 minutes. 11,400 POS terminals affected across APAC-South."* The number isn't theatrical — it's `len({h for h in hosts if h.kind=='pos' and h.region=='ap-south-1'}) * impacts['svc:pos-gateway']`.

### 7.7 Sample full graph payload

```json
{
  "snapshot_id": "snap_01HRPK4N7T",
  "generated_at": "2026-05-28T14:23:11Z",
  "window_min": 15,
  "nodes": [
    { "id": "svc:checkout-api", "kind": "service", "label": "checkout-api",
      "state": "degraded", "tier": "api", "region": "us-east-2",
      "metrics": { "error_rate": 0.31, "p99_ms": 1820, "request_rate_rpm": 14200 },
      "anomaly_score": 0.78 },
    { "id": "svc:fraud-scoring", "kind": "service", "label": "fraud-scoring",
      "state": "degraded", "tier": "core", "region": "us-east-2",
      "metrics": { "error_rate": 0.18, "p99_ms": 1410 },
      "anomaly_score": 0.72 },
    { "id": "svc:feature-store-db", "kind": "service", "label": "feature-store-db",
      "state": "critical", "tier": "data", "region": "us-east-2",
      "metrics": { "cpu_pct": 96.4, "io_wait_pct": 41.0 },
      "anomaly_score": 0.91 }
  ],
  "edges": [
    { "id": "e1", "source": "svc:checkout-api", "target": "svc:fraud-scoring",
      "layer": "L1_observed", "confidence": 0.97, "kind": "calls",
      "metrics": { "calls": 12400, "error_rate": 0.22, "p99_ms": 1480 },
      "blast_radius_role": "carrier" },
    { "id": "e2", "source": "svc:fraud-scoring", "target": "svc:feature-store-db",
      "layer": "L2_inferred", "confidence": 0.74, "kind": "co_failing",
      "metrics": { "co_failure_windows": 8 } }
  ],
  "blast_radius": {
    "origin": "svc:feature-store-db",
    "timeline": [
      { "t_minutes": 5,  "impacts": { "svc:fraud-scoring": 0.42 } },
      { "t_minutes": 15, "impacts": { "svc:fraud-scoring": 0.71, "svc:checkout-api": 0.38 } },
      { "t_minutes": 30, "impacts": { "svc:fraud-scoring": 0.88, "svc:checkout-api": 0.69,
                                       "svc:payment-orchestrator": 0.41 } }
    ]
  }
}
```

---

## 8. Module 9 — Splunk MCP Server Integration

MCP is what turns the agents from text generators into **operators**. Treat it as the platform's nervous system.

### 8.1 MCP positioning

TITAN HELIX runs **two MCP roles simultaneously:**

1. **As MCP server** — exposes Splunk search, graph queries, blast radius, and runbook execution as tools any MCP-compatible client (Claude Desktop, Cursor, custom agents) can call. This makes TITAN HELIX itself a **platform** other AI systems plug into.
2. **As MCP client** — its own internal agents call these same tools through the MCP protocol, which means *the agents and external clients are equal citizens*. No internal back door.

This symmetry is the architectural insight. Most MCP integrations expose a server and stop. By being client and server, we get free dogfooding: if our agents can solve incidents through MCP, anyone's can.

### 8.2 The tool registry

```python
# packages/mcp/src/helix_mcp/registry.py
from dataclasses import dataclass
from typing import Callable, Awaitable, Any

@dataclass
class MCPTool:
    name: str
    description: str
    input_schema: dict           # JSON schema
    output_schema: dict
    handler: Callable[[dict], Awaitable[Any]]
    requires_approval: bool = False
    audit: bool = True

class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, MCPTool] = {}

    def register(self, tool: MCPTool):
        if tool.name in self._tools:
            raise ValueError(f"duplicate tool: {tool.name}")
        self._tools[tool.name] = tool

    def list(self) -> list[dict]:
        return [{"name": t.name, "description": t.description,
                 "inputSchema": t.input_schema} for t in self._tools.values()]

    async def invoke(self, name: str, args: dict, *, actor: str) -> Any:
        tool = self._tools[name]
        if tool.requires_approval:
            raise PermissionError(f"{name} requires human approval")
        # audit FIRST, then execute — so we have a record even on failure
        if tool.audit:
            await self._audit(actor, name, args)
        return await tool.handler(args)
```

### 8.3 Tool catalogue (initial set)

| Tool | Purpose | Approval | Notes |
|---|---|---|---|
| `splunk_search` | Run validated SPL, return rows | ❌ | Validator + audit |
| `splunk_index_stats` | Volume/health per index | ❌ | |
| `splunk_emit_event` | Write to `helix_agent:reasoning` | ❌ | Agents log here |
| `graph_query` | Filter nodes/edges by predicate | ❌ | |
| `graph_neighbors` | k-hop expansion of a node | ❌ | |
| `blast_radius_sim` | Run propagation from origin | ❌ | |
| `incident_lookup` | RAG over past incidents | ❌ | |
| `k8s_describe` | Mocked `kubectl describe` | ❌ | Reads from synth world |
| `k8s_rollout_restart` | Mocked restart | ✅ | Logged as "would have" |
| `servicenow_create_ticket` | Mocked ITSM ticket | ❌ | Writes to `helix_incidents` |
| `servicenow_resolve_ticket` | Resolve | ✅ | |
| `runbook_execute` | Named runbook by ID | ✅ | YAML-defined |

`requires_approval=True` tools route through the Governance Agent first, which can deny based on policy (blast radius too large, off-hours change freeze, etc.).

### 8.4 MCP tool: `splunk_search`

```python
# packages/mcp/src/helix_mcp/tools/splunk_search.py
from helix_splunk.search import SplunkSearch
from helix_splunk.spl.validator import validate_spl, SPLValidationError
from helix_mcp.registry import MCPTool

ALLOWED_INDEXES = {"helix_metrics", "helix_logs", "helix_traces",
                   "helix_incidents", "helix_security", "helix_business",
                   "helix_deploy"}

def make_tool(splunk: SplunkSearch) -> MCPTool:
    async def handler(args: dict):
        spl = args["spl"]
        try:
            validated = validate_spl(spl, allow_indexes=ALLOWED_INDEXES)
        except SPLValidationError as e:
            return {"error": f"SPL rejected: {e}", "rows": []}
        rows = await splunk.run(validated,
                                 earliest=args.get("earliest", "-15m@m"),
                                 latest=args.get("latest", "now"))
        return {"rows": rows, "row_count": len(rows), "spl": validated}

    return MCPTool(
        name="splunk_search",
        description="Run a Splunk SPL search against Helix indexes. "
                    "Must include earliest/latest time bounds.",
        input_schema={
            "type": "object",
            "required": ["spl"],
            "properties": {
                "spl": {"type": "string", "description": "SPL query"},
                "earliest": {"type": "string", "default": "-15m@m"},
                "latest": {"type": "string", "default": "now"}
            }
        },
        output_schema={
            "type": "object",
            "properties": {
                "rows": {"type": "array"},
                "row_count": {"type": "integer"},
                "spl": {"type": "string"}
            }
        },
        handler=handler,
    )
```

### 8.5 The MCP server skeleton

```python
# packages/mcp/src/helix_mcp/server.py
from mcp.server import Server
from mcp.server.stdio import stdio_server
from helix_mcp.registry import ToolRegistry
from helix_mcp.tools import (splunk_search, graph_query, blast_radius_sim,
                              incident_lookup, k8s_describe, servicenow_create)

def build_server(splunk, graph, memory) -> Server:
    reg = ToolRegistry()
    reg.register(splunk_search.make_tool(splunk))
    reg.register(graph_query.make_tool(graph))
    reg.register(blast_radius_sim.make_tool(graph))
    reg.register(incident_lookup.make_tool(memory))
    reg.register(k8s_describe.make_tool(splunk))
    reg.register(servicenow_create.make_tool(splunk))

    server = Server("titan-helix")

    @server.list_tools()
    async def list_tools():
        return reg.list()

    @server.call_tool()
    async def call_tool(name: str, args: dict):
        return await reg.invoke(name, args, actor="mcp-client")

    return server

if __name__ == "__main__":
    import asyncio
    from helix_mcp.bootstrap import wire
    asyncio.run(stdio_server(build_server(*wire())))
```

### 8.6 An AI-driven investigation chain — what it actually looks like

User opens the graph, clicks the pulsing red `checkout-api` node, hits "Investigate."

```
[trigger] node:svc:checkout-api state=degraded
  ↓
[Observer] calls splunk_search(top errors), splunk_search(top latency)
   → finds: checkout-api error 31%, fraud-scoring p99 1480ms
  ↓
[Memory] calls incident_lookup("checkout 5xx fraud timeout")
   → recalls 3 past incidents, top match resolved by restarting feature-store-db
  ↓
[Topology] calls graph_neighbors("svc:checkout-api", k=2)
   → returns: fraud-scoring, payment-orchestrator, feature-store, feature-store-db
  ↓
[Correlation] calls splunk_search(cascading_error_chains)
   → finds: feature-store-db CPU spike preceded fraud-scoring errors by 90s
  ↓
[Prediction] calls blast_radius_sim(origin="svc:feature-store-db")
   → returns: payment-orchestrator likely degraded in 18m, POS-APAC in 34m
  ↓
[Remediation] proposes:
   1. rollout-restart feature-store-db (requires_approval)
   2. scale fraud-scoring replicas 4→8
   3. enable fraud-scoring heuristic fallback
   → past incident resolutions weighted #1 highest
  ↓
[Governance] reviews: change freeze inactive, blast radius justifies, approve #2 + #3 autonomous, #1 needs human
  ↓
[Executive] writes 4-sentence narrative + ranked action list to UI
```

This entire chain streams to the frontend as it happens. Every node lights up its panel. SPL queries are clickable. The whole thing is **shown, not just told.**

---

## 9. Module 5 — Frontend Architecture

### 9.1 Design language

We borrow from your **editorial-terminal** language (memories show you've already established this for your portfolio):

- Typeface stack: **Fraunces** (display), **Sora** (UI), **JetBrains Mono** (data/SPL)
- Palette: `#0E0E10` background, `#FF6B35` accent, `#7CF3A0` healthy, `#FFB454` degraded, `#FF4757` critical
- Motion: **physics-first.** No CSS keyframes. Use Framer Motion springs. Reasoning streams in like a heartbeat.
- Density: every panel earns its pixels. Dashboard nostalgia banned.

### 9.2 Stack

- **React 18 + TypeScript**, Vite
- **React Flow** for the graph (better incremental updates than Cytoscape for our case)
- **Zustand** for state (Redux is overkill; Zustand selectors are cleaner for high-frequency WS updates)
- **TanStack Query** for REST
- **Tailwind** + small primitives library; no Material/Chakra
- **D3** for the blast-radius timeline scrubber and sparklines
- **Framer Motion** for choreography

### 9.3 Folder structure

```
apps/web/src/
├── main.tsx
├── app/
│   ├── routes.tsx                       # /, /graph, /timeline, /memory, /simulate
│   ├── theme.ts
│   └── shell.tsx                        # nav + status bar
├── features/
│   ├── command-center/
│   │   ├── CommandCenter.tsx            # hero layout: graph + reasoning + timeline
│   │   ├── StatusBar.tsx
│   │   └── HotkeyBar.tsx
│   ├── mesh-graph/
│   │   ├── MeshGraph.tsx                # React Flow root
│   │   ├── nodes/
│   │   │   ├── ServiceNode.tsx          # custom node with metric ring
│   │   │   ├── DataNode.tsx
│   │   │   ├── PosNode.tsx
│   │   │   └── EdgeNode.tsx
│   │   ├── edges/
│   │   │   └── ConfidenceEdge.tsx       # opacity = confidence, dash = layer
│   │   ├── overlays/
│   │   │   ├── BlastRadiusOverlay.tsx   # pulse waves
│   │   │   ├── AgentDebateOverlay.tsx   # speech bubbles tethered to nodes
│   │   │   └── HeatmapOverlay.tsx       # error-rate density
│   │   ├── layout/
│   │   │   └── elk.ts                   # ELK auto-layout
│   │   └── selectors.ts
│   ├── agent-stream/
│   │   ├── ReasoningPanel.tsx           # token-by-token streaming
│   │   ├── AgentCard.tsx
│   │   ├── DebateTranscript.tsx
│   │   └── SPLProvenance.tsx            # collapsible SPL the agent ran
│   ├── timeline/
│   │   ├── Timeline.tsx                 # operational replay scrubber
│   │   └── IncidentTrack.tsx
│   ├── simulate/
│   │   ├── Simulator.tsx                # "what if X fails" mode
│   │   └── BlastSlider.tsx
│   └── memory/
│       └── MemorySearch.tsx
├── lib/
│   ├── ws.ts                            # typed WS client w/ reconnect
│   ├── api.ts                           # typed REST
│   ├── store/
│   │   ├── graph.ts                     # Zustand: nodes, edges, deltas
│   │   ├── reasoning.ts                 # streamed tokens per agent
│   │   ├── timeline.ts
│   │   └── selection.ts
│   └── format.ts
└── components/
    └── primitives/                      # Button, Card, Pill, MetricRing
```

### 9.4 The custom service node

```tsx
// apps/web/src/features/mesh-graph/nodes/ServiceNode.tsx
import { Handle, Position, NodeProps } from "reactflow";
import { motion } from "framer-motion";
import { MetricRing } from "@/components/primitives/MetricRing";
import { useReasoning } from "@/lib/store/reasoning";
import clsx from "clsx";

type ServiceNodeData = {
  label: string;
  state: "healthy" | "degraded" | "critical";
  errorRate: number;
  p99Ms: number;
  anomalyScore: number;
  region: string;
  tier: string;
};

const stateRing = {
  healthy:  "ring-helix-green/40",
  degraded: "ring-helix-amber/60",
  critical: "ring-helix-red/80 animate-helix-pulse",
};

export function ServiceNode({ data, selected }: NodeProps<ServiceNodeData>) {
  const agentSpeaking = useReasoning((s) => s.activeAgentByNode[data.label]);

  return (
    <motion.div
      layout
      animate={{ scale: selected ? 1.05 : 1 }}
      transition={{ type: "spring", stiffness: 280, damping: 22 }}
      className={clsx(
        "rounded-2xl border border-white/10 bg-helix-bg/85 backdrop-blur-md",
        "px-3 py-2 shadow-helix min-w-[180px] ring-2",
        stateRing[data.state],
      )}
    >
      <Handle type="target" position={Position.Left} className="!bg-white/30 !w-1.5 !h-1.5" />
      <div className="flex items-center gap-2">
        <MetricRing value={data.anomalyScore} state={data.state} size={28} />
        <div className="flex-1 min-w-0">
          <div className="font-mono text-[12px] tracking-tight truncate text-white">
            {data.label}
          </div>
          <div className="text-[10px] text-white/50 uppercase">
            {data.tier} · {data.region}
          </div>
        </div>
      </div>
      <div className="mt-1.5 grid grid-cols-2 gap-x-2 text-[10px] font-mono text-white/70">
        <div>err <span className="text-helix-red">{(data.errorRate*100).toFixed(1)}%</span></div>
        <div>p99 <span className="text-helix-amber">{data.p99Ms}ms</span></div>
      </div>
      {agentSpeaking && (
        <motion.div
          initial={{ opacity: 0, y: -4 }}
          animate={{ opacity: 1, y: 0 }}
          className="absolute -top-3 right-1 px-1.5 py-0.5 rounded
                     bg-helix-accent/90 text-[9px] uppercase tracking-wider"
        >
          {agentSpeaking}
        </motion.div>
      )}
      <Handle type="source" position={Position.Right} className="!bg-white/30 !w-1.5 !h-1.5" />
    </motion.div>
  );
}
```

### 9.5 The typed WS client

```ts
// apps/web/src/lib/ws.ts
import { useGraphStore } from "./store/graph";
import { useReasoningStore } from "./store/reasoning";

type ServerEvent =
  | { type: "graph.snapshot"; payload: GraphSnapshot }
  | { type: "graph.delta";    payload: GraphDelta }
  | { type: "agent.token";    agent: string; nodeId?: string; text: string }
  | { type: "agent.opinion";  agent: string; opinion: AgentOpinion }
  | { type: "blast.tick";     impacts: Record<string, number>; tMin: number }
  | { type: "incident.new";   incident: Incident };

export class HelixWS {
  private ws?: WebSocket;
  private retry = 0;
  constructor(private url: string) {}

  connect() {
    this.ws = new WebSocket(this.url);
    this.ws.onmessage = (m) => {
      const ev: ServerEvent = JSON.parse(m.data);
      this.route(ev);
    };
    this.ws.onclose = () => {
      const wait = Math.min(8000, 250 * 2 ** this.retry++);
      setTimeout(() => this.connect(), wait);
    };
    this.ws.onopen = () => { this.retry = 0; };
  }

  private route(ev: ServerEvent) {
    switch (ev.type) {
      case "graph.snapshot": useGraphStore.getState().replaceSnapshot(ev.payload); break;
      case "graph.delta":    useGraphStore.getState().applyDelta(ev.payload); break;
      case "agent.token":    useReasoningStore.getState().pushToken(ev.agent, ev.text, ev.nodeId); break;
      case "agent.opinion":  useReasoningStore.getState().pushOpinion(ev.agent, ev.opinion); break;
      case "blast.tick":     useGraphStore.getState().setBlastFrame(ev.tMin, ev.impacts); break;
      case "incident.new":   /* toast + sidebar */ break;
    }
  }
}
```

### 9.6 Rendering performance

At 500+ nodes React Flow degrades. Mitigations:

1. **Cluster non-critical nodes** below a zoom threshold. POS terminals collapse into a single region node until zoomed.
2. **Memoize node components** aggressively; only re-render on metric delta beyond 5%.
3. **Throttle graph deltas** to 4Hz; coalesce on the backend, not the frontend.
4. **Use React Flow's `onlyRenderVisibleElements`** + virtualization.

---

## 10. Module 6 — Backend Architecture

### 10.1 Core principles

- **Async everywhere.** No sync I/O on the request path.
- **Event-driven core.** Most state changes go through Redis Streams, not direct calls.
- **Service composition through DI.** FastAPI `Depends` for everything testable.
- **Streaming first-class.** WebSocket and SSE are not afterthoughts.

### 10.2 The app skeleton

```python
# packages/api/src/helix_api/main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from helix_api.routes import telemetry, graph, agents, incidents, simulate, memory
from helix_api.ws.manager import WSManager
from helix_api.bootstrap import wire_services

@asynccontextmanager
async def lifespan(app: FastAPI):
    svc = await wire_services()
    app.state.svc = svc
    await svc.event_loop.start()
    yield
    await svc.event_loop.stop()

app = FastAPI(title="TITAN HELIX", version="1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

app.include_router(telemetry.router, prefix="/api/v1/telemetry", tags=["telemetry"])
app.include_router(graph.router,     prefix="/api/v1/graph",     tags=["graph"])
app.include_router(agents.router,    prefix="/api/v1/agents",    tags=["agents"])
app.include_router(incidents.router, prefix="/api/v1/incidents", tags=["incidents"])
app.include_router(simulate.router,  prefix="/api/v1/simulate",  tags=["simulate"])
app.include_router(memory.router,    prefix="/api/v1/memory",    tags=["memory"])

ws_manager = WSManager()

@app.websocket("/ws/mesh")
async def mesh_socket(websocket):
    await ws_manager.connect(websocket, channel="mesh")
```

### 10.3 The event bus

Redis Streams, one stream per topic. Consumers use consumer groups for horizontal scale.

```python
# packages/core/src/helix_core/topics.py
TELEMETRY_RAW    = "helix.telemetry.raw"
GRAPH_DELTAS     = "helix.graph.deltas"
AGENT_REASONING  = "helix.agent.reasoning"
AGENT_OPINIONS   = "helix.agent.opinions"
BLAST_FRAMES     = "helix.blast.frames"
INCIDENTS_NEW    = "helix.incidents.new"
```

Anything that wants to react to telemetry — agents, graph inferencer, dashboards — subscribes to `helix.telemetry.raw` independently. Adding a new consumer doesn't touch the producer.

### 10.4 WebSocket fan-out

```python
# packages/api/src/helix_api/ws/manager.py
import asyncio, json
from collections import defaultdict
from fastapi import WebSocket

class WSManager:
    def __init__(self):
        self._conns: dict[str, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket, *, channel: str):
        await ws.accept()
        async with self._lock:
            self._conns[channel].add(ws)
        try:
            while True:
                # keepalive; clients may also send filters
                msg = await ws.receive_text()
                # parse and apply filter
        except Exception:
            pass
        finally:
            async with self._lock:
                self._conns[channel].discard(ws)

    async def broadcast(self, channel: str, message: dict):
        dead = []
        data = json.dumps(message)
        for ws in list(self._conns[channel]):
            try:
                await ws.send_text(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            async with self._lock:
                self._conns[channel].discard(ws)
```

A background task subscribes to Redis topics and calls `broadcast`. The HTTP/WS layer never directly knows about Redis.

### 10.5 Sample route — kick off an investigation

```python
# packages/api/src/helix_api/routes/agents.py
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from helix_api.deps import get_mesh, get_ws
from helix_agents.runtime.graph import build_mesh

router = APIRouter()

class InvestigateReq(BaseModel):
    node_id: str
    reason: str | None = None

@router.post("/investigate")
async def investigate(req: InvestigateReq, mesh = Depends(get_mesh), ws = Depends(get_ws)):
    state = {"trigger": {"kind": "user_investigate",
                          "node_id": req.node_id, "reason": req.reason},
             "observations": [], "opinions": [], "transcript": []}
    async def stream():
        async for chunk in mesh.astream(state):
            await ws.broadcast("mesh", {"type": "agent.opinion", **chunk})
    import asyncio
    asyncio.create_task(stream())
    return {"status": "investigation_started", "node_id": req.node_id}
```

---

## 11. Module 7 — Operational Time Simulation

### 11.1 Two simulation modes

1. **Past replay** — scrub through a historical incident, watch the graph evolve, see when each agent would have spoken. Built on Splunk `_time`-bucketed queries.
2. **Future projection** — pick a "what if" (e.g., "what if `feature-store-db` goes down right now") and run the propagation engine forward.

### 11.2 Future projection — backend

```python
# packages/api/src/helix_api/routes/simulate.py
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from helix_graph.propagation import simulate_blast_radius
from helix_api.deps import get_graph_store

router = APIRouter()

class SimReq(BaseModel):
    origin_node: str
    horizon_min: int = 60
    tick_min: int = 5

@router.post("/future")
async def future(req: SimReq, store = Depends(get_graph_store)):
    snapshot = await store.latest()
    timeline = simulate_blast_radius(
        snapshot.networkx,
        origin=req.origin_node,
        horizon_min=req.horizon_min,
        tick_min=req.tick_min,
    )
    # Translate node impacts to *business impact*
    business = _to_business_impact(timeline, snapshot)
    return {"timeline": timeline, "business": business}

def _to_business_impact(timeline, snapshot):
    """Translate per-node probs to user-facing claims."""
    out = []
    for frame in timeline:
        affected_pos = sum(1 for h in snapshot.hosts
                           if h["kind"] == "pos" and
                              frame["impacts"].get("svc:pos-gateway", 0) > 0.5)
        out.append({
            "t_minutes": frame["t_minutes"],
            "claims": [
                f"{affected_pos:,} POS terminals likely offline"
                    if affected_pos else None,
                "Payment processing >50% degraded"
                    if frame["impacts"].get("svc:payment-orchestrator", 0) > 0.5 else None,
            ]
        })
    return out
```

The UI binds a slider to `t_minutes`. As you drag, the graph lights up. The narrative pane on the right writes itself: *"In 30 minutes: 2,140 POS terminals offline. Payment processing >50% degraded. Recommend pre-emptive remediation."*

---

## 12. Module 8 — Productization Roadmap

### 12.1 From hackathon to product

| Phase | Timeline | What ships | What it costs |
|---|---|---|---|
| **Hackathon MVP** | now | Synth + Splunk + 4 agents + graph + UI, single tenant | 1 engineer × 3 weeks |
| **Design Partner** | +3 mo | Real Splunk integration, RBAC, SSO, 9 agents, MCP server public | 3 engineers × 3 mo |
| **Closed Beta** | +6 mo | Multi-tenant, OTel ingestion alongside Splunk, plugin SDK | 6 engineers + 1 PM |
| **GA** | +12 mo | SOC2, multi-cloud, marketplace, public MCP tools registry | 12+ |

### 12.2 Multi-tenancy

- **Tenant isolation at the index level** for Splunk: `helix_<tenant>_metrics`. Search filters injected at the SPL validator layer (`index=helix_<tenant>_* `).
- **Graph store per tenant** — NetworkX in-process won't scale; move to Neo4j with `tenant_id` as a mandatory label.
- **Agent context per tenant** — separate vector indexes for episodic memory. No cross-tenant retrieval, ever.

### 12.3 RBAC model

Three primitives:
- **Roles:** Viewer, Investigator, Operator, Admin
- **Scopes:** by business_unit, region, tier
- **Capabilities:** read graph, run agents, approve remediations, manage tools

Stored in `helix_<tenant>_rbac` index for full audit.

### 12.4 SIEM / SOAR / MCP ecosystem positioning

- **SIEM:** ingest from Splunk ES, Sentinel, Chronicle. Helix's Security Agent becomes a tier-2 analyst, not a replacement.
- **SOAR:** Helix proposes plans; SOAR (Phantom, XSOAR) executes them. The `runbook_execute` tool is the SOAR bridge.
- **MCP ecosystem:** publish the Helix MCP server to the official MCP registry. Make external Claude/GPT clients first-class operators. Bring-your-own-agent.

### 12.5 Differentiator one-liners (for the keynote slide)

- *"Your topology, rebuilt every 30 seconds from raw telemetry."*
- *"Watch the AI argue with itself before it touches your prod."*
- *"Blast radius before blast."*
- *"MCP-native. Bring your own agent."*
- *"Splunk is the memory. Helix is the mind."*

### 12.6 Monetization

- **Per-host telemetry tier** (the Splunk-y option, defensible).
- **Per-agent-investigation tier** (consumption-based, AI-cost-aligned).
- **Marketplace revenue share** on third-party MCP tools, plugins, scenarios.
- **Enterprise add-ons:** SOC2 pack, on-prem deployment, custom agent training.

---

## 13. Cross-cutting concerns

### 13.1 Configuration

Pydantic-Settings, env-driven, validated at boot. **No string literals for endpoints in code, ever.**

```python
# packages/core/src/helix_core/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import HttpUrl

class HelixSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="HELIX_", env_file=".env")

    splunk_hec_url: HttpUrl
    splunk_hec_token: str
    splunk_api_url: HttpUrl
    splunk_api_user: str
    splunk_api_password: str

    redis_url: str = "redis://localhost:6379/0"

    llm_provider: str = "anthropic"     # or "openai"
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    llm_default_model: str = "claude-opus-4-7"

    scenario_default: str = "checkout_collapse"
    synth_tick_hz: float = 4.0
    synth_seed: int = 42

    mcp_server_socket: str = "stdio"
    mcp_audit_index: str = "helix_audit"
```

### 13.2 Observability of the observability platform

Yes, Helix monitors itself. `helix_self_metrics` index. Agent latency, LLM cost, MCP call rate, graph staleness — all visible in a Helix-on-Helix dashboard. The demo punchline: *"and yes, it detected its own slow node before we did."*

### 13.3 Testing strategy

- **Scenario replay tests** — every scenario is a snapshot test. Run scenario X, assert agents reach conclusion Y within Z LLM calls.
- **Graph inference golden tests** — known traces → known graph. Edge recall ≥ 0.9.
- **SPL validator unit tests** — adversarial inputs. The validator is the most security-critical code in the system.
- **LLM-as-judge eval** — for agent reasoning quality, score against a rubric (faithfulness to evidence, no hallucinated services).

### 13.4 Security

- All MCP tools audited. No exceptions.
- SPL validator runs **before** anything hits Splunk.
- `requires_approval=True` tools never auto-execute; Governance Agent has veto.
- LLM outputs treated as **untrusted input** — no `eval`, no shell, no SQL ever from a model response without schema validation.
- Tenant-scoped index access enforced at the validator.

---

## 14. Hackathon Execution Plan

Assume one experienced engineer, 21 days, aggressive scope.

### Week 1 — Foundation
- **Day 1–2:** Repo scaffold, docker-compose with Splunk + Redis + FastAPI + Vite. `make demo` boots everything.
- **Day 3:** `helix_core` schemas, event envelope, topics, config.
- **Day 4–5:** Synthetic generator world model + metrics + logs generators. HEC sink. First events landing in Splunk.
- **Day 6–7:** First scenario (`checkout_collapse`) end-to-end. Orchestrator. Dashboards confirm pattern.

### Week 2 — Intelligence
- **Day 8–9:** Splunk search wrapper, SPL library, SPL validator with adversarial tests.
- **Day 10:** MCP server with `splunk_search` + `graph_query` tools.
- **Day 11–12:** Observer + Correlation + Topology + Prediction agents. LangGraph wiring. End-to-end: trigger → 4 agents → opinion list.
- **Day 13:** Memory agent + Splunk-backed episodic store. Recall on incident triggers.
- **Day 14:** Graph inferencer L1 + L2 + blast radius propagation. NetworkX → JSON exporter.

### Week 3 — Experience
- **Day 15–16:** React Flow canvas. Custom service node. Live updates over WS.
- **Day 17:** Reasoning panel — streaming agent tokens, debate transcript, SPL provenance.
- **Day 18:** Blast radius overlay + timeline scrubber.
- **Day 19:** Simulate mode + business impact translation.
- **Day 20:** Polish. Editorial-terminal theme. Hotkeys. Loading shimmers. Empty states. Recorded demo paths.
- **Day 21:** Dress rehearsal. Demo script. Resilience: what if the LLM is slow, what if Splunk is down — graceful degradation paths.

### Demo script (90 seconds)

1. (0:00) Open command center. Mesh is green. Synthetic POS traffic flowing. *"127 services, 4 regions, 11,400 POS terminals. Live."*
2. (0:15) Trigger `checkout_collapse` scenario. *"Now I'm injecting a real-world cascading failure. The AI doesn't know what's coming."*
3. (0:25) Watch nodes turn amber, then red. Edges thicken where errors flow.
4. (0:35) The Observer Agent fires. Tokens stream into the reasoning panel.
5. (0:45) Memory Agent recalls a similar incident from 'last quarter'.
6. (0:55) Correlation and Topology agents disagree. Debate transcript appears. They reach consensus.
7. (1:05) Prediction agent runs. Blast radius animates outward. *"In 34 minutes, 2,140 POS terminals offline across APAC-South."*
8. (1:20) Remediation panel: ranked actions, SPL provenance behind each.
9. (1:30) *"We didn't write a single dashboard. We wrote a mind."*

---

## 15. Appendix — Sample telemetry payloads

### A1. Infra metric (CPU)
```json
{ "time": 1730462400.0, "host": "checkout-api-7f5d8b6f9c-lx92q",
  "sourcetype": "helix:metrics:cpu", "index": "helix_metrics",
  "event": { "ts": 1730462400.0, "service": "checkout-api",
             "region": "us-east-2", "az": "use2-az2", "kind": "pod",
             "cpu_pct": 78.4 } }
```

### A2. App log (cascading error)
```json
{ "time": 1730462401.812, "host": "checkout-api-7f5d8b6f9c-lx92q",
  "sourcetype": "helix:logs:app", "index": "helix_logs",
  "event": { "ts": 1730462401.812, "service": "checkout-api",
             "region": "us-east-2", "level": "ERROR",
             "trace_id": "8a31f9e0c2b14a5e9d7f6e3a2b1c0d4e",
             "span_id": "f3e2d1c0b9a8",
             "downstream": "fraud-scoring",
             "message": "downstream fraud-scoring timeout after 1500ms; circuit-breaker OPEN",
             "http_status": 503,
             "request_id": "req_01HRPK4N7T",
             "deployment": "checkout-api@v2.41.3" } }
```

### A3. Distributed trace span
```json
{ "time": 1730462401.612, "host": "checkout-api-7f5d8b6f9c-lx92q",
  "sourcetype": "helix:traces:span", "index": "helix_traces",
  "event": { "ts": 1730462401.612,
             "trace_id": "8a31f9e0c2b14a5e9d7f6e3a2b1c0d4e",
             "span_id": "f3e2d1c0b9a8", "parent_span_id": "a1b2c3d4e5f6",
             "service": "fraud-scoring", "parent_service": "checkout-api",
             "operation": "POST /score",
             "duration_ms": 1503, "status": "ERROR",
             "tags": { "user_tier": "gold", "region": "us-east-2" } } }
```

### A4. ServiceNow-shaped incident
```json
{ "time": 1730462500.0, "sourcetype": "helix:incidents:servicenow",
  "index": "helix_incidents",
  "event": { "number": "INC0123456", "ts": 1730462500.0,
             "short_description": "Elevated checkout API errors in us-east-2",
             "category": "Application", "subcategory": "Availability",
             "priority": "2", "severity": "2", "state": "New",
             "assignment_group": "Payments-SRE",
             "cmdb_ci": "checkout-api",
             "u_region": "us-east-2",
             "u_source": "helix-prediction-agent",
             "u_confidence": 0.82 } }
```

### A5. Deployment event
```json
{ "time": 1730459000.0, "sourcetype": "helix:deploy:event",
  "index": "helix_deploy",
  "event": { "ts": 1730459000.0, "service": "checkout-api",
             "version": "v2.41.3", "previous": "v2.41.2",
             "rollout": "canary", "canary_pct": 25,
             "actor": "ci-bot", "pipeline": "checkout-api-prod",
             "change_id": "CHG0098234" } }
```

### A6. Security event
```json
{ "time": 1730462600.0, "sourcetype": "helix:logs:security",
  "index": "helix_security",
  "event": { "ts": 1730462600.0, "kind": "auth_anomaly",
             "user_id_hash": "a7c2…", "service": "auth-service",
             "region": "ap-south-1", "ip": "203.0.113.42",
             "country": "IN", "expected_country": "SG",
             "score": 0.91, "action": "step_up_mfa" } }
```

### A7. Business KPI
```json
{ "time": 1730462700.0, "sourcetype": "helix:metrics:business",
  "index": "helix_business",
  "event": { "ts": 1730462700.0,
             "metric": "checkout_completion_rate",
             "value": 0.687, "baseline": 0.972,
             "region": "us-east-2", "business_unit": "commerce" } }
```

### A8. Agent reasoning audit
```json
{ "time": 1730462450.0, "sourcetype": "helix:agent:reasoning",
  "index": "helix_audit",
  "event": { "ts": 1730462450.0, "agent": "correlation",
             "investigation_id": "inv_01HRPK4N7T",
             "claim": "feature-store-db CPU saturation is causal for fraud-scoring timeouts",
             "confidence": 0.78,
             "evidence": {
               "spl_used": ["index=helix_metrics sourcetype=helix:metrics:cpu host=feature-store-db-vm-* earliest=-30m@m"],
               "lead_lag_seconds": 90,
               "correlation_coef": 0.84
             },
             "model": "claude-opus-4-7", "tokens": 2104, "cost_usd": 0.0312 } }
```

---

## 16. Closing — Why this works

TITAN HELIX wins because each layer has a **single, sharp identity**:
- Synth is a *liar with internal consistency.*
- Splunk is *durable truth.*
- Agents are *opinionated specialists.*
- The graph is *living evidence.*
- MCP is *the universal verb.*
- The frontend is *cinema for operators.*

Nothing in this architecture is unbuildable in three weeks. Nothing in it is throwaway in three years. That's the test of a good system.

When the demo ends, the line to remember is:

> *"Every other platform shows you what broke. Helix shows you what's about to."*

— end of document —
