# TITAN HELIX — file manifest

The complete, canonical project. Everything the system uses, nothing it doesn't.
This is the single source of truth — if a file isn't listed here, it isn't part of the project.

```
titan-helix/
│
├── setup.sh                  ★ ONE COMMAND. Verifies prereqs, brings up Splunk in Docker,
│                               configures HEC + the 7 indexes, makes a venv, loads data,
│                               starts the backend. Idempotent — safe to re-run.
├── preflight.sh              ★ PRE-DEMO GATE. GO/NO-GO check: data in indexes, AI chain
│                               returns, inject armed, all pages serve. Run before a judge.
├── README.md                   Judge-facing overview + winning strategy + quickstart.
├── LICENSE                     MIT — open source (required: visible license).
├── PREFLIGHT.md                Printable checklist: visual pass + demo script + rebuttals.
├── .gitignore                  Keeps venv / data / logs / .helix.env out of git.
│
├── agents.py                   The AI reasoning mesh — 6 agents (Observer, Memory,
│                               Correlation, Prediction, Remediation, Executive).
│                               Deterministic by default; real Claude with an API key.
├── synth_generator.py          Live telemetry generator (metrics, logs, W3C traces,
│                               ServiceNow incidents, deploys, KPIs). 29-service topology.
│                               Drives the live cascade when you hit Inject.
├── historical_generator.py     N days of downsampled past telemetry, with embedded
│                               resolved incidents (powers the Memory agent's recall).
├── load_to_splunk.py           Batch-loads a JSONL dump into Splunk over HEC.
│
├── console.html                LIVE console — served at  /     (REAL Splunk data, no scripted cascade)
├── demo.html                   SCRIPTED demo — served at  /demo  (the incident cascade; no backend needed)
├── stage.html                  PRESENTER shell — served at /stage (Live ⇄ Demo toggle)
│
├── backend/
│   ├── __init__.py             Marks backend as a package (import-critical).
│   ├── app.py                  FastAPI: /api/graph, /api/service, /api/incidents,
│   │                           /api/simulate (inject), /api/investigate (agent mesh),
│   │                           /api/spl, /health  +  serves the 3 pages above.
│   ├── splunk_client.py        Thin Splunk REST client (reads HELIX_SPLUNK_* env).
│   └── requirements.txt        fastapi · uvicorn · requests · pyyaml  (installed by setup.sh)
│
├── scenarios/
│   └── checkout_collapse.yaml  The 6-phase cascade (root cause: feature-store-db).
│
└── docs/                       Reference only — NOT needed to run the system.
    ├── ARCHITECTURE.md         Full 16-section principal-architect design document.
    └── architecture.svg        Animated 4K architecture diagram (browser-animated, Inkscape-editable).
```

## Generated at runtime (not in the repo — created by setup.sh / on first run)

```
.venv/                 Python virtualenv
.helix.env             Backend env vars (Splunk URL/creds, HEC token) — source of truth
.helix.backend.pid     PID of the running backend (for stop/restart)
backend.log            Backend stdout/stderr
data/history.jsonl     Generated historical dataset
data/.loaded           Marker so setup.sh doesn't reload data every run
```

## Runs in Docker (managed by setup.sh)

```
container:  helix-splunk      (image: splunk/splunk:latest, --restart unless-stopped)
volumes:    helix-splunk-var  (indexed data — persists across reboots/rebuilds)
            helix-splunk-etc  (Splunk config)
ports:      8000 (UI) · 8088 (HEC, https) · 8089 (mgmt API, https)
indexes:    helix_metrics  helix_logs  helix_traces  helix_incidents
            helix_deploy   helix_business  helix_audit
```

## The only commands you need

```bash
./setup.sh            # set up / bring everything up   (re-run any time, incl. after reboot)
./setup.sh --check    # verify everything is healthy, change nothing
./preflight.sh        # GO/NO-GO pre-demo gate (run right before a judge evaluates)
./setup.sh --wipe     # clean rebuild (removes the Splunk container + volumes)
```

Then open **http://localhost:8080/stage**.
