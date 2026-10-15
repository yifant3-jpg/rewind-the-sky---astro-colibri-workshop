"""Replay engine: what was known about an event at time T?

`state_at(log, T)` only ever looks at log rows with `t <= T`, then summarises them.
The result is plain JSON-serialisable data (the future web viewer reads the same thing).
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
EVENTS = ROOT / "data" / "events"


def load_log(event: str) -> dict:
    return json.loads((EVENTS / f"{event}.json").read_text())


def parse_t(t) -> datetime:
    """Naive UTC datetime. Accepts datetimes and ISO strings, with or without a timezone ('Z', '+02:00')."""
    if not isinstance(t, datetime):
        t = datetime.fromisoformat(str(t).replace("Z", "+00:00"))
    if t.tzinfo is not None:
        t = t.astimezone(timezone.utc).replace(tzinfo=None)
    return t


def t_after(log: dict, **delta) -> datetime:
    """T expressed relative to the event: t_after(log, minutes=30) -> T0 + 30 min."""
    return parse_t(log["t0"]) + timedelta(**delta)


def _lobes_90(contours, min_points: int = 50) -> list:
    """Centroids of the large closed loops of the 90% contour = the sky-map 'lobes'.

    Two-detector localisations are often bimodal (a north and a south lobe), so the
    single best-position pixel can jump between lobes while the map barely changes.
    """
    if not contours:
        return []
    out = []
    for f in contours["features"]:
        if f["properties"]["credible_level"] != 0.9:
            continue
        geom = f["geometry"]
        lines = geom["coordinates"] if geom["type"] == "MultiLineString" else [geom["coordinates"]]
        for ln in lines:
            if len(ln) < min_points:
                continue
            ra, dec = np.radians([p[0] for p in ln]), np.radians([p[1] for p in ln])
            v = np.array([np.cos(dec) * np.cos(ra), np.cos(dec) * np.sin(ra), np.sin(dec)]).mean(axis=1)
            v /= np.linalg.norm(v)
            out.append({"ra": round(float(np.degrees(np.arctan2(v[1], v[0])) % 360), 1),
                        "dec": round(float(np.degrees(np.arcsin(v[2]))), 1)})
    return out


def _alert_summary(row: dict) -> dict:
    d = row["data"]
    return {
        "label": row["label"],
        "available_at": row["t"],
        "peak_ra": d["ra"], "peak_dec": d["dec"],  # max-probability pixel, NOT the localisation
        "lobes_90": _lobes_90(d["contours"]),
        "area50_deg2": d["area50"], "area90_deg2": d["area90"],
        "distance_mpc": d.get("distance_mpc"),
        "p_hasNS_if_astro": d["p_hasNS"], "p_BNS": d["p_BNS"],
        "p_NSBH": d["p_NSBH"], "p_BBH": d["p_BBH"],
        "p_terrestrial": round(d["p_terrestrial"] if "p_terrestrial" in d
                               else 1 - d["p_BNS"] - d["p_NSBH"] - d["p_BBH"], 4),
        "far_per_yr": d["far_per_yr"],
        "significant": d.get("significant"),   # None when the source does not say (older logs)
        "pipeline": d.get("pipeline"),
        "skymap": d.get("skymap"),
        "comment": d["comment"],
        "has_contours": d["contours"] is not None,
    }


def _joint_summary(row: dict) -> dict:
    d = row["data"]
    return {
        "label": row["label"], "available_at": row["t"], "skymap": d["skymap"],
        "peak_ra": d["ra"], "peak_dec": d["dec"],
        "area50_deg2": d["area50"], "area90_deg2": d["area90"],
        "external_observatory": d["external_observatory"], "external_search": d["external_search"],
        "time_difference_s": d["time_difference_s"],
        "time_coincidence_far_hz": d["time_coincidence_far_hz"], "joint_far_hz": d["joint_far_hz"],
    }


def state_at(log: dict, T, include_text: bool = False) -> dict:
    T = parse_t(T)
    t0 = parse_t(log["t0"])
    known = [r for r in log["rows"] if parse_t(r["t"]) <= T]

    alerts = [r for r in known if r["kind"] == "gw_alert"]
    joints = [r for r in known if r["kind"] == "joint_skymap"]
    circulars = [r for r in known if r["kind"] == "gcn_circular"]

    snap = {
        "event": log["event"],
        "T": T.isoformat(),
        "hours_since_event": round((T - t0).total_seconds() / 3600, 3),
        "n_alerts_received": len(alerts),
        "latest_alert": _alert_summary(alerts[-1]) if alerts else None,
        "alert_history": [_alert_summary(a) for a in alerts],
        "latest_joint": _joint_summary(joints[-1]) if joints else None,
        "joint_history": [_joint_summary(j) for j in joints],
        "n_circulars": len(circulars),
        "n_circulars_unique": sum(1 for c in circulars if not c["data"].get("duplicate_of")),
        "circulars_by_category": dict(Counter(
            (c["data"]["category"] or "other") for c in circulars)),
        "observatories_reporting": sorted({c["source"] for c in circulars}),
        "circulars": [
            {"label": c["label"], "available_at": c["t"], "source": c["source"],
             "category": c["data"]["category"], "subject": c["data"]["subject"],
             "duplicate_of": c["data"].get("duplicate_of"),
             **({"text": c["data"]["text"]} if include_text else {})}
            for c in circulars],
    }
    check_no_leak(log, snap)
    return snap


def check_no_leak(log: dict, snap: dict) -> None:
    """Hard guarantee: nothing in the snapshot is dated after T.

    Also re-derives the allowed rows from scratch, so a bug in state_at can't hide here.
    """
    T = parse_t(snap["T"])
    allowed = {(r["label"], r["t"]) for r in log["rows"] if parse_t(r["t"]) <= T}
    forbidden = {(r["label"], r["t"]) for r in log["rows"] if parse_t(r["t"]) > T}

    shown = {(a["label"], a["available_at"]) for a in snap["alert_history"]}
    shown |= {(c["label"], c["available_at"]) for c in snap["circulars"]}
    shown |= {(j["label"], j["available_at"]) for j in snap.get("joint_history", [])}
    leaked = shown & forbidden
    assert not leaked, f"LEAK at T={T}: {sorted(leaked)}"
    assert shown <= allowed, f"unknown rows in snapshot: {sorted(shown - allowed)}"
    for a in snap["alert_history"]:
        assert parse_t(a["available_at"]) <= T
    # counts must agree with the visible lists
    assert snap["n_alerts_received"] == len(snap["alert_history"])
    assert snap["n_circulars"] == len(snap["circulars"])
    for j in snap.get("joint_history", []):
        assert parse_t(j["available_at"]) <= T
    # the "latest" summaries must be items of the (already checked) histories
    for latest, hist in (("latest_alert", "alert_history"), ("latest_joint", "joint_history")):
        x = snap.get(latest)
        if x is not None:
            assert parse_t(x["available_at"]) <= T, f"LEAK in {latest} at T={T}"
            assert (x["label"], x["available_at"]) in {(h["label"], h["available_at"]) for h in snap.get(hist, [])}
    assert sum(snap["circulars_by_category"].values()) == snap["n_circulars"]


def _area(x) -> str:
    """Areas below 0.01 deg2 are below the resolution of the maps involved: quote them as an upper limit."""
    return "<0.01" if x is not None and x < 0.01 else f"{x:g}"


def format_snapshot(snap: dict) -> str:
    lines = [f'=== {snap["event"]} @ {snap["T"]}  (T0 + {snap["hours_since_event"]:.2f} h) ===']
    a = snap["latest_alert"]
    if a is None:
        lines.append("No alert received yet.")
    else:
        sig = {True: "  [SIGNIFICANT alert]", False: "  [LOW-SIGNIFICANCE alert]", None: ""}[a.get("significant")]
        dist = f'~{a["distance_mpc"]:.0f} Mpc' if a.get("distance_mpc") else "n/a"
        lines.append(
            f'Latest LVK alert: {a["label"]} (available {a["available_at"]}){sig}\n'
            f'  localisation: 50%={a["area50_deg2"]} deg2  90%={a["area90_deg2"]} deg2  '
            f'lobes(90%): ' + ", ".join(f'({l["ra"]:.0f},{l["dec"]:+.0f})' for l in a["lobes_90"]) + '\n'
            f'  peak-probability pixel (not the localisation!): RA={a["peak_ra"]:.1f} Dec={a["peak_dec"]:+.1f}\n'
            f'  distance {dist}  FAR={a["far_per_yr"]:.3g} per year\n'
            f'  class: Terrestrial={a["p_terrestrial"]:.0%} BNS={a["p_BNS"]:.0%} '
            f'NSBH={a["p_NSBH"]:.0%} BBH={a["p_BBH"]:.0%};  '
            f'P(has NS | astrophysical)={a["p_hasNS_if_astro"]}\n'
            f'  comment: {a["comment"] or "(none)"}')
        lines.append(f'Alerts so far: {snap["n_alerts_received"]} -> '
                     + ", ".join(h["label"] for h in snap["alert_history"]))
    j = snap.get("latest_joint")
    if j:
        lines.append(
            f'External coincidence ({j["external_observatory"]} {j["external_search"]}), {j["label"]} '
            f'(available {j["available_at"]}):\n'
            f'  joint map 50%={_area(j["area50_deg2"])} deg2  90%={_area(j["area90_deg2"])} deg2, '
            f'peak RA={j["peak_ra"]:.1f} Dec={j["peak_dec"]:+.1f}\n'
            f'  GRB candidate {j["time_difference_s"]:.2f} s after the GW; '
            f'coincidence FAR: time only {j["time_coincidence_far_hz"]:.2g} Hz, '
            f'time+sky {j["joint_far_hz"]:.2g} Hz (as stated in the notice)')
    n_u = snap.get("n_circulars_unique", snap["n_circulars"])
    dup = f' ({snap["n_circulars"] - n_u} duplicate submissions)' if snap["n_circulars"] != n_u else ""
    lines.append(f'GCN circulars so far: {n_u}{dup}  {snap["circulars_by_category"]}')
    for c in snap["circulars"][-5:]:
        lines.append(f'  {c["available_at"]}  {c["label"]:10} {c["source"]:16} {c["subject"][:70]}')
    return "\n".join(lines)
