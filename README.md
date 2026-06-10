# 🌐 TITAN HELIX

### Autonomous AI Operational Intelligence Mesh — *a neural network for your enterprise*

![License: MIT](https://img.shields.io/badge/license-MIT-FF6B35)
![Platform: Splunk](https://img.shields.io/badge/platform-Splunk-38BDF8)
![AI: MCP + Agent Mesh](https://img.shields.io/badge/AI-MCP%20%2B%20Agent%20Mesh-818CF8)
![Stack: FastAPI · SVG · Docker](https://img.shields.io/badge/stack-FastAPI%20·%20Docker-34D399)

> **Every enterprise sits on a dependency graph it can't see.** TITAN HELIX makes that graph
> visible, then puts a mesh of reasoning agents on top of it — agents that watch live Splunk
> telemetry, find a failure's *true* root cause, predict its blast radius, and recommend (or take)
> the fix. Built for the **Splunk Agentic Ops Hackathon**.

**▶ Live demo (no install):** `https://<your-username>.github.io/<repo>/`  ·  **🎬 [Architecture diagram](docs/architecture.svg)**  ·  **⚙ [Quickstart](#-quickstart-one-command)**

---

## 🎯 The problem

When a modern system fails, the alerts fire on the *symptom*, not the *cause*. Checkout starts
throwing 503s and twelve dashboards light up red — but the real culprit is a database three hops
upstream whose CPU is quietly saturating while still returning `200 OK`. Error-rate alerting never
sees it. On-call engineers burn the first 30 minutes of an incident just **drawing the dependency
map in their heads** and arguing about which red thing started it.

## 💡 What TITAN HELIX does

It generates a realistic, ground-truth enterprise (29 services, ~1,429 hosts) emitting metrics,
logs, W3C traces, ServiceNow incidents, deploys and KPIs into **Splunk** — then runs a **six-agent
reasoning mesh** over that live data:

| Agent | Job |
|-------|-----|
| **Observer** | Detects the leading anomaly (e.g. silent CPU saturation, *before* errors appear) |
| **Memory** | Recalls a near-identical past incident and how it was resolved |
| **Correlation** | Proves which red service is a *symptom* and which is the *cause* |
| **Prediction** | Forecasts the blast radius — what fails next, and where |
| **Remediation** | Ranks the fix with confidence |
| **Executive** | Issues the verdict, with the SPL evidence behind every claim |

The agents reach Splunk through the **Model Context Protocol (MCP)** — a standard tool fabric — and
render a **live, AI-inferred dependency graph** with blast-radius prediction, a full reasoning
trail, and an **autonomous closed loop** (detect → reason → remediate → verify).

## 🎬 See it in 60 seconds

Open the **live demo** (link above) — it auto-plays a `checkout_collapse` incident:

1. A healthy 29-node graph. The root cause (`feature-store-db`) **reddens first while error-free** — the silent failure normal tools miss.
2. The cascade propagates in true dependency order across **five services**, with a live phase timeline + countdown.
3. The **AI Reasoning** panel reveals all six agents reaching the verdict, each citing its SPL.
4. Click any completed phase to **scrub the graph back** to that moment.

No backend, no setup — it runs entirely in the browser.

---

## 🏆 Why this wins — mapped to the four judging criteria

The four criteria are weighted equally; here's how TITAN HELIX scores on each.

### 🧩 Quality of the Idea — *creative & unique*
Most AIOps tools **correlate and alert**. TITAN HELIX is the first to make the AI's **reasoning
itself the product** — you watch six specialized agents debate, cite evidence, and converge, the way
a senior SRE war-room would. The unique twist that lands with judges: a **synthetic ground-truth
world**. Because we control the scenario, we have an **answer key** — we can *prove* the AI reached
the correct root cause, not just plausibly-worded output. And it's the rare project that demonstrates
the **silent-failure insight**: the root cause is CPU-bound but error-free, so it slips past every
error-rate alert — exactly the failure mode real incidents are made of.

### 🛠 Technological Implementation — *quality software*
A genuinely full stack, all open source: a deterministic **synthetic telemetry generator** with a
hidden ground-truth topology → **Splunk** (HEC ingest, 7 purpose-built indexes, SPL) → a
**LangGraph-orchestrated agent mesh** that runs against live Splunk and works **deterministically with
zero keys** *or* with real **Claude** reasoning → exposed over the **Model Context Protocol**, the
emerging open standard for tool-using AI. A **FastAPI** backend, a dependency-free vanilla-JS
console with a self-written force-directed graph, and a **one-command, idempotent `setup.sh`** plus a
**`preflight.sh`** go/no-go gate. It's reproducible: `git clone && ./setup.sh`.

### 🎨 Design — *thoughtful UX*
An editorial, re:Invent-grade dark UI. The graph is **interactive** — hover for telemetry, click to
drill down, watch nodes redden in real time. Critically, **Live and Demo are cleanly separated**: the
Live tab is honest real Splunk data; the Demo tab is a deterministic, always-works incident with the
graph, phase timeline, and AI moving in perfect lockstep — and a transparent "synthetic data" badge so
a judge always knows what they're seeing. The reasoning is **legible**: agents reveal one by one with
confidence bars and collapsible SPL evidence.

### 🌍 Potential Impact — *how big*
Incident response is one of the most expensive, highest-stress problems in every enterprise that runs
Splunk — and MTTR is dominated by *diagnosis*, not repair. An agent mesh that names the true root
cause and blast radius in seconds, **natively on the data teams already have**, attacks that directly.
Because it's **Splunk-native and MCP-standard**, it drops into existing deployments instead of adding
another monitoring silo — and the autonomous closed loop points at a future where routine incidents
resolve themselves.

> **The one-liner for the pitch:** *"It's not another dashboard that tells you something's wrong —
> it's an AI war-room that tells you **why**, **what's next**, and **how to fix it**, and shows its work."*

---

## 🗺 Architecture

**[▶ Open the animated architecture diagram → `docs/architecture.svg`](docs/architecture.svg)** *(opens animated in a browser; editable in Inkscape)*

```
 PAYLOAD ORIGINS ─▶ INGESTION (ALB→HEC) ─▶  SPLUNK DATA PLANE  ─▶  AI AGENT MESH ─▶ EXPERIENCE & ACTION
 metrics·logs·traces                         EC2 · 7 indexes · SPL     (LangGraph hub        console · blast radius
 incidents·deploys·KPIs                       │      ▲                  + 6 agents)           remediation
                                              │      │                      ▲ │                    │
                                              ▼      │ MCP ▸ SPL query       │ ▼  tool calls        ▼  autonomous
                                       ┌──────────────────────────────────────────────┐      ServiceNow INC +
                                       │   MODEL CONTEXT PROTOCOL · tool fabric (bus)   │◀──── hotfix deploy
                                       │ search_spl · get_service · blast_radius · …    │   (closed loop ↺ back to origins)
                                       └──────────────────────────────────────────────┘
```

**How it interacts with Splunk:** telemetry is ingested via **HEC** into seven indexes
(`helix_metrics, helix_logs, helix_traces, helix_incidents, helix_deploy, helix_business, helix_audit`);
the backend and agents query Splunk over its **REST/SPL** API; the live console renders the dependency
graph and drill-downs straight from SPL results.

**How AI is integrated:** the agent mesh reasons over that live Splunk data and reaches Splunk through
the **Model Context Protocol** — Splunk search/fetch is exposed as typed MCP tools, so the AI calls
`search_spl()`, `get_service()`, `blast_radius()` etc. rather than hard-coded glue. Reasoning runs
**deterministically** (computed from the data) by default, or with a real **LLM (Claude)** when an
API key is provided.

---

## ⚙ Quickstart (one command)

```bash
git clone <your-repo-url> titan-helix
cd titan-helix
./setup.sh
```

`setup.sh` verifies prerequisites, brings up **Splunk in Docker** (persistent across reboots),
configures HEC + the seven indexes, creates a Python venv, loads a week of historical telemetry, and
starts the API. First run takes a few minutes (Splunk's first boot); re-runs take seconds. Requires
**Docker**, **Python 3.10+**, ~4 GB RAM.

Then open:

| URL | What |
|-----|------|
| **http://localhost:8080/stage** | **Presenter shell** — `Live · real data ⇄ Demo · scripted` (keys `L` / `D`) |
| http://localhost:8080/ | Live console (real Splunk data) |
| http://localhost:8080/demo | Scripted incident cascade (no backend data needed) |
| http://localhost:8000 | Splunk UI (`admin` / `ChangeMe_Helix_2026`) |

**Before presenting**, run the go/no-go gate:

```bash
./preflight.sh        # checks data is loaded, the AI returns a full chain, all pages serve
```

See **[PREFLIGHT.md](PREFLIGHT.md)** for the visual pass + 60-second demo script.

### Optional — real Claude reasoning

The mesh runs without any key (deterministic). For genuine LLM reasoning, add an Anthropic API key
(from [console.anthropic.com](https://console.anthropic.com), separate from a Claude.ai subscription)
to `.helix.env`, then re-run `./setup.sh`:

```bash
export HELIX_LLM_API_KEY=sk-ant-...
export HELIX_LLM_PROVIDER=anthropic
export HELIX_LLM_MODEL=claude-sonnet-4-6
```

---

## 🚀 Deploy the live demo to GitHub Pages

`demo.html` is fully static, so it hosts on **GitHub Pages** for a public, zero-install judge link
(works on Free for public repos; your Pro plan also allows private). Steps:

1. Push the repo to GitHub (public).
2. For the cleanest URL, copy the demo to the site root:
   ```bash
   cp demo.html index.html && git add index.html && git commit -m "Pages: demo as index" && git push
   ```
3. Repo **Settings → Pages → Build and deployment → Source: Deploy from a branch → `main` / root → Save.**
4. After ~1 minute your live demo is at **`https://<your-username>.github.io/<repo>/`**
   (or `…/demo.html` if you skipped step 2).

> Only the **scripted demo** runs on Pages (it needs no server). The live console and `/stage` require
> the local backend — run those with `./setup.sh`.

---

## 🧰 Tech stack

**Splunk** (HEC, indexes, SPL) · **Model Context Protocol** · **LangGraph** agent orchestration ·
**Anthropic Claude** (optional LLM reasoning) · **FastAPI** + **Uvicorn** · **Docker** · vanilla-JS
console with a hand-written force-directed graph · animated **SVG** architecture · **Bash** automation.

## 📁 Project layout

```
titan-helix/
├── setup.sh / preflight.sh     one-command setup · pre-demo go/no-go gate
├── README.md · LICENSE · MANIFEST.md · PREFLIGHT.md
├── agents.py                   the 6-agent reasoning mesh
├── synth_generator.py          live telemetry generator (drives the scenario)
├── historical_generator.py     past telemetry (powers the Memory agent)
├── load_to_splunk.py           HEC batch loader
├── console.html · demo.html · stage.html    live console · scripted demo · presenter shell
├── backend/                    FastAPI: graph, drill-down, /api/investigate, MCP-shaped Splunk access
├── scenarios/checkout_collapse.yaml         the cascade scenario
└── docs/                       architecture.svg (animated) · ARCHITECTURE.md (full design)
```

## 📜 License

[MIT](LICENSE) — open source. Free to use, modify, and build on.

---

*Built for the Splunk Agentic Ops Hackathon · deadline June 15, 2026.*
