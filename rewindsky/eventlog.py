"""Build a time-stamped "event log" from cached Astro-COLIBRI responses.

One row = one piece of information and the moment it became available.
All times are naive UTC ISO strings. Nothing here touches the network.

Knowledge-time rules (what makes replay leak-free):
  * LVK alert revisions: `last_modified` of the archive revision, NOT `ivorn_time`.
    A revision may be re-saved later with extra fields (e.g. S250818k_3 added a
    comment ~3 h after notice #3), so the original notice time would leak that comment.
  * GCN circulars: NASA's `createdOn` rounded up to the next second (data/gcn/<event>/<n>.json); the `DATE:` header
    of the platform text is the fallback (it agrees with createdOn to < 1 s, but can be up to 1 s early).
Only the first LVK_REVISIONS archive revisions are used; later ones are platform
re-archiving (follow-up lists, links) and carry no new alert information.
"""
from __future__ import annotations

import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "events"

EVENT = "S250818k"
LVK_REVISIONS = range(5)  # S250818k_0 .. S250818k_4


def _load(name: str) -> dict:
    rec = json.loads((RAW / name).read_text())
    assert rec["status"] == 200, (name, rec["status"])
    return rec["body"]


def _nasa_time(number: int, event: str):
    """NASA `createdOn` (ms) rounded UP to the next second, if the circular JSON was downloaded."""
    f = ROOT / "data" / "gcn" / event / f"{number}.json"
    if not f.exists():
        return None
    ms = int(json.loads(f.read_text())["createdOn"])
    return datetime.fromtimestamp(math.ceil(ms / 1000), tz=timezone.utc).replace(tzinfo=None)


def _gcn_time(text: str) -> datetime:
    m = re.search(r"^DATE:\s+(\d\d)/(\d\d)/(\d\d) (\d\d:\d\d:\d\d)", text, re.M)
    if not m:
        raise ValueError("no DATE header")
    yy, mm, dd, hms = m.groups()
    return datetime.strptime(f"20{yy}-{mm}-{dd} {hms}", "%Y-%m-%d %H:%M:%S")


def build(event: str = EVENT) -> dict:
    rows = []

    # --- LVK alert revisions -------------------------------------------------
    t_event = None
    for i in LVK_REVISIONS:
        b = _load(f"event__gw_{event}_{i}.json")
        t_event = t_event or b["time"][:19]
        areas = json.loads(b["map_areas"]) if b.get("map_areas") else {}
        rows.append({
            "t": b["last_modified"],
            "source": "LVK",
            "kind": "gw_alert",
            "label": f'{b["alert_type"]} #{int(b["pkt_ser_num"])}',
            "revision": b["archive_id"],
            "notice_time": b["ivorn_time"],
            "data": {
                "ra": b["ra"], "dec": b["dec"], "distance_mpc": b["distance"],
                "area50": areas.get("50"), "area90": areas.get("90"),
                "far_per_yr": b["far"],
                "p_BNS": b["gw_BNS"], "p_NSBH": b["gw_NSBH"], "p_BBH": b["gw_BBH"],
                "p_hasNS": b["gw_hasNS"], "pipeline": b["gw_pipeline"],
                "instruments": b["instrument"], "comment": b["comment"],
                "circular_url": b["url"],
                "contours": json.loads(b["gw_contours"]) if b.get("gw_contours") else None,
            },
        })

    # --- GCN circulars -------------------------------------------------------
    fu = _load(f"followup_summary__probe_followup_{event}.json")
    for r in fu["reports"]:
        text = r.get("body") or r.get("text") or ""
        num = re.search(r"^NUMBER:\s+(\d+)", text, re.M)
        rows.append({
            "t": ((_nasa_time(int(num.group(1)), event) if num else None) or _gcn_time(text)).isoformat(),
            "source": r.get("observatory_short_name") or r.get("observatory") or "unknown",
            "kind": "gcn_circular",
            "label": f'GCN {num.group(1)}' if num else "GCN ?",
            "revision": None,
            "notice_time": None,
            "data": {
                "number": int(num.group(1)) if num else None,
                "category": r.get("observation_category"),
                "subject": (r.get("subject") or "").strip(),
                "role": r.get("role"),
                "has_photometry": r.get("has_photometry"),
                "has_optical_followup": r.get("has_optical_followup"),
                "summary": r.get("summary"),
                "report_url": r.get("report_url"),
                "text": text,
            },
        })

    rows.sort(key=lambda r: (r["t"], r["kind"] != "gw_alert"))
    return {"event": event, "t0": t_event, "n_rows": len(rows), "rows": rows}


def write(event: str = EVENT) -> Path:
    log = build(event)
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{event}.json"
    path.write_text(json.dumps(log, ensure_ascii=False))
    return path


if __name__ == "__main__":
    p = write()
    log = json.loads(p.read_text())
    print(p, log["n_rows"], "rows; t0 =", log["t0"])
