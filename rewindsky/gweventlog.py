"""Build the time-stamped event log of a gravitational-wave event from PRIMARY sources.

Sources (all cached on disk, nothing here touches the network):
  * LVK notices        data/gracedb/<event>/<event>-<n>-<type>.xml   (time = VOEvent distribution time)
  * sky maps           data/skymaps/<event>/<name>.fits.gz           (flat, rasterised from the GraceDB files)
  * GCN circulars      data/gcn/<event>/<n>.json                     (time = NASA `createdOn`, ms resolution)
  * Astro-COLIBRI      data/raw/event__gw_<event>_<i>.json           (what the platform showed; cross-check only)

Knowledge-time rules
  * LVK alert        : the notice distribution time (when the machine-readable alert left GCN), NOT the
                       platform's `last_modified` (which lags by ~10-20 s and may be re-saved later).
  * joint map        : same notice as the alert that carries the `External Coincidence` block.
  * circular         : `createdOn` of the NASA GCN archive, rounded UP to the next full second.
  * GraceDB map file : creation time of the file in the GraceDB log (can precede the notice that
                       references it by many hours); stored as kind `gracedb_map` and NOT shown to the
                       default replay, only used for sensitivity analyses.
Each row also carries `platform_time` when the platform stored the same notice, so the lag is auditable.
"""
from __future__ import annotations

import json
import math
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

from . import skymaps as sm

ROOT = Path(__file__).resolve().parent.parent
SEC_PER_YR = 365.25 * 86400

# (regex on the circular subject, source, category). The earliest match in the subject wins. Transparent and deterministic:
# these categories are NOT the platform's LLM labels.
CIRCULAR_RULES = [
    (r"Identification of a GW|Updated Sky|Updated Coincidence|Coincidence False Alarm", "LVK", "general_report"),
    (r"LST-1 and MAGIC", "LST-1+MAGIC", "vhe_followup"),
    (r"INTEGRAL", "INTEGRAL", "gamma_followup"),          # before the BAT rule: its title mentions the BAT counterpart
    (r"Fermi-GBM", "Fermi-GBM", "gamma_followup"),
    (r"Konus", "Konus-Wind", "gamma_followup"),
    (r"BAT-GUANO|BAT counterpart", "Swift/BAT-GUANO", "gamma_followup"),
    (r"EP-FXT", "EP-FXT", "xray_followup"),
    (r"XRT", "Swift/XRT", "xray_followup"),
    (r"UVOT", "Swift/UVOT", "optical_followup"),
    (r"Kinder", "Kinder", "optical_followup"),
    (r"COLIBR", "COLIBRI", "optical_followup"),
    (r"GROWTH-India", "GROWTH-India", "optical_followup"),
    (r"GOT", "GOT", "optical_followup"),
    (r"IceCube", "IceCube", "neutrino_followup"),
    (r"MAXI", "MAXI", "xray_followup"),
    (r"EP-WXT|Einstein Probe", "Einstein Probe", "xray_followup"),
    (r"GECAM|SVOM/GRM|MSU cubesats", "GRB monitors", "gamma_followup"),
    (r"CHIME/FRB|Repeating Bursts|Time Machine", "FRB", "radio_followup"),
    (r"NED Galaxies|GLADEnet", "NED/GLADE", "general_report"),
    (r"Pan-STARRS|SOAR|ATLAS|FTW|MMT|ePESSTO|Zwicky|Keck|NEWFIRM|GECKO|BOOTES|CAHA|WFST|MASTER|WINTER|Gemini|DECam"
     r"|AbAO|AZT-33IK|LIGHETR|Virtual Telescope", "", "optical_followup"),     # "" = use the matched name
    (r"DDOTI", "DDOTI", "optical_followup"),
    (r"SAGUARO", "SAGUARO", "optical_followup"),
    (r"HCT", "HCT", "optical_followup"),
    (r"GRANDMA", "GRANDMA", "optical_followup"),
]

UNMATCHED: list[str] = []                     # circular subjects no rule matched (check after building a new event)

MAP_NAMES = {  # GraceDB file name in the notice -> our map key
    "bayestar.multiorder.fits": "bayestar",
    "Bilby.multiorder.fits": "bilby",
    "Bilby.offline0.multiorder.fits": "bilby_offline0",
    "combined-ext.multiorder.fits": "combined",
}


def map_key(url: str) -> str:
    """'.../files/bayestar.multiorder.fits,2' -> 'bayestar_2'"""
    name, _, ver = url.rsplit("/", 1)[-1].partition(",")
    base = MAP_NAMES.get(name) or re.sub(r"[^a-z0-9]+", "_", name.replace(".multiorder.fits", "").lower()).strip("_")
    return f"{base}_{ver or 0}"


