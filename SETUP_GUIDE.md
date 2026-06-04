# TITAN HELIX — Complete Setup Guide
### For Ubuntu **and** Alma Linux / RHEL / Rocky · written for a first-timer

This guide assumes **you have never set this project up before**. Every command
is here. Where Ubuntu and Alma differ, both are shown side by side. Follow it top
to bottom and you'll have a working system.

> **Two ways to read this:**
> - **Fast path** — run `./setup.sh` (Part 3) and skip to Part 6.
> - **Manual path** — do every step yourself (good for understanding / when the
>   script can't run). Parts 3M onward.

---

## Table of contents
0. Concepts (read this first — 2 min)
1. System requirements
2. Get the files in place
3. Fast path: one command
   - 3M. Manual path: install dependencies yourself
4. Install & start Splunk (manual path)
5. Create indexes + configure HEC (manual path)
6. Generate & load HISTORICAL data
7. Stream LIVE telemetry
8. Run the AI agents
9. Run the backend API + open the visuals
10. Verify it all works
11. Troubleshooting (the big one)
12. Demo-day runbook
13. What's built vs. what's next

---

## 0. Concepts (read first)

You're standing up four things that talk to each other:

```
  GENERATORS                SPLUNK                 INTELLIGENCE            UI
  ──────────                ──────                 ────────────            ──
  synth_generator.py  ──►   (telemetry      ──►    agents.py        ──►   browser
  historical_gen.py   ──►    backbone +              backend/app.py        (demo.html
                             memory)                                        + architecture.html)
```

- **Generators** make fake-but-realistic telemetry (logs, metrics, traces,
  incidents). One streams *live*, one backfills *history*.
- **Splunk** stores all of it. It's the single source of truth.
- **agents.py** reads Splunk, reasons about what's wrong, writes conclusions back.
- **backend/app.py** serves the graph + the web UI from Splunk data.

You do **not** need to understand Splunk deeply. You just need it running.

**Key terms:**
- **HEC** = HTTP Event Collector. Splunk's "data inbox." We POST events to it.
- **HEC token** = a password (a UUID) that authorizes writing to HEC.
- **Index** = a Splunk table/bucket. We use `helix_logs`, `helix_metrics`, etc.
- **SPL** = Splunk's query language.

---

## 1. System requirements

| Resource | Minimum | Recommended |
|---|---|---|
| RAM (VM) | 4 GB | 8 GB |
| Disk | 15 GB free | 30 GB |
| CPU | 2 cores | 4 cores |
| OS | Ubuntu 22.04+ / AlmaLinux 8+ / Rocky 8+ / RHEL 8+ | latest |

> **Splunk will not start with less than ~4 GB RAM.** In VirtualBox: power off
> the VM → Settings → System → Base Memory → set to 4096+ MB → also bump
> Processors to 2+. Then boot.

Check your resources:
```bash
free -h          # memory
df -h /          # disk
nproc            # cpu cores
```

---

## 2. Get the files in place

Put the `titan-helix` folder in your **home directory** (`~`). Pick the line that
matches where the folder currently is:

```bash
# If it's in Downloads:
mv ~/Downloads/titan-helix ~/titan-helix

# If it came as a zip:
cd ~/Downloads && unzip titan-helix.zip -d ~/ && cd ~/titan-helix

# If it's on a VirtualBox shared folder:
cp -r /media/sf_<sharename>/titan-helix ~/titan-helix
```

Go into it and confirm the contents:
```bash
cd ~/titan-helix
ls -1
```
You should see (among others): `setup.sh`, `synth_generator.py`,
`historical_generator.py`, `load_to_splunk.py`, `agents.py`, `backend/`,
`demo.html`, `architecture.html`, `index.html`, `scenarios/`.

> **From here on, every command assumes you are inside `~/titan-helix`.**
> If a command "can't find" a file, run `pwd` — it should print
> `/home/<you>/titan-helix`.

---

## 3. Fast path — one command

```bash
cd ~/titan-helix
chmod +x setup.sh
./setup.sh
```

`setup.sh` auto-detects your OS and does everything: installs Python + Docker,
starts Splunk, creates indexes, configures HEC. When it finishes it prints your
Splunk URL, HEC URL, and token.

> If `setup.sh` errors out, don't panic — go to the **Manual path (3M)** below and
> do the steps by hand. The script just automates them.

> **The #1 first-time gotcha — Docker permissions.** After installing Docker,
> your user isn't in the `docker` group *in the current shell* yet. If you see
> `permission denied while trying to connect to the Docker daemon`, fix it:
> ```bash
> newgrp docker          # OR: log out of the desktop and back in
> ./setup.sh             # re-run; it's safe to run again
> ```

**If the fast path worked, skip to Part 6.** Otherwise continue with 3M.

---

## 3M. Manual path — install dependencies yourself

### 3M.1 Update the system

**Ubuntu / Debian:**
```bash
sudo apt-get update && sudo apt-get upgrade -y
```

**Alma / Rocky / RHEL:**
```bash
sudo dnf update -y
# (older systems may use: sudo yum update -y)
```

### 3M.2 Install base tools (curl, git, etc.)

**Ubuntu:**
```bash
sudo apt-get install -y curl jq git ca-certificates gnupg lsb-release
```

**Alma:**
```bash
sudo dnf install -y curl jq git ca-certificates gnupg2
```

### 3M.3 Install Python 3 + pip

**Ubuntu:**
```bash
sudo apt-get install -y python3 python3-pip python3-venv
python3 --version        # expect 3.10+
```

**Alma:**
```bash
sudo dnf install -y python3 python3-pip
python3 --version        # expect 3.9+
```

> Alma 8 ships Python 3.6 by default in some images. If `python3 --version`
> shows < 3.9, install a newer one:
> ```bash
> sudo dnf install -y python3.11 python3.11-pip
> # then use `python3.11` everywhere this guide says `python3`
> ```

### 3M.4 Install the Python libraries this project needs

The project needs just: **pyyaml**, **requests**, **fastapi**, **uvicorn**.

```bash
pip3 install --user pyyaml requests fastapi "uvicorn[standard]"
```

> **Ubuntu 23.04+ / "externally-managed-environment" error?** Newer Debian/Ubuntu
> blocks system-wide pip. Two clean options:
>
> **Option A — allow user install (simplest):**
> ```bash
> pip3 install --user --break-system-packages pyyaml requests fastapi "uvicorn[standard]"
> ```
>
> **Option B — virtual environment (cleanest, recommended for the associate):**
> ```bash
> cd ~/titan-helix
> python3 -m venv .venv
> source .venv/bin/activate         # do this in every new terminal
> pip install pyyaml requests fastapi "uvicorn[standard]"
> ```
> If you use a venv, run `source ~/titan-helix/.venv/bin/activate` at the start
> of **every** terminal session before running the Python scripts.

Verify:
```bash
python3 -c "import yaml, requests, fastapi, uvicorn; print('python deps OK')"
```

### 3M.5 Make sure `~/.local/bin` is on your PATH

`pip --user` installs `uvicorn` into `~/.local/bin`, which may not be on PATH:
```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
which uvicorn        # should print a path; if blank, use `python3 -m uvicorn` later
```

### 3M.6 Install Docker

**Ubuntu:**
```bash
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
```

**Alma / Rocky / RHEL:**
```bash
sudo dnf install -y dnf-plugins-core
sudo dnf config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
sudo dnf install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
```

**Both — start Docker and allow your user to use it:**
```bash
sudo systemctl enable --now docker
sudo usermod -aG docker $USER
newgrp docker                  # apply group now (or log out/in)
docker --version               # confirm
docker run --rm hello-world    # confirm the daemon works
```

> **Alma alternative — Podman.** Alma ships Podman by default. If you prefer not
> to install Docker, Podman is drop-in compatible:
> ```bash
> sudo dnf install -y podman
> alias docker=podman           # add to ~/.bashrc to persist
> ```
> Everything in this guide then works with `docker` mapped to `podman`. (Note:
> with rootless Podman you don't need `sudo` for container commands.)

---

## 4. Install & start Splunk (manual path)

We run Splunk in a container — no system install, easy cleanup.

Pick a password and HEC token first (you'll reuse them everywhere):
```bash
# Choose your own, or use these defaults:
export SPLUNK_PW="ChangeMe_Helix_2026"
export HEC_TOKEN="11111111-2222-3333-4444-555555555555"
# (To generate a random token instead: export HEC_TOKEN=$(uuidgen) )
```

Start Splunk:
```bash
docker run -d --name helix-splunk \
  -p 8000:8000 -p 8088:8088 -p 8089:8089 \
  -e SPLUNK_START_ARGS=--accept-license \
  -e SPLUNK_PASSWORD="$SPLUNK_PW" \
  -e SPLUNK_HEC_TOKEN="$HEC_TOKEN" \
  splunk/splunk:9.2
```

> **SELinux note (Alma/RHEL only).** If a later step that mounts a local folder
> into the container fails with "permission denied", append `:Z` to the volume
> (e.g. `-v $(pwd)/infra:/tmp/x:Z`). The command above mounts nothing, so it's
> fine — this note is for the docker-compose route.

Wait for Splunk to boot (first time ~60–120s). Watch for readiness:
```bash
# This loops until Splunk's API answers, then stops:
until docker exec helix-splunk curl -fsk -u "admin:$SPLUNK_PW" \
  https://localhost:8089/services/server/info >/dev/null 2>&1; do
  echo "…waiting for Splunk"; sleep 5
done
echo "Splunk is up"
```

Open `http://localhost:8000` in the VM's browser → log in `admin` / your password.

---

## 5. Create indexes + configure HEC (manual path)

**5.1 Create the indexes:**
```bash
for IDX in helix_metrics helix_logs helix_traces helix_incidents \
           helix_security helix_business helix_deploy helix_audit \
           helix_self_metrics; do
  docker exec helix-splunk curl -sk -u "admin:$SPLUNK_PW" \
    -X POST https://localhost:8089/services/data/indexes \
    -d name="$IDX" -d datatype=event >/dev/null && echo "+ $IDX"
done
```

**5.2 Enable HEC and register the token:**
```bash
# Enable the HEC input globally
docker exec helix-splunk curl -sk -u "admin:$SPLUNK_PW" \
  -X POST https://localhost:8089/servicesNS/nobody/splunk_httpinput/data/inputs/http/http \
  -d disabled=0 >/dev/null

# Register our token, scoped to all helix indexes
docker exec helix-splunk curl -sk -u "admin:$SPLUNK_PW" \
  -X POST https://localhost:8089/servicesNS/nobody/splunk_httpinput/data/inputs/http \
  -d "name=helix-hec" -d "token=$HEC_TOKEN" -d "index=helix_logs" \
  -d "indexes=helix_metrics,helix_logs,helix_traces,helix_incidents,helix_security,helix_business,helix_deploy,helix_audit,helix_self_metrics" \
  -d "disabled=0" >/dev/null && echo "HEC token registered"
```

**5.3 Test HEC accepts an event:**
```bash
curl -sk http://localhost:8088/services/collector/event \
  -H "Authorization: Splunk $HEC_TOKEN" \
  -d '{"event":{"hello":"helix"},"sourcetype":"helix:test","index":"helix_logs"}'
# Expect: {"text":"Success","code":0}
```

---

## 6. Generate & load HISTORICAL data

This gives the platform a past — baselines and **3 resolved incidents** the
Memory agent recalls.

```bash
cd ~/titan-helix

# 6.1 Generate 7 days of history (~575k events, ~235 MB)
python3 historical_generator.py --days 7 --output data/history.jsonl
```
> Lower-resource VM? Generate less: `--days 3 --bucket-seconds 600`.

```bash
# 6.2 (optional) validate the file before loading
python3 load_to_splunk.py data/history.jsonl --dry-run

# 6.3 Load it into Splunk
python3 load_to_splunk.py data/history.jsonl \
    --hec-url http://localhost:8088 \
    --hec-token "$HEC_TOKEN"
```
Expected: `done · sent ~575,000 · failed 0`.

**Verify in Splunk** (UI → Search, time range "Last 8 days"):
```spl
index=helix_* earliest=-8d | stats count by index
```
See the past incidents:
```spl
index=helix_incidents earliest=-8d
| table _time number short_description state close_notes | sort _time
```

---

## 7. Stream LIVE telemetry (with the cascade)

Open a **second terminal** (keep Splunk running). `cd ~/titan-helix` first
(and `source .venv/bin/activate` if you used a venv).

```bash
python3 synth_generator.py \
    --hec-url http://localhost:8088 \
    --hec-token "$HEC_TOKEN" \
    --scenario scenarios/checkout_collapse.yaml \
    --speed 10
```

This streams the live firehose **and** injects a 6-phase cascading failure. At
`--speed 10` the 15-minute scenario plays in ~90 seconds. Leave it running.

Watch the cascade in Splunk (time range "Last 15 minutes"):
```spl
index=helix_logs service=fraud-scoring level=ERROR | head 20
```
```spl
index=helix_incidents | table _time number priority short_description
```

> Steady state with no scenario (runs until Ctrl-C):
> ```bash
> python3 synth_generator.py --hec-url http://localhost:8088 --hec-token "$HEC_TOKEN"
> ```

---

## 8. Run the AI agents

The agent mesh reads Splunk, reasons about the incident, and writes its
conclusions back to `helix_audit`.

**8.1 Self-test first (no Splunk, no API key needed):**
```bash
python3 agents.py --mock-data --investigate checkout-api
```
You'll see the Observer → Memory → Correlation → Prediction → Remediation →
Executive chain reason about a sample cascade. This proves the logic works.

**8.2 Against your live Splunk:**
```bash
python3 agents.py \
    --splunk-api-url https://localhost:8089 \
    --splunk-password "$SPLUNK_PW" \
    --hec-url http://localhost:8088 \
    --hec-token "$HEC_TOKEN" \
    --investigate checkout-api
```
The opinions are written to Splunk — see them:
```spl
index=helix_audit sourcetype=helix:agent:reasoning | sort _time
```

**8.3 (Optional) Genuine LLM reasoning** — needs internet + an API key:
```bash
python3 agents.py --mock-data --investigate checkout-api \
    --llm --provider anthropic --api-key sk-ant-XXXX --model claude-opus-4-7
# or: --provider openai --api-key sk-XXXX --model gpt-4o
```
Without `--llm`, the agents use built-in deterministic reasoning — fully
functional, no key required.

---

## 9. Run the backend API + open the visuals

**Third terminal**, in `~/titan-helix`:
```bash
export HELIX_SPLUNK_API_URL=https://localhost:8089
export HELIX_SPLUNK_API_USER=admin
export HELIX_SPLUNK_API_PASSWORD="$SPLUNK_PW"

uvicorn backend.app:app --host 0.0.0.0 --port 8080
# if 'uvicorn: command not found': python3 -m uvicorn backend.app:app --host 0.0.0.0 --port 8080
```

Open in the browser:
- **`http://localhost:8080`** — the command center, served from live Splunk.
- **`~/titan-helix/index.html`** — the project hub (links the diagram + demo).
  Open with: `xdg-open ~/titan-helix/index.html`
- **`~/titan-helix/architecture.html`** — the animated data-flow diagram.
- **`~/titan-helix/demo.html`** — the standalone command-center preview.

Test the live API:
```bash
curl http://localhost:8080/health
curl http://localhost:8080/api/graph | head -c 400
```
`"source":"splunk"` = reading real data. `"source":"sample"` = Splunk not reachable
(the API falls back so the UI never breaks — check your exports / that Splunk is up).

---

## 10. Verify it all works (one-shot checklist)

```bash
cd ~/titan-helix

echo "1. Splunk reachable:"
curl -sk -u "admin:$SPLUNK_PW" https://localhost:8089/services/server/info >/dev/null && echo "   OK"

echo "2. HEC accepts events:"
curl -sk http://localhost:8088/services/collector/event \
  -H "Authorization: Splunk $HEC_TOKEN" \
  -d '{"event":{"t":"ok"},"index":"helix_logs"}' | grep -q Success && echo "   OK"

echo "3. Agents run (mock):"
python3 agents.py --mock-data --json >/dev/null 2>&1 && echo "   OK"

echo "4. Data present in Splunk:"
docker exec helix-splunk /opt/splunk/bin/splunk search \
  'index=helix_* | stats count' -auth "admin:$SPLUNK_PW" -maxout 1
```

---

## 11. Troubleshooting

**`docker: permission denied` / `cannot connect to the Docker daemon`**
You're not in the docker group in this shell. `newgrp docker` or log out/in.
On Alma with Podman: you shouldn't need sudo at all; check `alias docker=podman`.

**Splunk container exits immediately / won't stay up**
Almost always RAM. Give the VM ≥ 4 GB. Check logs:
```bash
docker logs helix-splunk | tail -40
```
Look for the line `Ansible playbook complete` (means it finished booting).

**`externally-managed-environment` when pip installing**
See 3M.4 — use `--break-system-packages` or a venv.

**`uvicorn: command not found`**
`~/.local/bin` not on PATH (see 3M.5), or run `python3 -m uvicorn …` instead.

**`ModuleNotFoundError: No module named 'fastapi'` (or yaml/requests)**
The deps aren't installed in the Python you're running. If using a venv, did you
`source .venv/bin/activate` in this terminal? Re-run 3M.4.

**HEC test returns `{"text":"Invalid token"}`**
The token you're sending doesn't match what's registered. Re-run 5.2 with the
same `$HEC_TOKEN`, or check it: `echo $HEC_TOKEN`.

**HEC returns `{"text":"Incorrect index"}` or events vanish**
The index isn't in the token's allowed list. Re-run 5.2 (it scopes all helix_*
indexes), or create the missing index (5.1).

**Loader / generator: `Connection refused` to :8088**
Splunk isn't up yet, or HEC isn't enabled. Confirm Part 4 readiness loop finished
and 5.2 ran.

**Splunk search shows nothing**
Wrong time range (top-right). Live → "Last 15 minutes". History → "Last 8 days".
Confirm data exists: `index=helix_* | stats count`.

**Ports already in use (8000/8088/8089/8080)**
Find and stop the other process, or change the published port. Check:
```bash
sudo ss -tulpn | grep -E '8000|8088|8089|8080'
```

**firewalld blocking ports (Alma/RHEL, if accessing from another machine)**
Local browser access doesn't need this. For remote access:
```bash
sudo firewall-cmd --add-port=8000/tcp --add-port=8080/tcp --permanent
sudo firewall-cmd --reload
```

**Start completely over**
```bash
docker rm -f helix-splunk
rm -rf ~/titan-helix/data
# then redo from Part 4 (or just ./setup.sh)
```

**Stop / restart Splunk without losing setup**
```bash
docker stop helix-splunk      # stop
docker start helix-splunk     # resume (indexes + token persist)
```

---

## 12. Demo-day runbook (90 seconds)

Have ready **before** presenting: 3 terminals + browser tabs for
`localhost:8080` and a pre-typed Splunk search.

1. Open with: *"Every enterprise sits on a graph it can't see."*
2. Show `index.html` hub → click into the **architecture** diagram (data flowing).
3. Run the live generator (Terminal 2) — telemetry starts streaming.
4. Switch to Splunk tab, run the dependency search — the graph appears from traces.
5. Run `python3 agents.py --investigate checkout-api` (Terminal 3) — the agent
   chain reasons live and names `feature-store-db` as the cause.
6. Switch to `demo.html` for the cinematic cascade + blast radius.
7. Close on the audit query: *"and it writes every decision back, with the SPL
   trail to prove it"* → `index=helix_audit sourcetype=helix:agent:reasoning`.

> **Safety net:** `demo.html` plays the whole story with zero backend. If the
> live stack hiccups on stage, open that tab and keep going.

---

## 13. What's built vs. what's next

**Built and verified (every script was executed before shipping):**
- `synth_generator.py` — live telemetry → Splunk / file / stdout
- `historical_generator.py` + `load_to_splunk.py` — 7-day backfill with past incidents
- `agents.py` — full reasoning chain (mock mode = no key; `--llm` = real LLM)
- `backend/app.py` — Splunk-backed API with sample fallback
- `demo.html`, `architecture.html`, `index.html` — the visuals
- Splunk indexes + HEC config (via `setup.sh` or Part 5)

**Designed, partially wired (the next milestone):**
- The production React Flow frontend (`demo.html` is the visual reference for it).
- The standalone MCP server (the tool registry + `splunk_search` tool are
  designed in the architecture doc; `agents.py` already calls Splunk directly in
  the same shape an MCP tool would).

**Recommended next build:** wire `agents.py` behind a WebSocket endpoint in
`backend/app.py` so the command center streams the live agent debate as it
happens — that connects the reasoning you just ran to the visuals you just saw.

---

*Questions while building? The architecture rationale for every component is in
`TITAN_HELIX_Architecture.md`. This guide is the operational how-to; that doc is
the why.*
