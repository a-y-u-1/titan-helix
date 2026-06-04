#!/usr/bin/env python3
"""
TITAN HELIX · Splunk Dump Loader
══════════════════════════════════════════════════════════════════════════════
Loads a JSONL dump (HEC-envelope format, e.g. from historical_generator.py)
into Splunk via the HTTP Event Collector, in batches. Because each line carries
a `time` field, Splunk places every event at its historical timestamp.

USAGE
─────
    pip install requests

    # Dry run — validate the file without sending
    python3 load_to_splunk.py data/history.jsonl --dry-run

    # Load into Splunk
    python3 load_to_splunk.py data/history.jsonl \\
        --hec-url http://localhost:8088 \\
        --hec-token YOUR-UUID-TOKEN

    # Tune batch size / parallelism for big files
    python3 load_to_splunk.py data/history.jsonl \\
        --hec-url http://localhost:8088 --hec-token ... \\
        --batch 1000

VERIFY AFTER LOADING (in Splunk):
    index=helix_* earliest=-8d
    | stats count by index, sourcetype
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

try:
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except ImportError:
    sys.exit("Missing dep: pip install requests")


def load(path: str, hec_url: str, hec_token: str, batch: int = 500,
         verify_ssl: bool = False, dry_run: bool = False):
    p = Path(path)
    if not p.exists():
        sys.exit(f"File not found: {path}")

    total_lines = sum(1 for _ in open(p))
    sys.stderr.write(f"[loader] {path} · {total_lines:,} events\n")

    if dry_run:
        # Validate every line is parseable + has required envelope keys
        bad = 0
        seen_st: dict[str, int] = {}
        with open(p) as fh:
            for i, line in enumerate(fh, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                    assert "event" in ev and "sourcetype" in ev and "index" in ev
                    seen_st[ev["sourcetype"]] = seen_st.get(ev["sourcetype"], 0) + 1
                except Exception as e:
                    bad += 1
                    if bad <= 5:
                        sys.stderr.write(f"  line {i}: {e}\n")
        sys.stderr.write(f"[loader] dry-run OK · {bad} bad lines\n")
        sys.stderr.write("[loader] sourcetypes:\n")
        for st, c in sorted(seen_st.items(), key=lambda x: -x[1]):
            sys.stderr.write(f"    {st:32s} {c:>8,}\n")
        # time range
        first_t = last_t = None
        with open(p) as fh:
            for line in fh:
                try:
                    t = json.loads(line)["time"]
                    if first_t is None:
                        first_t = t
                    last_t = t
                except Exception:
                    pass
        if first_t and last_t:
            import datetime as dt
            sys.stderr.write(
                f"[loader] time span: "
                f"{dt.datetime.fromtimestamp(first_t).isoformat()} → "
                f"{dt.datetime.fromtimestamp(last_t).isoformat()}\n")
        return

    if not hec_url or not hec_token:
        sys.exit("Loading requires --hec-url and --hec-token (or use --dry-run)")

    url = hec_url.rstrip("/") + "/services/collector/event"
    session = requests.Session()
    retry = Retry(total=5, backoff_factor=0.5,
                  status_forcelist=(500, 502, 503, 504))
    session.mount("http://", HTTPAdapter(max_retries=retry))
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.headers = {"Authorization": f"Splunk {hec_token}"}
    session.verify = verify_ssl

    sent = failed = 0
    t0 = time.monotonic()
    buf: list[str] = []

    def flush():
        nonlocal sent, failed
        if not buf:
            return
        try:
            r = session.post(url, data="\n".join(buf), timeout=30)
            r.raise_for_status()
            sent += len(buf)
        except Exception as e:
            failed += len(buf)
            sys.stderr.write(f"\n[loader] batch failed ({len(buf)} events): {e}\n")
        buf.clear()

    with open(p) as fh:
        for i, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            buf.append(line)
            if len(buf) >= batch:
                flush()
                if i % (batch * 10) == 0:
                    pct = 100 * i / total_lines
                    rate = sent / max(0.1, time.monotonic() - t0)
                    sys.stderr.write(
                        f"\r[loader] {pct:5.1f}% · sent {sent:,} "
                        f"· {rate:,.0f} ev/s")
                    sys.stderr.flush()
        flush()

    elapsed = time.monotonic() - t0
    sys.stderr.write(
        f"\n[loader] done · sent {sent:,} · failed {failed:,} "
        f"· {elapsed:.1f}s · {sent/max(0.1,elapsed):,.0f} ev/s\n")
    if failed:
        sys.stderr.write(
            "[loader] some batches failed — check HEC token, index permissions, "
            "and that Splunk is reachable.\n")


def main():
    ap = argparse.ArgumentParser(description="Load a JSONL dump into Splunk via HEC")
    ap.add_argument("file", help="Path to JSONL dump file")
    ap.add_argument("--hec-url", default=None, help="e.g. http://localhost:8088")
    ap.add_argument("--hec-token", default=None, help="Splunk HEC token")
    ap.add_argument("--batch", type=int, default=500, help="Events per POST")
    ap.add_argument("--verify-ssl", action="store_true")
    ap.add_argument("--dry-run", action="store_true",
                    help="Validate the file without sending")
    args = ap.parse_args()
    load(args.file, args.hec_url, args.hec_token, batch=args.batch,
         verify_ssl=args.verify_ssl, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