def _iso(s: str) -> str:
    return s.replace("Z", "").split(".")[0]


def _parse_notice(path: Path) -> dict:
    root = ET.parse(path).getroot()
    P = {p.get("name"): p.get("value") for p in root.iter("Param")}
    G = {g.get("name"): {p.get("name"): p.get("value") for p in g.iter("Param")} for g in root.iter("Group")}
    return {"params": P, "groups": G, "time": _iso(root.find(".//Who/Date").text),
            "event_time": root.find(".//ISOTime").text.rstrip("Z")}


def _classify_circular(subject: str, event: str = "") -> tuple[str, str]:
    """The author's instrument is the one named FIRST in the subject ("COLIBRI upper limits on ... Swift/XRT
    sources" is a COLIBRI circular), so the rule whose pattern matches earliest in the text wins.
    Text after the event name is tried first ("EP-WXT trigger 017.. / LIGO..S250206dm: FTW optical" is an FTW
    circular); if nothing matches there the whole subject is used. Subjects that match no rule are recorded in
    UNMATCHED and get a keyword-based category with source "unknown"."""
    texts = ([subject.split(event, 1)[1]] if event and event in subject else []) + [subject]
    for text in texts:
        hits = [(m.start(), i, src, cat) for i, (pat, src, cat) in enumerate(CIRCULAR_RULES)
                if (m := re.search(pat, text))]
        if hits:
            _, _, src, cat = min(hits)
            if not src:                                      # rule without a fixed name: use the matched text
                src = next(m.group(0) for pat, s_, _c in CIRCULAR_RULES if not s_ and (m := re.search(pat, text)))
            return src, cat
    UNMATCHED.append(subject)
    low = subject.lower()
    cat = ("xray_followup" if re.search(r"x-ray|xrt|nustar|chandra", low) else
           "radio_followup" if re.search(r"radio|vla|meerkat|gmrt|atca", low) else
           "gamma_followup" if re.search(r"gamma|grb|gbm|integral|konus", low) else
           "optical_followup" if re.search(r"optical|upper limit|photometr|spectro|observation", low) else
           "general_report")
    return "unknown", cat


