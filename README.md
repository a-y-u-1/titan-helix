# TITAN HELIX

**Autonomous AI Operational Intelligence Mesh** — a neural network for your enterprise.

Every enterprise sits on a dependency graph it can't see. TITAN HELIX generates realistic
enterprise telemetry, streams it into Splunk, runs a mesh of reasoning agents over it, and
renders a **live, AI-inferred service dependency graph** with blast-radius prediction and
remediation — so an incident's root cause and ripple effect are visible in seconds.

---

## Quick start (one command)

```bash
git clone <your-repo-url> titan-helix
cd titan-helix
./setup.sh
```

That's it. The script verifies prerequisites, brings up Splunk in Docker, configures HEC and
indexes, creates a Python virtualenv, loads a week of historical telemetry, and starts the API.
First run takes a few minutes (mostly Splunk's first boot); re-runs take seconds.

When it finishes, open:

| URL | What |
|-----|------|
| **http://localhost:8080/stage** | **Presenter shell** — toggle Live ⇄ Demo (keys `L` / `D`) |
| http://localhost:8080/ | Live console (queries Splunk in real time) |
| http://localhost:8080/demo | Scripted demo (no backend data needed — always works) |
| http://localhost:8000 | Splunk UI (`admin` / `ChangeMe_Helix_2026`) |

> **Presenting?** Use `/stage`. It opens in **Live** mode. Press **D** for the scripted
> demo — a "switching to mocked data" notice appears and a persistent badge stays up, so it's
> always transparent that the demo is synthetic. Press **L** to go back to live. The demo
> replays the full cascade in ~40s with the AI reaching its verdict on screen, and works on any
> laptop even with no connection to the backend.

---

## Before you present

Run the pre-flight gate — it confirms not just that services are up, but that the indexes hold
data, the AI returns a full reasoning chain, and all pages serve:

```bash
./preflight.sh
```

It ends in **● GO** or **● NO-GO** with a one-line fix for anything red. Then walk the short
eyeball pass and demo script in **`PREFLIGHT.md`**.

---

## What the demo shows

A `checkout_collapse` incident cascading through a real dependency chain:

```
feature-store-db  (CPU saturates first — error-free, the silent root cause)
   └─ feature-store        (cache misses, latency)
        └─ fraud-scoring   (timeouts → 503s)
             └─ checkout-api  (customer-facing 503s)
                  └─ pos-gateway  (ap-south-1 retail offline)
```

The **AI Reasoning** tab runs a six-agent mesh — Observer, Memory, Correlation, Prediction,
Remediation, Executive — that fingers `feature-store-db` as the root cause, recalls a matching
past incident, predicts the blast radius, and ranks the fix. By default it reasons
deterministically from the data (no API key). For genuine LLM reasoning, see below.

---

## Optional: real Claude reasoning in the AI tab

The agent mesh runs without any API key (deterministic, data-driven). To switch it to genuine
LLM reasoning, add an **Anthropic API key** (this is the developer API at
[console.anthropic.com](https://console.anthropic.com) — separate from a Claude.ai
subscription) to `.helix.env`:

```bash
export HELIX_LLM_API_KEY=sk-ant-...
export HELIX_LLM_PROVIDER=anthropic
export HELIX_LLM_MODEL=claude-sonnet-4-6
```

Then restart the backend (`./setup.sh`). The AI tab's badge flips from "deterministic" to the
model name. A few dollars of credit covers far more investigations than you'll run.

---

## Useful commands

```bash
./setup.sh --check         # verify everything is healthy, change nothing
./setup.sh --reload-data   # regenerate + reload the historical dataset
./setup.sh --wipe          # nuke the Splunk container + volumes and rebuild clean
./setup.sh --no-backend    # set up but don't launch the API
./setup.sh --install-service   # auto-start the API on boot via systemd

tail -f backend.log              # watch the API
kill $(cat .helix.backend.pid)   # stop the API
docker logs helix-splunk --tail 50   # Splunk logs
```

Splunk persists across reboots (named Docker volumes + `--restart unless-stopped`). After a
reboot just run `./setup.sh` again and the stack is back in seconds. Add `--install-service`
once if you also want the API to come up automatically on boot.

---

## Architecture (at a glance)

```
synth_generator.py ─┐
historical_gen.py  ─┼─► Splunk (HEC) ─► backend/app.py ─► console.html / demo.html / stage.html
agents.py (mesh) ◄──┘     indexes        FastAPI + SPL        live graph · AI tab · SPL provenance
```

- **`synth_generator.py`** — live telemetry generator (metrics, logs, W3C traces, ServiceNow
  incidents, deploys, KPIs) with a hidden ground-truth topology of 29 services.
- **`historical_generator.py`** — downsampled past telemetry with embedded resolved incidents
  (powers the Memory agent's recall).
- **`agents.py`** — the reasoning mesh; deterministic by default, LLM-backed with a key.
- **`backend/app.py`** — FastAPI: dependency graph, drill-downs, incidents, SPL provenance,
  cascade injection, and the `/api/investigate` agent endpoint.
- **`console.html` / `demo.html` / `stage.html`** — live console, scripted demo, presenter shell.

See `docs/ARCHITECTURE.md` for the full design.

---

## Requirements

Docker, Python 3.10+, and ~4 GB free RAM for Splunk. `setup.sh` installs the rest
(`fastapi`, `uvicorn`, `requests`, `pyyaml`) into a local virtualenv.
