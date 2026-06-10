#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════════════
#  TITAN HELIX  ·  one-command setup & verification
# ──────────────────────────────────────────────────────────────────────────────
#  Brings up the whole stack from a fresh git clone with minimum moving parts:
#    • verifies project files + prerequisites
#    • starts Splunk in Docker (persists across reboots: named volumes + restart)
#    • configures HEC + the 7 indexes the code actually uses (idempotent, via REST)
#    • creates a Python venv and installs deps
#    • loads historical data once
#    • launches the backend and verifies it end-to-end
#
#  USAGE
#    ./setup.sh                 full setup (safe to re-run any time)
#    ./setup.sh --check         verify only — change nothing, just report status
#    ./setup.sh --wipe          remove the Splunk container + volumes, then rebuild
#    ./setup.sh --reload-data   regenerate + reload the historical dataset
#    ./setup.sh --no-backend    set everything up but don't start the API server
#    ./setup.sh --install-service   also install a systemd unit so the API
#                                   auto-starts on boot (asks for sudo)
#
#  Everything is configurable via env (HELIX_SPLUNK_PASSWORD, HELIX_HEC_TOKEN,
#  SPLUNK_IMAGE, HELIX_BACKEND_PORT, HELIX_DATA_DAYS …). Tested on Ubuntu 22/24/26.
# ══════════════════════════════════════════════════════════════════════════════
set -euo pipefail

# ── config (override via env) ────────────────────────────────────────────────
SPLUNK_PASSWORD="${HELIX_SPLUNK_PASSWORD:-ChangeMe_Helix_2026}"
HEC_TOKEN="${HELIX_HEC_TOKEN:-11111111-2222-3333-4444-555555555555}"
SPLUNK_IMAGE="${SPLUNK_IMAGE:-splunk/splunk:latest}"
CONTAINER="${HELIX_CONTAINER:-helix-splunk}"
VOL_VAR="${HELIX_VOL_VAR:-helix-splunk-var}"
VOL_ETC="${HELIX_VOL_ETC:-helix-splunk-etc}"
BACKEND_PORT="${HELIX_BACKEND_PORT:-8080}"
DATA_DAYS="${HELIX_DATA_DAYS:-7}"
MGMT="https://localhost:8089"
HEC_URL="https://localhost:8088"

# the 7 indexes the code actually writes to / queries (verified against source)
INDEXES=(helix_metrics helix_logs helix_traces helix_incidents helix_deploy helix_business helix_audit)

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; cd "$ROOT"
ENVFILE="$ROOT/.helix.env"
PIDFILE="$ROOT/.helix.backend.pid"
DATA_FILE="$ROOT/data/history.jsonl"
DATA_MARK="$ROOT/data/.loaded"

# ── flags ─────────────────────────────────────────────────────────────────────
CHECK_ONLY=0; WIPE=0; RELOAD=0; NO_BACKEND=0; INSTALL_SVC=0
for a in "$@"; do case "$a" in
  --check)            CHECK_ONLY=1 ;;
  --wipe)             WIPE=1 ;;
  --reload-data)      RELOAD=1 ;;
  --no-backend)       NO_BACKEND=1 ;;
  --install-service)  INSTALL_SVC=1 ;;
  -h|--help) grep -E '^#' "$0" | sed -E 's/^# ?//'; exit 0 ;;
  *) echo "unknown flag: $a  (try --help)"; exit 1 ;;
esac; done

# ── pretty output ───────────────────────────────────────────────────────────
if [ -t 1 ]; then B='\033[1m'; G='\033[1;32m'; A='\033[1;33m'; RED='\033[1;31m'; C='\033[1;36m'; Z='\033[0m'
else B=''; G=''; A=''; RED=''; C=''; Z=''; fi
ok(){   echo -e "  ${G}✓${Z} $*"; }
warn(){ echo -e "  ${A}!${Z} $*"; }
bad(){  echo -e "  ${RED}✗${Z} $*"; }
die(){  echo -e "\n${RED}✗ $*${Z}\n" >&2; exit 1; }
hdr(){  echo -e "\n${B}$*${Z}"; echo "────────────────────────────────────────────"; }
FAILED=0; mark_fail(){ FAILED=1; }

