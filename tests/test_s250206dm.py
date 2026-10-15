"""S250206dm: cross-checks of the event log against independent primary sources (same spirit as test_s241125n)."""
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from rewindsky.replay import check_no_leak, load_log, parse_t, state_at, t_after  # noqa: E402

LOG_PATH = ROOT / "data" / "events" / "S250206dm.json"
pytestmark = pytest.mark.skipif(not LOG_PATH.exists(), reason="S250206dm log not built")
LOG = load_log("S250206dm") if LOG_PATH.exists() else None


def rows(kind):
    return [r for r in LOG["rows"] if r["kind"] == kind]


def test_structure():
    assert (len(rows("gw_alert")), len(rows("joint_skymap")), len(rows("gcn_circular"))) == (7, 0, 62)
    assert len(rows("gracedb_map")) == 5


def test_first_alert_has_a_high_terrestrial_probability_then_it_collapses():
    a1 = state_at(LOG, t_after(LOG, seconds=40))["latest_alert"]
    assert a1["pipeline"] == "MBTA" and abs(a1["p_terrestrial"] - 0.725) < 0.003
    a2 = state_at(LOG, t_after(LOG, minutes=6))["latest_alert"]
    assert a2["pipeline"] == "pycbc" and a2["p_terrestrial"] < 0.08 and abs(a2["p_NSBH"] - 0.55) < 0.01


def test_areas_match_lvk_circulars_and_the_platform():
    def quoted(n):
        body = json.loads((ROOT / f"data/gcn/S250206dm/{n}.json").read_text())["body"]
        return [float(x) for x in re.findall(r"credible region is ([\d.]+) deg2", body)]
    by_label = {r["label"]: r["data"]["area90"] for r in rows("gw_alert")}
    assert abs(by_label["Initial #3"] - quoted(39175)[0]) < 1          # 1544 (bayestar, the map of the 3-Initial notice)
    assert abs(by_label["Update #4"] - quoted(39178)[0]) < 1           # 1626 (first Bilby)
    assert abs(by_label["Update #6"] - quoted(39184)[0]) < 1           # 910
    assert abs(by_label["Update #7"] - quoted(39231)[0]) < 1           # 547 (final)
    for r in rows("gw_alert"):
        raw = json.loads((ROOT / f"data/raw/event__gw_S250206dm_{r['revision'].split('_')[1]}.json").read_text())["body"]
        assert abs(r["data"]["area90"] - json.loads(raw["map_areas"])["90"]) < 1.5, r["label"]


def test_notice_times_match_gracedb_and_platform_lags():
    gl = json.loads((ROOT / "data/gracedb/S250206dm/logs.json").read_text())["log"]
    created = {l["filename"]: l["created"] for l in gl if (l.get("filename") or "").endswith(".xml")}
    for r in rows("gw_alert"):
        n = int(r["label"].split("#")[1])
        fn = next(f for f in created if f.startswith(f"S250206dm-{n}-"))
        t = datetime.strptime(created[fn], "%Y-%m-%d %H:%M:%S UTC")
        assert abs((parse_t(r["t"]) - t).total_seconds()) <= 5
        assert 4 <= (parse_t(r["platform_time"]) - parse_t(r["t"])).total_seconds() <= 30, r["label"]


def test_key_circulars_and_their_attribution():
    c = {r["data"]["number"]: r for r in rows("gcn_circular")}
    assert c[39176]["source"] == "IceCube" and c[39176]["t"] == "2025-02-06T22:36:53"
    assert c[39216]["source"] == "FRB" and c[39216]["t"] == "2025-02-07T21:26:32"
    assert c[39214]["source"] == "FTW"                                   # EP-WXT is named first, but the author is FTW
    assert c[39194]["source"] == "INTEGRAL" and c[39179]["source"] == "MAXI"


def test_no_iact_circular_among_the_62():
    """The study relies on this: there is no real IACT history to compare with for this event."""
    names = ("MAGIC", "LST-1", "H.E.S.S", "VERITAS", "CTAO", "HAWC", "LHAASO")
    for p in (ROOT / "data/gcn/S250206dm").glob("*.json"):
        d = json.loads(p.read_text())
        text = d["subject"] + " " + (d.get("body") or "")
        assert not any(n in text for n in names), (p.name, names)


def test_neutrino_candidate_slides_out_of_the_localisation():
    """The IceCube track is inside the 90 % region of the map it was computed from and outside the final one."""
    import healpy as hp
    import numpy as np
    from rewindsky import skymaps as sm, s250206dm as E

    def level(name):
        p, ns = sm.load_flat(ROOT / E.SK / f"{name}.fits.gz")
        order = np.argsort(p)[::-1]
        cum = np.empty_like(p)
        cum[order] = np.cumsum(p[order])
        return cum[hp.ang2pix(ns, *E.ICECUBE, nest=True, lonlat=True)]
    assert level("bayestar_1") < 0.9 < level("bilby_offline1_0")
    assert level("bilby_offline1_0") > 0.97


def test_nothing_leaks_at_any_row_boundary():
    for r in LOG["rows"]:
        for dt in (-1, 0, 1):
            check_no_leak(LOG, state_at(LOG, parse_t(r["t"]) + timedelta(seconds=dt)))
