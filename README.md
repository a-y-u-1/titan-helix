＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿

```
  ████████ ██ ████████  █████  ███   ██     ██   ██ ███████ ██      ██ ██   ██
     ██    ██    ██    ██   ██ ████  ██     ██   ██ ██      ██      ██  ██ ██
     ██    ██    ██    ███████ ██ ██ ██     ███████ █████   ██      ██   ███
     ██    ██    ██    ██   ██ ██  ████     ██   ██ ██      ██      ██  ██ ██
     ██    ██    ██    ██   ██ ██   ███     ██   ██ ███████ ███████ ██ ██   ██
```

**An autonomous reasoning mesh that sits on your Splunk data and explains failures while they unfold.**

[ live demo ](https://your-username.github.io/your-repo/) · [ architecture ](docs/architecture.svg) · [ run it ](#run-it)

＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿

The incident always starts before the alert.

A feature-store database drifts to 94% CPU. It is slow, not broken — every query still returns
`200 OK`, so error-rate alerting stays quiet. Ninety seconds later fraud-scoring times out,
checkout-api begins returning 503s, point-of-sale terminals in one region go dark, and a ServiceNow
page wakes someone up. They spend the first half hour of the outage doing what humans do: redrawing
the dependency graph from memory and arguing about which red box started it.

TITAN HELIX watched the whole thing. It can already tell you the database was the cause — back when
it was still answering `200`.

## What it is

A synthetic but fully-built enterprise — 29 services, ~1,429 hosts — streams metrics, logs, W3C
traces, deploys, ServiceNow incidents and revenue KPIs into Splunk in real time. On top of that data
runs a mesh of six reasoning agents. They do not stop at correlation and a red dot; they argue toward
a conclusion the way a good war room does, and they leave the evidence on the table.

    observer      finds the leading signal — the silent CPU climb, before a single error
    memory        pulls the near-identical incident from six weeks ago, and how it was closed
    correlation   walks the call graph and shows checkout-api is a symptom, not the cause
    prediction    calls the regional POS plane as the next domino, and roughly when
    remediation   ranks the fix by confidence
    executive     writes the verdict — with the exact SPL behind every line of it

The agents never reach into Splunk with hand-wired queries. They call it through the Model Context
Protocol — `search_spl()`, `get_service()`, `blast_radius()` — the same open tool standard a model
would use to touch any system. Replace the synthetic world with a real Splunk deployment and the
reasoning layer above it does not change a line.

## Watch it

→ **https://your-username.github.io/your-repo/** — opens in a browser, plays on its own, installs nothing.

It runs the `checkout_collapse` incident end to end in about forty seconds:

    the graph is green — then feature-store-db turns red first, while its error rate is still zero
    the failure spreads in dependency order across five services, a phase clock counting down beside it
    the reasoning panel fills one agent at a time and lands on the verdict, each step carrying its SPL
    when it settles, click any phase on the timeline and the graph scrubs back to that exact second

The incident is explorable, not a recording. That is the part screenshots can't carry.

## How it works

The generator holds a hidden topology — the real call graph and a known root cause — and emits
telemetry that obeys it, including the awkward truth that a saturating database stays error-free for
a while. Events land in Splunk over HEC across seven indexes (`helix_metrics`, `helix_logs`,
`helix_traces`, `helix_incidents`, `helix_deploy`, `helix_business`, `helix_audit`). The backend and
the agents read it back over SPL; the console draws the dependency graph and every drill-down
straight from those query results.

The mesh runs in two modes, and the panel always says which one is live. With no key it reasons
**deterministically** — every conclusion is computed from the actual numbers (the CPU curve, the
trace timings, the incident history) and written out in plain language. Hand it an Anthropic key and
the same evidence goes to **Claude** for the narrative. Nothing is invented. The stage demo is
scripted so it never flinches in front of an audience; the live console runs the genuine mesh against
whatever Splunk is holding.

One choice worth stating plainly, because it usually gets read backwards: the synthetic world is not
a shortcut around real data — it is the proof. The scenario has a known answer, so the system can be
*checked*. It either names `feature-store-db` or it doesn't. Most AI demos can only be plausible;
this one has an answer key, and it hits it every run.

## Architecture

Open **[docs/architecture.svg](docs/architecture.svg)** — it animates in a browser and is editable in
Inkscape or any text editor. The shape of it:

    payload origins ─▶ ingestion ─▶  SPLUNK DATA PLANE  ─▶  AI AGENT MESH ─▶  experience & action
    metrics · logs       ALB → HEC     EC2 · 7 indexes · SPL    LangGraph hub      console · blast radius
    traces · incidents      │            ▲                       + 6 agents          remediation
    deploys · KPIs          │            │ MCP queries SPL          ▲ │                   │
                            ▼            │                          │ ▼ tool calls         ▼  autonomous
                     ┌────────────────────────────────────────────────────┐        ServiceNow incident
                     │   MODEL CONTEXT PROTOCOL · tool fabric               │◀────── + hotfix deploy
                     │   search_spl · get_service · blast_radius · …        │     ( closed loop ↺ to origins )
                     └────────────────────────────────────────────────────┘

Where Splunk sits: it is the system of record. Telemetry enters through HEC, lives in the seven
indexes above, and is queried back over SPL and the REST API — the graph, the service detail, the
incident history are all SPL results, not a side database.

Where the AI plugs in: the mesh reasons over those SPL results and reaches Splunk through MCP, so the
model calls typed tools instead of carrying hard-coded queries. The protocol is the seam — the same
boundary that would let it run against a production Splunk, or expose its tools to any other MCP
client.

## Run it

```
git clone <your-repo-url> titan-helix
cd titan-helix
./setup.sh
```

`setup.sh` is idempotent: it checks prerequisites, brings up Splunk in Docker (persistent across
reboots), wires HEC and the seven indexes, builds a Python venv, loads a week of historical telemetry,
and starts the API. The first run waits on Splunk's first boot — a few minutes; after that it's
seconds. Needs Docker, Python 3.10+, ~4 GB RAM.

    http://localhost:8080/stage    presenter shell — Live (real data) ⇄ Demo (scripted), keys L / D
    http://localhost:8080/         live console, straight off Splunk
    http://localhost:8080/demo     the scripted incident, no backend data required
    http://localhost:8000          Splunk UI — admin / ChangeMe_Helix_2026

Before you show it to anyone:

```
./preflight.sh      # confirms data is loaded, the mesh returns a full chain, every page serves
```

[PREFLIGHT.md](PREFLIGHT.md) has the visual pass and a sixty-second script.

Optional — real Claude reasoning instead of deterministic. Drop an Anthropic key (from
console.anthropic.com, separate from a Claude.ai subscription) into `.helix.env` and re-run setup:

```
export HELIX_LLM_API_KEY=sk-ant-...
export HELIX_LLM_PROVIDER=anthropic
export HELIX_LLM_MODEL=claude-sonnet-4-6
```

## The public demo, on GitHub Pages

`demo.html` is fully self-contained, so it hosts as a static site — a public link a judge can open
cold, nothing to install. Pages is free on public repositories.

```
cp demo.html index.html          # cleanest root URL
git add index.html && git commit -m "pages: scripted demo at root" && git push
```

Then **Settings → Pages → Deploy from a branch → main / root**. A minute later it's live at
`https://your-username.github.io/your-repo/`. Only the scripted demo runs there — the live console and
`/stage` need the local backend from `./setup.sh`.

## Built on

Splunk for ingest, storage and SPL. The Model Context Protocol as the tool seam between model and
data. LangGraph to orchestrate the agents, with Claude behind them when a key is present. FastAPI and
Uvicorn for the backend. A dependency-free vanilla-JS console with a force-directed graph written by
hand. An animated SVG for the architecture. Bash for setup that survives a reboot.

## Map

```
titan-helix/
  setup.sh  preflight.sh        one-command bring-up · pre-demo go/no-go
  agents.py                     the six-agent reasoning mesh
  synth_generator.py            live telemetry, driven by the scenario
  historical_generator.py       past telemetry — what the memory agent recalls
  load_to_splunk.py             HEC batch loader
  console.html  demo.html  stage.html    live · scripted · presenter shell
  backend/                      FastAPI — graph, drill-down, /api/investigate, MCP-shaped Splunk access
  scenarios/checkout_collapse.yaml        the cascade, with its hidden root cause
  docs/                         architecture.svg (animated) · ARCHITECTURE.md (full design)
  README.md  LICENSE  MANIFEST.md  PREFLIGHT.md
```

＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿

MIT-licensed — see [LICENSE](LICENSE). Built for the Splunk Agentic Ops Hackathon.