echo -e "${C}"
echo "  ╔══════════════════════════════════════════╗"
echo "  ║   T I T A N   H E L I X   ·   setup       ║"
echo "  ╚══════════════════════════════════════════╝"
echo -e "${Z}  mode: $([ $CHECK_ONLY -eq 1 ] && echo 'VERIFY ONLY' || echo 'full setup')"

# ══════════════════════════════════════════════════════════════════════════════
# 1 · project files
# ══════════════════════════════════════════════════════════════════════════════
hdr "1 · project files"
REQUIRED=(
  backend/app.py backend/splunk_client.py backend/requirements.txt backend/__init__.py
  console.html demo.html stage.html
  synth_generator.py historical_generator.py load_to_splunk.py agents.py
  scenarios/checkout_collapse.yaml
)
missing=0
for f in "${REQUIRED[@]}"; do
  if [ -f "$f" ]; then ok "$f"; else bad "MISSING  $f"; missing=1; fi
done
# __init__.py is the one file we can safely auto-create if absent
if [ ! -f backend/__init__.py ] && [ $CHECK_ONLY -eq 0 ]; then : > backend/__init__.py; ok "created backend/__init__.py"; missing=0; fi
[ $missing -eq 0 ] || die "Core files missing. Run this from the repository root after 'git clone'."

# ══════════════════════════════════════════════════════════════════════════════
# 2 · prerequisites
# ══════════════════════════════════════════════════════════════════════════════
hdr "2 · prerequisites"
need_apt=()
have(){ command -v "$1" >/dev/null 2>&1; }
for t in docker python3 curl; do
  if have "$t"; then ok "$t  ($($t --version 2>&1 | head -1))"; else bad "$t not found"; need_apt+=("$t"); fi
done
if python3 -c 'import venv' 2>/dev/null; then ok "python3-venv"; else bad "python3-venv missing"; need_apt+=(python3-venv); fi
if have jq; then ok "jq"; else warn "jq not found (used for token read-back)"; need_apt+=(jq); fi