def build(event: str, t0: str, n_alerts: int) -> dict:
    """Event log for `event`; `t0` is the GW event time (ISO, UTC); `n_alerts` the number of LVK notices."""
    gdb = ROOT / "data" / "gracedb" / event
    skydir = ROOT / "data" / "skymaps" / event
    rows = []

    # ---- platform revisions, keyed by ivorn (first revision of each notice) ------------------------
    plat = {}
    for f in sorted((ROOT / "data" / "raw").glob(f"event__gw_{event}_*.json")):
        b = json.loads(f.read_text())["body"]
        cur = plat.setdefault(b["ivorn"], b)
        if b["last_modified"] < cur["last_modified"]:
            plat[b["ivorn"]] = b

    # ---- LVK notices + joint maps ------------------------------------------------------------------
    for xmlf in sorted(gdb.glob(f"{event}-*-*.xml"), key=lambda p: int(p.name.split("-")[1])):
        n = _parse_notice(xmlf)
        P, G = n["params"], n["groups"]
        num = int(xmlf.name.split("-")[1])
        key = map_key(P["skymap_fits"])
        flat = skydir / f"{key}.fits.gz"
        prob, ns = sm.load_flat(flat)
        cls = G["Classification"]
        p_astro_terr = float(cls["Terrestrial"])
        ivorn = f"ivo://gwnet/LVC#{event}-{num}-{P['AlertType']}"
        pf = plat.get(ivorn)
        ra, dec = sm.peak(prob, ns)
        area = {lvl: sm.credible_area(gdb / _orig_name(key), lvl, 1024) for lvl in (0.5, 0.9)}
        ext = G.get("External Coincidence")
        rows.append({
            "t": n["time"], "source": "LVK", "kind": "gw_alert",
            "label": f"{P['AlertType']} #{num}",
            "revision": pf["archive_id"] if pf else None,
            "notice_time": n["time"], "platform_time": pf["last_modified"] if pf else None,
            "data": {
                "ra": ra, "dec": dec, "distance_mpc": pf["distance"] if pf else None,
                "area50": round(area[0.5], 1), "area90": round(area[0.9], 1),
                "far_per_yr": float(P["FAR"]) * SEC_PER_YR, "significant": P["Significant"] == "1",
                "p_BNS": float(cls["BNS"]), "p_NSBH": float(cls["NSBH"]), "p_BBH": float(cls["BBH"]),
                "p_terrestrial": p_astro_terr, "p_hasNS": float(G["Properties"]["HasNS"]),
                "pipeline": P["Pipeline"], "instruments": P["Instruments"], "skymap": key,
                "comment": "", "circular_url": "", "has_external": ext is not None,
                "contours": sm.contours_geojson(gdb / _orig_name(key)),
            },
        })
        if ext:
            jkey = map_key(ext["joint_skymap_fits"])
            jprob, jns = sm.load_flat(skydir / f"{jkey}.fits.gz")
            jra, jdec = sm.peak(jprob, jns)
            jarea = {lvl: sm.credible_area(gdb / _orig_name(jkey), lvl, 1024) for lvl in (0.5, 0.9)}
            rows.append({
                "t": n["time"], "source": "LVK+Swift", "kind": "joint_skymap",
                "label": f"Joint map v{jkey.rsplit('_', 1)[1]}", "revision": None,
                "notice_time": n["time"], "platform_time": None,
                "data": {"ra": jra, "dec": jdec, "area50": round(jarea[0.5], 4), "area90": round(jarea[0.9], 1),
                         "skymap": jkey, "external_observatory": ext["External_Observatory"],
                         "external_search": ext["External_Search"],
                         "time_difference_s": float(ext["Time_Difference"]),
                         "time_coincidence_far_hz": float(ext["Time_Coincidence_FAR"]),
                         "joint_far_hz": float(ext["Time_Sky_Position_Coincidence_FAR"]),
                         "external_notice_id": ext["External_GCN_Notice_Id"],
                         "contours": sm.contours_geojson(gdb / _orig_name(jkey))},
            })

    # ---- GraceDB sky-map files (earlier than the notices that reference them) ----------------------
    for l in json.loads((gdb / "logs.json").read_text())["log"]:
        fn = l.get("filename") or ""
        if "multiorder" in fn and l.get("file_version") is not None:
            name = fn.replace(".multiorder.fits", "")
            key = map_key(f"{fn},{l['file_version']}")
            rows.append({"t": _iso(l["created"].replace(" UTC", "").replace(" ", "T")), "source": "GraceDB",
                         "kind": "gracedb_map", "label": f"{name},{l['file_version']}", "revision": None,
                         "notice_time": None, "platform_time": None,
                         "data": {"skymap": key, "comment": l.get("comment", "")}})

    # ---- GCN circulars (NASA) ----------------------------------------------------------------------
    for f in sorted((ROOT / "data" / "gcn" / event).glob("*.json")):
        d = json.loads(f.read_text())
        subj = " ".join(d["subject"].split())
        body = d.get("body") or ""
        src, cat = _classify_circular(subj, event)
        dup = re.search(r"duplicate submission of (\d{5})", subj)
        # createdOn has ms resolution; round UP so that a circular is never visible before it existed
        t = datetime.fromtimestamp(math.ceil(int(d["createdOn"]) / 1000), tz=timezone.utc).replace(tzinfo=None)
        rows.append({
            "t": t.isoformat(), "source": src, "kind": "gcn_circular", "label": f"GCN {d['circularId']}",
            "revision": None, "notice_time": None, "platform_time": None,
            "data": {"number": int(d["circularId"]), "category": cat, "subject": subj,
                     "duplicate_of": int(dup.group(1)) if dup else None, "text": body,
                     "submitter": d["submitter"]},
        })

    order = {"gw_alert": 0, "joint_skymap": 1, "gracedb_map": 2, "gcn_circular": 3}
    rows.sort(key=lambda r: (r["t"], order[r["kind"]]))
    n_gw = sum(r["kind"] == "gw_alert" for r in rows)
    assert n_gw == n_alerts, f"expected {n_alerts} LVK notices, found {n_gw}"
    return {"event": event, "t0": t0, "n_rows": len(rows), "rows": rows}


def _orig_name(key: str) -> str:
    """Our map key ('bayestar_0') -> the raw GraceDB file in data/gracedb/<event>/ (see scripts/fetch_gw_event.py)."""
    return f"{key}.fits"


def write(event: str, t0: str, n_alerts: int) -> Path:
    log = build(event, t0, n_alerts)
    out = ROOT / "data" / "events" / f"{event}.json"
    out.write_text(json.dumps(log, ensure_ascii=False))
    return out


if __name__ == "__main__":
    p = write("S241125n", "2024-11-25T01:01:16", 7)
    log = json.loads(p.read_text())
    print(p, log["n_rows"], "rows")
