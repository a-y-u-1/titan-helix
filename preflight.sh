#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════════════
#  TITAN HELIX  ·  pre-flight check   (run right before a judge evaluates)
# ──────────────────────────────────────────────────────────────────────────────
#  Goes beyond `setup.sh --check`: confirms the indexes actually contain data,
#  the AI investigation returns a full reasoning chain, incidents are present for
#  the Memory agent, inject is armed, and all three pages serve. Ends with a clear
#  GO / NO-GO verdict and a remediation hint for anything red.
#
#    ./preflight.sh
# ══════════════════════════════════════════════════════════════════════════════
set -uo pipefail   # NOT -e: we want every check to run and report, not bail early

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; cd "$ROOT"
[ -f .helix.env ] && { set -a; # shellcheck disable=SC1091
  . ./.helix.env; set +a; }

PORT="${HELIX_BACKEND_PORT:-8080}"
MGMT="${HELIX_SPLUNK_API_URL:-https://localhost:8089}"
PW="${HELIX_SPLUNK_API_PASSWORD:-ChangeMe_Helix_2026}"
HEC_URL="${HELIX_HEC_URL:-https://localhost:8088}"
HEC_TOKEN="${HELIX_HEC_TOKEN:-}"
BASE="http://127.0.0.1:$PORT"
CONTAINER="${HELIX_CONTAINER:-helix-splunk}"

if [ -t 1 ]; then B='\033[1m'; G='\033[1;32m'; A='\033[1;33m'; RED='\033[1;31m'; C='\033[1;36m'; Z='\033[0m'
else B=''; G=''; A=''; RED=''; C=''; Z=''; fi
PASS=0; FAIL=0; WARN=0
ok(){   echo -e "  ${G}✓${Z} $1"; PASS=$((PASS+1)); }
no(){   echo -e "  ${RED}✗${Z} $1"; [ -n "${2:-}" ] && echo -e "      ${A}→ $2${Z}"; FAIL=$((FAIL+1)); }
wn(){   echo -e "  ${A}!${Z} $1"; WARN=$((WARN+1)); }
hdr(){  echo -e "\n${B}$*${Z}"; echo "──────────────────────────────────────────────"; }

have(){ command -v "$1" >/dev/null 2>&1; }
DOCKER="docker"; docker info >/dev/null 2>&1 || DOCKER="sudo docker"
SP(){ curl -sk -u "admin:$PW" "$@"; }
jqr(){ if have jq; then jq -r "$1" 2>/dev/null; else cat; fi; }

echo -e "${C}"
echo "  ╔══════════════════════════════════════════╗"
echo "  ║   T I T A N   H E L I X  ·  pre-flight    ║"
echo "  ╚══════════════════════════════════════════╝${Z}"
echo "  backend: $BASE   splunk: $MGMT"

# ── 1 · Splunk + HEC ──────────────────────────────────────────────────────────
hdr "1 · Splunk & HEC"
if $DOCKER ps --format '{{.Names}}' 2>/dev/null | grep -qx "$CONTAINER"; then
  hs="$($DOCKER inspect -f '{{.State.Health.Status}}' "$CONTAINER" 2>/dev/null || echo unknown)"
  ok "container '$CONTAINER' running (health: $hs)"
else
  no "container '$CONTAINER' not running" "run ./setup.sh"
fi
if SP "$MGMT/services/server/info" >/dev/null 2>&1; then ok "Splunk management API responding"
else no "Splunk API not responding" "docker logs $CONTAINER --tail 50 ; or ./setup.sh"; fi

if [ -n "$HEC_TOKEN" ]; then
  r="$(curl -sk "$HEC_URL/services/collector" -H "Authorization: Splunk $HEC_TOKEN" -d '{"event":"preflight","index":"main"}' 2>/dev/null)"
  echo "$r" | grep -q '"code":0' && ok "HEC accepting events" || no "HEC self-test failed: ${r:-no response}" "./setup.sh --wipe"
else
  no "HELIX_HEC_TOKEN not set" "run ./setup.sh (writes .helix.env)"
fi

# ── 2 · data actually present (the live console needs this) ───────────────────
hdr "2 · data in indexes"
for idx in helix_metrics helix_traces helix_logs helix_incidents; do
  cnt="$(SP "$MGMT/services/data/indexes/$idx?output_mode=json" 2>/dev/null | jqr '.entry[0].content.totalEventCount // 0')"
  cnt="${cnt:-0}"; case "$cnt" in ''|*[!0-9]*) cnt=0;; esac
  if [ "$cnt" -gt 0 ]; then ok "$idx has data ($cnt events)"
  else no "$idx is EMPTY" "load data: ./setup.sh --reload-data"; fi
done

# ── 3 · backend API ───────────────────────────────────────────────────────────
hdr "3 · backend API"
health="$(curl -fs --max-time 8 "$BASE/health" 2>/dev/null || echo '{}')"
if echo "$health" | grep -q '"status"' || [ -n "$health" ] && curl -fs "$BASE/health" >/dev/null 2>&1; then
  ok "/health responding"