if [ ${#need_apt[@]} -gt 0 ]; then
  if [ $CHECK_ONLY -eq 1 ]; then
    bad "missing tools: ${need_apt[*]}  — run ./setup.sh (without --check) to install"; mark_fail
  elif have apt-get; then
    warn "installing: ${need_apt[*]}"
    sudo apt-get update -qq
    # map docker -> docker.io for apt
    pkgs=(); for p in "${need_apt[@]}"; do [ "$p" = docker ] && pkgs+=(docker.io) || pkgs+=("$p"); done
    sudo apt-get install -y -qq "${pkgs[@]}"
    sudo systemctl enable --now docker 2>/dev/null || true
    ok "installed."
  else
    die "Missing ${need_apt[*]} and no apt-get available. Install them manually."
  fi
fi

# pick the docker invocation that works (with or without sudo)
DOCKER=""
if docker info >/dev/null 2>&1; then DOCKER="docker"
else
  sudo systemctl start docker 2>/dev/null || true
  if docker info >/dev/null 2>&1; then DOCKER="docker"
  elif sudo docker info >/dev/null 2>&1; then DOCKER="sudo docker"; warn "using 'sudo docker' (add yourself to the docker group to avoid this: sudo usermod -aG docker \$USER, then re-login)"
  else die "Docker daemon not reachable. Start it: sudo systemctl start docker"; fi
fi
ok "docker daemon reachable"

# ══════════════════════════════════════════════════════════════════════════════
# 3 · Splunk container
# ══════════════════════════════════════════════════════════════════════════════
hdr "3 · Splunk container"
exists(){ $DOCKER ps -a --format '{{.Names}}' | grep -qx "$CONTAINER"; }
running(){ $DOCKER ps    --format '{{.Names}}' | grep -qx "$CONTAINER"; }

if [ $WIPE -eq 1 ] && [ $CHECK_ONLY -eq 0 ]; then
  warn "--wipe: removing container + volumes"
  $DOCKER rm -f "$CONTAINER" >/dev/null 2>&1 || true
  $DOCKER volume rm "$VOL_VAR" "$VOL_ETC" >/dev/null 2>&1 || true
  rm -f "$DATA_MARK"
fi

if [ $CHECK_ONLY -eq 1 ]; then
  if running; then ok "container '$CONTAINER' running"; else bad "container '$CONTAINER' not running"; mark_fail; fi
else
  if running; then
    ok "container '$CONTAINER' already running"
  elif exists; then
    warn "container exists but stopped — starting"
    $DOCKER start "$CONTAINER" >/dev/null
  else
    warn "creating container (first boot ~60-120s) using image $SPLUNK_IMAGE"
    # both license flags (newer images require SPLUNK_GENERAL_TERMS),
    # named volumes for persistence, restart policy so it survives reboots,
    # SPLUNK_HEC_TOKEN to seed the token deterministically at boot.
    $DOCKER run -d --name "$CONTAINER" \
      --restart unless-stopped \
      -p 8000:8000 -p 8088:8088 -p 8089:8089 \
      -v "$VOL_VAR":/opt/splunk/var \
      -v "$VOL_ETC":/opt/splunk/etc \
      -e SPLUNK_GENERAL_TERMS="--accept-sgt-current-at-splunk-com" \
      -e SPLUNK_START_ARGS="--accept-license" \
      -e SPLUNK_PASSWORD="$SPLUNK_PASSWORD" \
      -e SPLUNK_HEC_TOKEN="$HEC_TOKEN" \
      "$SPLUNK_IMAGE" >/dev/null
    ok "container created"
  fi
fi

# wait for the management API
if [ $CHECK_ONLY -eq 0 ] || running; then
  printf "  … waiting for Splunk management API"
  up=0
  for i in $(seq 1 40); do
    if curl -fsk -u "admin:$SPLUNK_PASSWORD" "$MGMT/services/server/info" >/dev/null 2>&1; then up=1; break; fi
    printf "."; sleep 3
  done
  echo
  if [ $up -eq 1 ]; then ok "Splunk API is up (admin / $SPLUNK_PASSWORD)"
  else
    if [ $CHECK_ONLY -eq 1 ]; then bad "Splunk API not responding"; mark_fail
    else die "Splunk did not come up. Check: $DOCKER logs $CONTAINER --tail 50"; fi
  fi
fi

# ══════════════════════════════════════════════════════════════════════════════
# 4 · indexes + HEC  (REST from host — no in-container permission issues)
# ══════════════════════════════════════════════════════════════════════════════
hdr "4 · indexes + HEC"
SP(){ curl -sk -u "admin:$SPLUNK_PASSWORD" "$@"; }   # splunk mgmt helper

if [ $CHECK_ONLY -eq 0 ]; then
  # indexes (idempotent: 'already exists' is fine)
  for idx in "${INDEXES[@]}"; do
    SP -X POST "$MGMT/services/data/indexes" -d name="$idx" -d datatype=event >/dev/null 2>&1 || true
  done
  ok "indexes ensured: ${INDEXES[*]}"

  # enable the global HEC input (with SSL — generators use https)
  SP -X POST "$MGMT/servicesNS/nobody/splunk_httpinput/data/inputs/http/http" \
     -d disabled=0 -d enableSSL=1 >/dev/null 2>&1 || true

  # (re)create our named token with a deterministic value pointing at all indexes
  csv="$(IFS=,; echo "${INDEXES[*]}")"
  SP -X DELETE "$MGMT/servicesNS/nobody/splunk_httpinput/data/inputs/http/helix-hec" >/dev/null 2>&1 || true
  SP -X POST "$MGMT/servicesNS/nobody/splunk_httpinput/data/inputs/http" \
     -d name=helix-hec -d token="$HEC_TOKEN" -d index=helix_logs \
     -d indexes="$csv" -d disabled=0 >/dev/null 2>&1 || true
  ok "HEC token 'helix-hec' registered"
fi

# read the token actually in effect (source of truth) and self-test it
ACTUAL_TOKEN="$HEC_TOKEN"
if have jq; then
  rb="$(SP "$MGMT/servicesNS/nobody/splunk_httpinput/data/inputs/http/helix-hec?output_mode=json" 2>/dev/null | jq -r '.entry[0].content.token // empty' 2>/dev/null || true)"
  [ -n "$rb" ] && ACTUAL_TOKEN="$rb"
fi
hectest="$(curl -sk "$HEC_URL/services/collector" -H "Authorization: Splunk $ACTUAL_TOKEN" -d '{"event":"helix-setup-probe","index":"main"}' 2>/dev/null || true)"
if echo "$hectest" | grep -q '"code":0'; then ok "HEC accepting events  (token: $ACTUAL_TOKEN)"
else bad "HEC self-test failed: ${hectest:-no response}"; mark_fail; fi

# ══════════════════════════════════════════════════════════════════════════════
# 5 · environment file  (single source of truth for the backend)
# ══════════════════════════════════════════════════════════════════════════════
hdr "5 · environment file"
if [ $CHECK_ONLY -eq 0 ]; then
  cat > "$ENVFILE" <<EOF
# auto-generated by setup.sh — source this before running the backend
export HELIX_SPLUNK_API_URL=$MGMT
export HELIX_SPLUNK_API_USER=admin
export HELIX_SPLUNK_API_PASSWORD=$SPLUNK_PASSWORD
export HELIX_SPLUNK_VERIFY_SSL=0
export HELIX_HEC_URL=$HEC_URL
export HELIX_HEC_TOKEN=$ACTUAL_TOKEN
# Optional — real Claude reasoning in the AI tab (separate Anthropic API key):
# export HELIX_LLM_API_KEY=sk-ant-...
# export HELIX_LLM_PROVIDER=anthropic
# export HELIX_LLM_MODEL=claude-sonnet-4-6
EOF
  ok "wrote .helix.env"
else
  [ -f "$ENVFILE" ] && ok ".helix.env present" || { bad ".helix.env missing"; mark_fail; }
fi

# ══════════════════════════════════════════════════════════════════════════════
# 6 · Python venv + deps
# ══════════════════════════════════════════════════════════════════════════════
hdr "6 · Python environment"
if [ -d .venv ]; then ok ".venv exists"
elif [ $CHECK_ONLY -eq 1 ]; then bad ".venv missing"; mark_fail
else python3 -m venv .venv && ok "created .venv"; fi

if [ -d .venv ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
  if [ $CHECK_ONLY -eq 0 ]; then
    pip install -q --upgrade pip >/dev/null 2>&1 || true
    pip install -q -r backend/requirements.txt
    ok "dependencies installed (fastapi, uvicorn, requests, pyyaml)"
  else
    python3 -c 'import fastapi, uvicorn, requests, yaml' 2>/dev/null \
      && ok "deps importable" || { bad "deps missing in .venv"; mark_fail; }
  fi
fi

# ══════════════════════════════════════════════════════════════════════════════
# 7 · historical data
# ══════════════════════════════════════════════════════════════════════════════
hdr "7 · historical data"
mkdir -p data
if [ $CHECK_ONLY -eq 1 ]; then
  [ -f "$DATA_MARK" ] && ok "historical data loaded (marker present)" || warn "historical data not loaded yet"
elif [ -f "$DATA_MARK" ] && [ $RELOAD -eq 0 ]; then
  ok "historical data already loaded — skipping (use --reload-data to refresh)"
else
  if [ ! -f "$DATA_FILE" ] || [ $RELOAD -eq 1 ]; then
    warn "generating ${DATA_DAYS}d of history (≈575k events, ~30s)…"
    python3 historical_generator.py --days "$DATA_DAYS" --output "$DATA_FILE"
  fi
  warn "loading into Splunk via HEC (batch 50)…"
  python3 load_to_splunk.py "$DATA_FILE" --hec-url "$HEC_URL" --hec-token "$ACTUAL_TOKEN" --batch 50
  touch "$DATA_MARK"
  ok "historical data loaded"
fi

# ══════════════════════════════════════════════════════════════════════════════
# 8 · backend
# ══════════════════════════════════════════════════════════════════════════════
hdr "8 · backend API"
start_backend(){
  [ -f "$PIDFILE" ] && kill "$(cat "$PIDFILE")" 2>/dev/null || true
  # shellcheck disable=SC1090
  source "$ENVFILE"; source .venv/bin/activate
  nohup python3 -m uvicorn backend.app:app --host 0.0.0.0 --port "$BACKEND_PORT" \
        > "$ROOT/backend.log" 2>&1 &
  echo $! > "$PIDFILE"
}
backend_alive(){ curl -fs "http://127.0.0.1:$BACKEND_PORT/health" >/dev/null 2>&1; }

if [ $CHECK_ONLY -eq 1 ]; then
  if backend_alive; then ok "backend healthy on :$BACKEND_PORT"; else warn "backend not running"; fi
elif [ $NO_BACKEND -eq 1 ]; then
  ok "skipping backend start (--no-backend). To run it:"
  echo -e "      ${C}source .helix.env && source .venv/bin/activate${Z}"
  echo -e "      ${C}python3 -m uvicorn backend.app:app --host 0.0.0.0 --port $BACKEND_PORT${Z}"
else
  warn "starting backend…"
  start_backend
  for i in $(seq 1 10); do backend_alive && break; sleep 1; done
  if backend_alive; then
    ok "backend healthy on :$BACKEND_PORT  (pid $(cat "$PIDFILE"), logs → backend.log)"
    nodes="$(curl -fs "http://127.0.0.1:$BACKEND_PORT/api/graph" 2>/dev/null | { command -v jq >/dev/null && jq -r '.nodes|length' || grep -o '"id"' | wc -l; } 2>/dev/null || true)"
    [ -n "${nodes:-}" ] && ok "/api/graph returned ${nodes} services" || warn "/api/graph reachable"
  else
    bad "backend failed to start — see backend.log"; mark_fail
  fi
fi

# ══════════════════════════════════════════════════════════════════════════════
# optional · systemd unit so the backend auto-starts on boot
# ══════════════════════════════════════════════════════════════════════════════
if [ $INSTALL_SVC -eq 1 ] && [ $CHECK_ONLY -eq 0 ]; then
  hdr "optional · systemd service"
  UNIT=/etc/systemd/system/titan-helix.service
  sudo tee "$UNIT" >/dev/null <<EOF
[Unit]
Description=TITAN HELIX backend
After=docker.service network-online.target
Wants=docker.service network-online.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$ROOT
EnvironmentFile=$ENVFILE
ExecStart=$ROOT/.venv/bin/python -m uvicorn backend.app:app --host 0.0.0.0 --port $BACKEND_PORT
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF
  sudo systemctl daemon-reload
  sudo systemctl enable --now titan-helix.service
  ok "installed + enabled titan-helix.service (auto-starts on boot)"
  warn "manage with: sudo systemctl {status|restart|stop} titan-helix"
fi

# ══════════════════════════════════════════════════════════════════════════════
# summary
# ══════════════════════════════════════════════════════════════════════════════
echo
if [ $FAILED -eq 0 ]; then
  echo -e "${G}${B}  ✓ ALL CHECKS PASSED${Z}"
else
  echo -e "${RED}${B}  ✗ SOME CHECKS FAILED — see above${Z}"
fi
cat <<EOF

  ${B}Open in your browser${Z}
    ${C}http://localhost:$BACKEND_PORT/stage${Z}   ← presenter shell (Live ⇄ Demo toggle, keys L/D)
    http://localhost:$BACKEND_PORT/          live console
    http://localhost:$BACKEND_PORT/demo      scripted demo (no backend data needed)
    http://localhost:8000                    Splunk UI (admin / $SPLUNK_PASSWORD)

  ${B}Handy${Z}
    ./setup.sh --check         re-verify everything is healthy
    tail -f backend.log        watch the API
    kill \$(cat .helix.backend.pid)   stop the API
    $DOCKER logs $CONTAINER --tail 50    Splunk logs

  Splunk persists across reboots (named volumes + restart policy).
  After a reboot, just run ./setup.sh again — it'll be back in seconds.
EOF
[ $FAILED -eq 0 ] || exit 1
