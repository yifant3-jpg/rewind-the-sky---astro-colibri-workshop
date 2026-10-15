import json
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rewindsky.replay import load_log, parse_t, state_at, t_after, check_no_leak  # noqa: E402

LOG = load_log("S250818k")


def test_nothing_before_first_alert():
    s = state_at(LOG, t_after(LOG, seconds=1))
    assert s["latest_alert"] is None and s["n_circulars"] == 0


def test_first_alert_and_sees_no_later_info():
    s = state_at(LOG, t_after(LOG, minutes=1))
    assert s["n_alerts_received"] == 1
    assert s["latest_alert"]["label"] == "Preliminary #1"
    assert s["latest_alert"]["peak_dec"] < 0      # peak pixel in the south lobe
    assert s["n_circulars"] == 0


def test_peak_pixel_jumps_but_skymap_is_the_same_two_lobes():
    a = state_at(LOG, t_after(LOG, minutes=1))["latest_alert"]
    b = state_at(LOG, t_after(LOG, minutes=10))["latest_alert"]
    assert b["label"] == "Preliminary #2"
    assert a["peak_dec"] < 0 < b["peak_dec"]      # the single best pixel flips lobes...
    for s in (a, b):                              # ...but both maps have a south and a north lobe
        assert any(l["dec"] < -30 for l in s["lobes_90"])
        assert any(l["dec"] > 30 for l in s["lobes_90"])
    assert abs(a["area90_deg2"] - b["area90_deg2"]) / a["area90_deg2"] < 0.05


def test_class_probabilities_match_lvk_circular_41437():
    a = state_at(LOG, t_after(LOG, minutes=1))["latest_alert"]
    assert abs(a["p_terrestrial"] - 0.71) < 0.005 and a["p_BNS"] == 0.29
    # FAR 2.149/yr == 6.8e-8 Hz quoted in GCN 41437
    assert abs(a["far_per_yr"] / (365.25 * 86400) - 6.8e-8) < 0.1e-8


def test_revision_3_comment_does_not_leak_before_it_existed():
    # Notice #3 was sent 2025-08-20 04:52:51, but the comment appears only in the
    # revision stored at 07:47:32. Between those times it must be absent.
    T = parse_t("2025-08-20T06:00:00")
    s = state_at(LOG, T)
    assert s["latest_alert"]["label"] == "Initial #3"
    assert s["latest_alert"]["comment"] == ""
    # ...and present once the revision exists
    s2 = state_at(LOG, parse_t("2025-08-20T08:00:00"))
    assert "ZTF25abjmnps" in s2["latest_alert"]["comment"]


def test_no_circular_before_its_date():
    for r in LOG["rows"]:
        if r["kind"] != "gcn_circular":
            continue
        T = parse_t(r["t"]) - timedelta(seconds=1)
        s = state_at(LOG, T)
        assert r["label"] not in {c["label"] for c in s["circulars"]}
        s_after = state_at(LOG, parse_t(r["t"]))
        assert r["label"] in {c["label"] for c in s_after["circulars"]}


def test_monotonic_growth():
    prev = (0, 0)
    for h in (0.01, 0.1, 1, 6, 24, 72, 200, 1100):
        s = state_at(LOG, t_after(LOG, hours=h))
        cur = (s["n_alerts_received"], s["n_circulars"])
        assert cur[0] >= prev[0] and cur[1] >= prev[1]
        prev = cur
    assert prev == (5, 50)


def test_every_row_boundary_is_leak_free():
    for r in LOG["rows"]:
        for dt in (-1, 0, 1):
            T = parse_t(r["t"]) + timedelta(seconds=dt)
            check_no_leak(LOG, state_at(LOG, T))


def test_leak_guard_actually_fires():
    s = state_at(LOG, t_after(LOG, minutes=1))
    late = next(r for r in LOG["rows"] if r["kind"] == "gcn_circular")
    s["circulars"].append({"label": late["label"], "available_at": late["t"],
                           "source": late["source"], "category": None, "subject": ""})
    s["n_circulars"] += 1
    s["circulars_by_category"]["other"] = s["circulars_by_category"].get("other", 0) + 1
    try:
        check_no_leak(LOG, s)
    except AssertionError:
        return
    raise AssertionError("leak guard did not fire")


def test_snapshot_is_json_serialisable():
    json.dumps(state_at(LOG, t_after(LOG, hours=100)))


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for f in fns:
        f()
        print("ok ", f.__name__)
    print(f"{len(fns)} passed")
