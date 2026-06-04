"""
backend.splunk_client
═════════════════════
Minimal Splunk client over raw REST (search export endpoint). No splunk-sdk
dependency — just requests. Returns rows as plain dicts.
"""
from __future__ import annotations

import json
import os
import logging
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
log = logging.getLogger("helix.splunk")


class SplunkClient:
    def __init__(self, api_url: str, user: str, password: str,
                 verify_ssl: bool = False):
        self.api_url = api_url.rstrip("/")
        self.auth = (user, password)
        self.verify_ssl = verify_ssl
        self.session = requests.Session()
        self.session.auth = self.auth
        self.session.verify = verify_ssl

    @classmethod
    def from_env(cls) -> "SplunkClient":
        return cls(
            api_url=os.environ.get("HELIX_SPLUNK_API_URL", "https://localhost:8089"),
            user=os.environ.get("HELIX_SPLUNK_API_USER", "admin"),
            password=os.environ.get("HELIX_SPLUNK_API_PASSWORD", "ChangeMe_Helix_2026"),
            verify_ssl=os.environ.get("HELIX_SPLUNK_VERIFY_SSL", "0") == "1",
        )

    def ping(self) -> bool:
        try:
            r = self.session.get(f"{self.api_url}/services/server/info",
                                  params={"output_mode": "json"}, timeout=5)
            return r.status_code == 200
        except Exception:
            return False

    def search(self, spl: str, earliest: str = "-15m@m",
               latest: str = "now", timeout: int = 60) -> list[dict]:
        """Run a oneshot search via the export endpoint. Returns result rows."""
        if not spl.strip().startswith(("search ", "|")):
            spl = "search " + spl
        try:
            r = self.session.post(
                f"{self.api_url}/services/search/jobs/export",
                data={"search": spl, "output_mode": "json",
                      "earliest_time": earliest, "latest_time": latest},
                stream=True, timeout=timeout)
            r.raise_for_status()
            rows = []
            for line in r.iter_lines():
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    if "result" in obj:
                        rows.append(obj["result"])
                except json.JSONDecodeError:
                    continue
            return rows
        except Exception as e:
            log.warning("Splunk search failed: %s", e)
            return []
