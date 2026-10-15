"""Minimal Astro-COLIBRI API client with on-disk caching and a daily request budget.

Every request is cached by (method, endpoint, payload) so that re-running a
notebook never spends quota twice. Every *real* network call is appended to
data/request_log.jsonl and counted against DAILY_LIMIT.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import date, datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
LOG_PATH = ROOT / "data" / "request_log.jsonl"
BASE_URL = "https://astro-colibri.science"
DAILY_LIMIT = 100
SAFETY_MARGIN = 5  # never spend the last few requests


class BudgetExceeded(RuntimeError):
    pass


def _load_uid() -> str:
    uid = os.environ.get("COLIBRI_UID")
    if uid:
        return uid
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("COLIBRI_UID="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError("COLIBRI_UID not set (env var or .env)")


def requests_used_today() -> int:
    """Units spent today according to the local log (UTC date)."""
    if not LOG_PATH.exists():
        return 0
    today = date.today().isoformat()
    used = 0
    for line in LOG_PATH.read_text().splitlines():
        rec = json.loads(line)
        if rec["utc"].startswith(today):
            used += rec.get("cost", 1)
    return used


def _cache_key(method: str, endpoint: str, payload: dict | None) -> str:
    blob = json.dumps([method, endpoint, payload], sort_keys=True)
    return hashlib.sha1(blob.encode()).hexdigest()[:12]


class Colibri:
    def __init__(self, uid: str | None = None):
        self.uid = uid or _load_uid()
        RAW_DIR.mkdir(parents=True, exist_ok=True)

    def call(self, method: str, endpoint: str, payload: dict | None = None,
             cost: int = 1, tag: str = "") -> dict | str:
        """Cached request. `payload` is the JSON body (POST) or query params (GET).

        The uid is injected here and is NOT part of the cache key or the saved file.
        """
        key = _cache_key(method, endpoint, payload)
        stem = endpoint.strip("/").replace("/", "_")
        path = RAW_DIR / f"{stem}__{tag or key}.json"
        if path.exists():
            return json.loads(path.read_text())["body"]

        if requests_used_today() + cost > DAILY_LIMIT - SAFETY_MARGIN:
            raise BudgetExceeded(
                f"{requests_used_today()} used today; refusing cost={cost} "
                f"(limit {DAILY_LIMIT}, margin {SAFETY_MARGIN})")

        url = BASE_URL + endpoint
        t0 = time.time()
        if method == "POST":
            body = dict(payload or {})
            body["uid"] = self.uid
            r = requests.post(url, json=body, timeout=60)
        else:
            params = dict(payload or {})
            params["uid"] = self.uid
            r = requests.get(url, params=params, timeout=60)

        with LOG_PATH.open("a") as f:
            f.write(json.dumps({
                "utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "method": method, "endpoint": endpoint, "payload": payload,
                "status": r.status_code, "cost": cost,
                "secs": round(time.time() - t0, 2),
            }) + "\n")

        try:
            parsed = r.json()
        except ValueError:
            parsed = r.text
        record = {"status": r.status_code, "endpoint": endpoint, "method": method,
                  "payload": payload, "body": parsed}
        # Cache everything including errors, so a failing call isn't repeated blindly.
        path.write_text(json.dumps(record, indent=1, ensure_ascii=False))
        return parsed
