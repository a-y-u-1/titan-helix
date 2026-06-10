# TITAN HELIX — Pre-flight checklist

Run top to bottom before a judge evaluates. Three gates: **automated → visual → environment**,
then a 60-second demo script and the two questions you'll be asked.

---

## ⏱ T-10 min — automated gate (must be GO)

```bash
cd titan-helix
./preflight.sh
```

It checks the things a judge will actually hit and ends in **● GO** or **● NO-GO**:

- [ ] Splunk container running & healthy, management API responding
- [ ] HEC accepting events
- [ ] **Indexes contain data** (`helix_metrics / traces / logs / incidents` non-empty)
- [ ] Backend `/health` up, **inject armed** (HEC configured in backend)
- [ ] `/api/graph` returns ~29 services (live graph populated)
- [ ] **AI investigation returns the full 6-agent chain** (+ tells you deterministic vs LLM)
- [ ] Incidents present (Memory agent recall ready)
- [ ] `/`, `/demo`, `/stage` all return 200
- [ ] RAM / disk headroom

If **NO-GO**, fix the red items (each prints a one-line remedy), re-run. Most issues clear with
`./setup.sh --reload-data` (empty indexes) or `./setup.sh --wipe` (Splunk/HEC wonky).

> Warnings (yellow) don't block you — the scripted **Demo** tab covers anything that's thin.

---

## ⏱ T-5 min — visual pass (your eyes, ~60s)

Open **http://localhost:8080/stage** and confirm by eye:

**Live console** (opens by default)
- [ ] Graph renders as a clean spread of ~29 nodes — not a collapsed blob, no overlapping pile
- [ ] Hover a node → tooltip shows state / error / cpu / dependencies
- [ ] Click **checkout-api** → Inspector fills (metrics, upstream/downstream, errors, hosts)
- [ ] Click **🧠 Investigate with AI agent mesh** → 6 agents reveal in sequence with confidence bars, ending in the green Executive verdict
- [ ] **SPL** tab → top block shows a live query for the selected service

**Demo** (press **D**)
- [ ] "Switching to Demo view — mocked data" pop-up appears, then clears
- [ ] Cascade plays: **feature-store-db reddens first**, then feature-store → fraud-scoring → checkout-api → pos-gateway (5 nodes)
- [ ] HUD shows the **countdown** ("ends ~Xs") and the phase timeline fills
- [ ] At the incident phase it auto-opens **AI Reasoning** and reaches the verdict
- [ ] After it finishes, **click an earlier phase** → graph + narrative scrub back to that moment
- [ ] Press **L** → back to Live; badge returns to green "LIVE · Splunk"

---

## ⏱ T-2 min — environment

- [ ] Browser zoom at **100%** (Ctrl+0), window **full-screen** (F11)
- [ ] Close other tabs; silence Slack/email/OS notifications
- [ ] If projecting: mirror tested, resolution sane (the layout is responsive but check the rail isn't cramped)
- [ ] `tail -f backend.log` open in a spare terminal (optional, to catch anything mid-demo)
- [ ] Water within reach 🙂

**Fallback rule:** if the live graph ever looks wrong or laggy, press **D**. The scripted demo
needs zero backend data and cannot desync — it's your safety net. Never debug live in front of a judge.

---

## 🎬 60-second demo script (what to click + say)

1. **Open `/stage` (Live).** "This is a *live* view of an enterprise's service graph — 29 services, dependencies *inferred by AI* from trace data, not hand-drawn. This is real Splunk data: right now everything's green and healthy."
2. **Press `D` → Demo.** "Now I'll show a real failure scenario play out. This is our scripted incident — deterministic, so it runs the same every time." (Pop-up confirms it's mocked data.)
3. **Point at `feature-store-db` going red first.** "Notice the root cause lights up *before* any errors appear — it's CPU-saturated but still returning 200s. That's the silent failure normal alerting misses."
4. **Follow the cascade.** "It propagates along the dependency edges — fraud-scoring times out, checkout-api throws 503s, and ap-south-1 POS terminals drop. Five services, in order."
5. **Open AI Reasoning** (auto-opens in demo). "Six agents reason over the live data: Observer flags the CPU anomaly, **Memory recalls the matching past incident**, Correlation proves checkout-api is a symptom not the cause, Prediction forecasts the POS outage, Remediation ranks the fix. The Executive verdict: root cause feature-store-db, deploy the hotfix."
6. **Scrub the timeline** (post-run). "And it's fully explorable — click any phase to see exactly what was happening at that step."

---

## ❓ The two questions you'll get — short answers

**"Isn't this just Datadog / Dynatrace Davis / BigPanda / Moogsoft?"**
Those correlate and alert. The differentiator here is the **visible reasoning trail** — you watch
the agents debate and cite the SPL evidence behind every claim, and it's **Splunk-native**
(your existing data, your existing platform), not another silo. The AI doesn't just say "anomaly
on checkout-api" — it explains *why checkout-api is innocent* and names the real culprit.

**"Is the AI real, or scripted?"**
The agent mesh reasons over real Splunk telemetry. By default it's **deterministic** — every
conclusion is computed from the actual data (the CPU numbers, the trace timings, the incident
history), with templated prose. Flip on an Anthropic API key (`HELIX_LLM_API_KEY`) and the same
mesh uses **real Claude** for the language — the badge in the AI tab shows which mode is live.
The *demo* is scripted for stage safety, but the live console runs the genuine mesh against
Splunk; the preflight above confirms `/api/investigate` returns a real 6-agent chain.

> Synthetic data is a **feature, not a weakness**: because we control the ground-truth scenario,
> we can *prove* the AI reached the correct answer — there's an answer key.
