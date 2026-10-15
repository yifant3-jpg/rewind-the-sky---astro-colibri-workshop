"""Tests for the S241125n event log and study. They cross-check our numbers against independent primary sources:
LVK circulars (text), the Astro-COLIBRI platform records, the GraceDB log and the MAGIC+LST-1 paper."""
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from rewindsky.replay import check_no_leak, load_log, parse_t, state_at, t_after  # noqa: E402

LOG_PATH = ROOT / "data" / "events" / "S241125n.json"
pytestmark = pytest.mark.skipif(not LOG_PATH.exists(), reason="S241125n log not built")
LOG = load_log("S241125n") if LOG_PATH.exists() else None


def rows(kind):
    return [r for r in LOG["rows"] if r["kind"] == kind]


def test_structure():
    assert (len(rows("gw_alert")), len(rows("joint_skymap")), len(rows("gcn_circular"))) == (7, 3, 26)
    assert all(r["data"]["contours"]["features"] for r in rows("gw_alert") + rows("joint_skymap"))


def test_first_alert_is_low_significance_then_significant():
    s1 = state_at(LOG, t_after(LOG, seconds=30))["latest_alert"]
    assert s1["label"] == "Preliminary #1" and s1["significant"] is False
    assert abs(s1["p_terrestrial"] - 0.566) < 0.002 and abs(s1["p_BBH"] - 0.434) < 0.002
    s2 = state_at(LOG, t_after(LOG, seconds=45))["latest_alert"]
    assert s2["label"] == "Preliminary #2" and s2["significant"] is True and s2["p_BBH"] > 0.999


def test_notice_times_match_gracedb_log():
    gl = json.loads((ROOT / "data/gracedb/S241125n/logs.json").read_text())["log"]
    created = {l["filename"]: l["created"] for l in gl if (l.get("filename") or "").endswith(".xml")}
    for r in rows("gw_alert"):
        n = int(r["label"].split("#")[1])
        fn = next(f for f in created if f.startswith(f"S241125n-{n}-"))
        t = datetime.strptime(created[fn], "%Y-%m-%d %H:%M:%S UTC")
        assert abs((parse_t(r["t"]) - t).total_seconds()) <= 5, (fn, r["t"], created[fn])


def test_platform_lags_the_notice_by_seconds():
    for r in rows("gw_alert"):
        lag = (parse_t(r["platform_time"]) - parse_t(r["t"])).total_seconds()
        assert 5 <= lag <= 30, (r["label"], lag)


def test_areas_match_the_platform_records():
    for r in rows("gw_alert"):
        raw = json.loads((ROOT / f"data/raw/event__gw_S241125n_{r['revision'].split('_')[1]}.json").read_text())["body"]
        a = json.loads(raw["map_areas"])
        assert abs(r["data"]["area90"] - a["90"]) < 1.5, (r["label"], r["data"]["area90"], a)


def test_areas_match_the_numbers_quoted_in_lvk_circulars():
    """Primary text (GCN circulars) vs primary data (GraceDB FITS)."""
    def quoted(n):
        body = json.loads((ROOT / f"data/gcn/S241125n/{n}.json").read_text())["body"]
        return [float(x) for x in re.findall(r"credible region is ([\d.]+) deg2", body)]
    by_label = {r["label"]: r["data"]["area90"] for r in rows("joint_skymap") + rows("gw_alert")}
    assert quoted(38309) == [1957.0, 873.0] and quoted(38312) == [174.0] and quoted(38313) == [2196.0]
    assert quoted(38315) == [76.0]
    assert abs(by_label["Update #5"] - 1957) < 1 and abs(by_label["Joint map v0"] - 873) < 1
    assert abs(by_label["Joint map v1"] - 174) < 1 and abs(by_label["Update #7"] - 2196) < 1
    assert abs(by_label["Joint map v2"] - 76) < 1                       # also the 76 deg2 of arXiv:2607.19972


def test_joint_map_arrives_with_notice_5_not_earlier():
    before = state_at(LOG, parse_t("2024-11-25T18:03:23"))
    after = state_at(LOG, parse_t("2024-11-25T18:03:24"))
    assert before["latest_joint"] is None and after["latest_joint"]["label"] == "Joint map v0"
    assert after["latest_joint"]["time_difference_s"] == 0.25
    assert after["latest_alert"]["skymap"] == "bilby_0"     # the main map of notice #5 is LVK-only


def test_circular_times_come_from_nasa_created_on():
    c = {r["data"]["number"]: r for r in rows("gcn_circular")}
    assert c[38308]["t"] == "2024-11-25T18:29:14" and c[38443]["t"] == "2024-12-05T15:33:49"   # createdOn, rounded up
    assert c[38305]["t"] == "2024-11-25T04:30:37"