else no "/health not responding" "start it: source .helix.env && source .venv/bin/activate && python3 -m uvicorn backend.app:app --host 0.0.0.0 --port $PORT"; fi

heccfg="$(echo "$health" | jqr '.hec_configured // false')"
[ "$heccfg" = "true" ] && ok "HEC configured in backend (optional CLI live-injection available)" \
  || wn "HEC not in backend env — only needed for the optional CLI live-injection, not for the demo"

nodes="$(curl -fs --max-time 12 "$BASE/api/graph" 2>/dev/null | jqr '.nodes|length // 0')"
nodes="${nodes:-0}"; case "$nodes" in ''|*[!0-9]*) nodes=0;; esac
if   [ "$nodes" -ge 20 ]; then ok "/api/graph returns $nodes services (live graph populated)"
elif [ "$nodes" -gt 0 ];  then wn "/api/graph returns only $nodes services — data may be thin; widen window or --reload-data"
else no "/api/graph returns 0 services" "no live data — ./setup.sh --reload-data, and confirm Splunk has events"; fi

svc="$(curl -fs --max-time 12 "$BASE/api/service/checkout-api" 2>/dev/null | jqr '.latency.p99 // empty')"
[ -n "$svc" ] && ok "/api/service drill-down works (checkout-api p99=${svc}ms)" \
  || wn "/api/service/checkout-api returned no latency (will show sample data)"

echo "  … running AI investigation (deterministic = instant, LLM = up to ~20s)"
resp="$(curl -fs --max-time 60 "$BASE/api/investigate/checkout-api" 2>/dev/null || echo '{}')"
ops="$(echo "$resp" | jqr '.opinions|length // 0')"; ops="${ops:-0}"; case "$ops" in ''|*[!0-9]*) ops=0;; esac
mode="$(echo "$resp" | jqr '.reasoning_mode // "?"')"
if [ "$ops" -ge 6 ]; then ok "AI mesh returns full chain ($ops agents · mode: $mode)"
elif [ "$ops" -gt 0 ]; then wn "AI mesh returned $ops agents (expected 6) · mode: $mode"
else no "AI investigation returned no opinions" "check backend.log; ensure agents.py present and Splunk reachable"; fi
case "$mode" in
  llm:*) ok "AI is using a real LLM ($mode)";;
  deterministic) wn "AI is in deterministic mode (no API key). Fine to demo; for real Claude set HELIX_LLM_API_KEY in .helix.env";;
esac

inc="$(curl -fs --max-time 10 "$BASE/api/incidents" 2>/dev/null || echo '')"
echo "$inc" | grep -q 'INC' && ok "/api/incidents has incidents (Memory agent recall ready)" \
  || wn "/api/incidents shows no INC records — Memory agent recall may be thin (--reload-data)"

# ── 4 · pages serve ───────────────────────────────────────────────────────────
hdr "4 · pages"
for path in "/" "/demo" "/stage"; do
  code="$(curl -fs -o /dev/null -w '%{http_code}' --max-time 8 "$BASE$path" 2>/dev/null || echo 000)"
  [ "$code" = 200 ] && ok "GET $path → 200" || no "GET $path → $code" "check console.html / demo.html / stage.html exist in repo root"
done

# ── 5 · host headroom ─────────────────────────────────────────────────────────
hdr "5 · host"
if have free; then
  avail="$(free -m | awk '/^Mem:/{print $7}')"; avail="${avail:-0}"
  [ "$avail" -ge 800 ] && ok "RAM available: ${avail} MB" || wn "low free RAM (${avail} MB) — Splunk likes ≥1GB headroom"
fi
diskg="$(df -Pm . | awk 'NR==2{print $4}')"; diskg="${diskg:-0}"
[ "$diskg" -ge 1500 ] && ok "disk free: $((diskg/1024)) GB" || wn "low disk ($((diskg/1024)) GB free)"

# ── verdict ───────────────────────────────────────────────────────────────────
echo
echo "──────────────────────────────────────────────"
echo -e "  ${G}$PASS passed${Z}   ${A}$WARN warnings${Z}   ${RED}$FAIL failed${Z}"
if [ "$FAIL" -eq 0 ]; then
  echo -e "\n  ${G}${B}● GO${Z} — stack is ready for evaluation."
  echo -e "  Open ${C}$BASE/stage${Z} and do the 60-second eyeball pass in PREFLIGHT.md."
  [ "$WARN" -gt 0 ] && echo -e "  (${A}$WARN warning(s)${Z} above won't block the demo — the scripted Demo tab covers them.)"
else
  echo -e "\n  ${RED}${B}● NO-GO${Z} — fix the ${RED}✗${Z} items above, then re-run ./preflight.sh."
  echo -e "  ${A}Fallback:${Z} even if live is broken, ${C}$BASE/demo${Z} (or press D in /stage) works with zero backend data."
fi
echo
exit "$([ "$FAIL" -eq 0 ] && echo 0 || echo 1)"
