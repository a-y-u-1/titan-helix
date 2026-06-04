#!/usr/bin/env bash
# ════════════════════════════════════════════════════════════════════════════
# TITAN HELIX · One-Command Ubuntu Setup
# Installs everything and brings up Splunk with indexes + HEC configured.
#
#   chmod +x setup.sh
#   ./setup.sh
#
# Safe to re-run. Idempotent where possible.
# Tested on Ubuntu 22.04 / 24.04 (VirtualBox).
# ════════════════════════════════════════════════════════════════════════════
set -euo pipefail

# ─── Config (override via env) ───────────────────────────────────────────────
SPLUNK_PASSWORD="${HELIX_SPLUNK_PASSWORD:-ChangeMe_Helix_2026}"
HEC_TOKEN="${HELIX_SPLUNK_HEC_TOKEN:-11111111-2222-3333-4444-555555555555}"
SPLUNK_IMAGE="splunk/splunk:9.2"

B='\033[1m'; G='\033[1;32m'; A='\033[1;33m'; R='\033[0m'; RED='\033[1;31m'
say()  { echo -e "${G}▸${R} $*"; }
warn() { echo -e "${A}!${R} $*"; }
err()  { echo -e "${RED}✗${R} $*" >&2; }

echo -e "${B}TITAN HELIX setup${R}"
echo    "─────────────────"

# ─── 1. System packages ──────────────────────────────────────────────────────
say "Updating apt and installing base packages…"
sudo apt-get update -qq
sudo apt-get install -y -qq \
  python3 python3-pip python3-venv curl jq git ca-certificates gnupg lsb-release \
  >/dev/null
say "Base packages installed."

# ─── 2. Docker ───────────────────────────────────────────────────────────────
if ! command -v docker >/dev/null 2>&1; then
  say "Installing Docker…"
  sudo install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
    | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  sudo chmod a+r /etc/apt/keyrings/docker.gpg
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
    | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
  sudo apt-get update -qq
  sudo apt-get install -y -qq docker-ce docker-ce-cli containerd.io \
    docker-buildx-plugin docker-compose-plugin >/dev/null
  sudo usermod -aG docker "$USER" || true
  warn "Added you to the 'docker' group. If docker commands fail with"
  warn "'permission denied', log out and back in (or run: newgrp docker)."
else
  say "Docker already installed: $(docker --version)"
fi

# ─── 3. Python deps ──────────────────────────────────────────────────────────
say "Installing Python dependencies…"
pip3 install --user --quiet --break-system-packages \
  pyyaml requests fastapi "uvicorn[standard]" 2>/dev/null \
  || pip3 install --user --quiet pyyaml requests fastapi "uvicorn[standard]"
say "Python deps installed."

# ─── 4. Start Splunk ─────────────────────────────────────────────────────────
if sudo docker ps -a --format '{{.Names}}' | grep -q '^helix-splunk$'; then
  say "Splunk container exists. Starting it…"
  sudo docker start helix-splunk >/dev/null
else
  say "Starting Splunk container (first boot takes ~90s)…"
  sudo docker run -d --name helix-splunk \
    -p 8000:8000 -p 8088:8088 -p 8089:8089 \
    -e SPLUNK_START_ARGS=--accept-license \
    -e SPLUNK_PASSWORD="$SPLUNK_PASSWORD" \
    -e SPLUNK_HEC_TOKEN="$HEC_TOKEN" \
    "$SPLUNK_IMAGE" >/dev/null
fi

# ─── 5. Wait for Splunk management API ───────────────────────────────────────
say "Waiting for Splunk to become ready…"
for i in $(seq 1 60); do
  if sudo docker exec helix-splunk curl -fsk \
      -u "admin:$SPLUNK_PASSWORD" \
      https://localhost:8089/services/server/info >/dev/null 2>&1; then
    say "Splunk is up."
    break
  fi
  printf "\r  …still booting (%ds)" $((i*5)); sleep 5
  if [ "$i" -eq 60 ]; then err "Splunk did not come up in time."; exit 1; fi
done
echo

# ─── 6. Create indexes ───────────────────────────────────────────────────────
say "Creating Helix indexes…"
for IDX in helix_metrics helix_logs helix_traces helix_incidents \
           helix_security helix_business helix_deploy helix_audit \
           helix_self_metrics; do
  sudo docker exec helix-splunk curl -sk -u "admin:$SPLUNK_PASSWORD" \
    -X POST https://localhost:8089/services/data/indexes \
    -d name="$IDX" -d datatype=event >/dev/null 2>&1 \
    && echo "    + $IDX" || echo "    = $IDX (exists)"
done

# ─── 7. Configure HEC ────────────────────────────────────────────────────────
say "Configuring HTTP Event Collector…"
# Enable HEC globally
sudo docker exec helix-splunk curl -sk -u "admin:$SPLUNK_PASSWORD" \
  -X POST https://localhost:8089/servicesNS/nobody/splunk_httpinput/data/inputs/http/http \
  -d disabled=0 >/dev/null 2>&1 || true
# Register our token (idempotent: delete-then-create)
sudo docker exec helix-splunk curl -sk -u "admin:$SPLUNK_PASSWORD" \
  -X DELETE https://localhost:8089/servicesNS/nobody/splunk_httpinput/data/inputs/http/helix-hec \
  >/dev/null 2>&1 || true
sudo docker exec helix-splunk curl -sk -u "admin:$SPLUNK_PASSWORD" \
  -X POST https://localhost:8089/servicesNS/nobody/splunk_httpinput/data/inputs/http \
  -d "name=helix-hec" \
  -d "token=$HEC_TOKEN" \
  -d "index=helix_logs" \
  -d "indexes=helix_metrics,helix_logs,helix_traces,helix_incidents,helix_security,helix_business,helix_deploy,helix_audit,helix_self_metrics" \
  -d "disabled=0" >/dev/null 2>&1 \
  && say "HEC token registered." \
  || warn "HEC token registration returned non-zero (may already exist)."

# ─── Done ────────────────────────────────────────────────────────────────────
cat <<EOF

$(echo -e "${G}✓ Setup complete.${R}")

  ${B}Splunk UI:${R}   http://localhost:8000   (admin / $SPLUNK_PASSWORD)
  ${B}HEC URL:${R}     http://localhost:8088
  ${B}HEC token:${R}   $HEC_TOKEN

NEXT STEPS
──────────
  1) Generate + load historical data (7 days):
       python3 historical_generator.py --days 7 --output data/history.jsonl
       python3 load_to_splunk.py data/history.jsonl \\
           --hec-url http://localhost:8088 --hec-token $HEC_TOKEN

  2) Stream live telemetry with the cascade scenario:
       python3 synth_generator.py \\
           --hec-url http://localhost:8088 --hec-token $HEC_TOKEN \\
           --scenario scenarios/checkout_collapse.yaml --speed 10

  3) Start the backend API + open the demo:
       uvicorn backend.app:app --host 0.0.0.0 --port 8080
       # then open http://localhost:8080

  4) Or just open the standalone visual:
       xdg-open demo.html

Full walkthrough: see SETUP_UBUNTU.md
EOF