def test_tricky_circular_sources():
    """Titles that mention another instrument must be attributed to the author's instrument."""
    c = {r["data"]["number"]: r["source"] for r in rows("gcn_circular")}
    assert c[38311] == "INTEGRAL" and c[38308] == "Swift/BAT-GUANO" and c[38351] == "Swift/BAT-GUANO"
    assert c[38314] == "Kinder" and c[38334] == "COLIBRI" and c[38443] == "LST-1+MAGIC"
    assert c[38356] == "LVK" and c[38350] == "Swift/UVOT" and c[38324] == "Swift/XRT"


def test_duplicate_circulars_are_flagged():
    c = {r["data"]["number"]: r["data"] for r in rows("gcn_circular")}
    assert c[38346]["duplicate_of"] == 38345 and c[38347]["duplicate_of"] == 38345
    assert state_at(LOG, t_after(LOG, hours=300))["n_circulars_unique"] == 24


def test_graceDB_early_maps_are_not_shown_before_their_notice():
    """Bilby map exists on GraceDB from 07:06 but is only distributed with notice #5 at 18:03."""
    snap = state_at(LOG, parse_t("2024-11-25T12:00:00"))
    assert snap["latest_alert"]["label"] == "Initial #4" and snap["latest_alert"]["skymap"] == "bayestar_2"
    g = [r for r in rows("gracedb_map") if r["label"].startswith("Bilby,0")]
    assert g and g[0]["t"] == "2024-11-25T07:06:27"


def test_nothing_leaks_at_any_row_boundary():
    for r in LOG["rows"]:
        for dt in (-1, 0, 1):
            check_no_leak(LOG, state_at(LOG, parse_t(r["t"]) + timedelta(seconds=dt)))


def test_snapshot_serialisable():
    json.dumps(state_at(LOG, t_after(LOG, hours=100)))


# ---------------------------------------------------------------------------------------- study (cache)
STUDY = ROOT / "data" / "strategies" / "S241125n"


@pytest.mark.skipif(not STUDY.exists(), reason="study cache not built")
def test_no_double_booking_and_constraints_in_study():
    import pandas as pd
    from rewindsky import s241125n as E, study
    res = study.run_study(E.EVENT, E.STRATEGIES, [E.BASE], workers=1)
    for st in E.STRATEGIES:
        df = res[(E.BASE.tag(), st.key)]
        gaps = df.sort_values("time").time.diff().dropna().dt.total_seconds() / 60
        assert (gaps >= E.BASE.duration_min - 0.1).all(), (st.key, gaps.min())


@pytest.mark.skipif(not STUDY.exists(), reason="study cache not built")
def test_bat_tile_covers_what_the_joint_map_says():
    """Strategy C points at BAT: its coverage of the joint map must equal the map probability in that disc."""
    from rewindsky import s241125n as E, study, skymaps as sm
    res = study.run_study(E.EVENT, [s for s in E.STRATEGIES if s.key == "C"], [E.BASE], workers=1)
    tiles = res[(E.BASE.tag(), "C")]
    cov = study.Scorer(ROOT / E.TRUTHS["H1"], E.BASE.fov_radius).coverage(tiles)
    p, ns = sm.load_flat(ROOT / E.TRUTHS["H1"])
    assert abs(cov - sm.prob_in_disc(p, ns, E.BAT[0], E.BAT[1], E.BASE.fov_radius)) < 0.01   # tile centre <~0.3 deg off


@pytest.mark.skipif(not STUDY.exists(), reason="study cache not built")
def test_replay_reproduces_the_real_start_within_half_an_hour():
    """MAGIC+LST-1 started at 20:01:49 (paper). Our earliest dark-time start must be earlier, by < 30 min."""
    import pandas as pd
    from rewindsky import s241125n as E, study
    res = study.run_study(E.EVENT, [s for s in E.STRATEGIES if s.key == "C"], [E.BASE], workers=1)
    first = res[(E.BASE.tag(), "C")].time.min()
    real = pd.Timestamp(E.REAL["lst1_start"])
    assert pd.Timedelta(0) < real - first < pd.Timedelta(minutes=30), (first, real)


def test_timezone_aware_times_are_accepted():
    a = state_at(LOG, "2024-11-25T18:03:24Z")
    b = state_at(LOG, "2024-11-25T19:03:24+01:00")
    assert a["latest_joint"]["label"] == b["latest_joint"]["label"] == "Joint map v0"


def test_leak_guard_covers_latest_alert():
    s = state_at(LOG, t_after(LOG, seconds=30))
    late = [r for r in LOG["rows"] if r["kind"] == "gw_alert"][-1]
    s["latest_alert"] = dict(s["latest_alert"], label=late["label"], available_at=late["t"])
    with pytest.raises(AssertionError):
        check_no_leak(LOG, s)


def test_joint_map_50pct_area_is_below_map_resolution():
    """LVK: '50% credible region is less than 1 deg2'; our crossmatch value must not be inflated by pixelisation."""
    j = [r for r in rows("joint_skymap")]
    assert j[1]["data"]["area50"] < 0.01 and j[2]["data"]["area50"] < 0.01
