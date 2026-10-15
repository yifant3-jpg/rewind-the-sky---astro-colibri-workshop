"""S250818k on the `study` framework: equivalence with the first analysis (frozen tiles) where the two must agree,
and the properties the new framework adds (no double booking, no repeated fields, scoring consistency)."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from rewindsky import s250818k as E, study  # noqa: E402

DARK = E.SENSITIVITY["dark time"]


def _cached(setup):
    return all((study.CACHE_DIR / E.EVENT / setup.tag() /
                f"chain_{st.key}-{study._chain_hash(st, setup)}_{site}.csv").exists()
               for st in E.STRATEGIES for site in setup.sites)


pytestmark = pytest.mark.skipif(not (_cached(E.BASE) and _cached(DARK) and E.V1.exists()),
                                reason="S250818k study or legacy cache not built")
RES = study.run_study(E.EVENT, E.STRATEGIES, [E.BASE, DARK]) if pytestmark.args[0] is False else {}


def _key(df):
    return df.sort_values(["site", "time"])[["site", "time", "ra", "dec"]].round({"ra": 4, "dec": 4}).reset_index(drop=True)


@pytest.mark.parametrize("moon,setup", [("grey", E.BASE), ("dark", DARK)])
def test_single_step_strategies_reproduce_the_first_analysis(moon, setup):
    """B and C have one decision each, so the two frameworks must give the very same tiles."""
    old = E.first_version_tiles(moon)
    for k in "BC":
        pd.testing.assert_frame_equal(_key(old[k]), _key(RES[(setup.tag(), k)]), check_dtype=False)


@pytest.mark.parametrize("setup", [E.BASE, DARK])
def test_no_double_booking_and_no_repeated_field(setup):
    for st in E.STRATEGIES:
        for site, g in RES[(setup.tag(), st.key)].groupby("site"):
            g = g.sort_values("time")
            gaps = g.time.diff().dropna().dt.total_seconds() / 60
            assert (gaps >= setup.duration_min - 0.1).all(), (st.key, site, gaps.min())
            radec = g[["ra", "dec"]].round(3).apply(tuple, axis=1)
            assert radec.is_unique, (st.key, site)


def test_replan_keeps_the_started_tile_and_tells_tilepy():
    """A: the first-map tile that is running at the re-plan is kept, and the re-planned fields avoid it (in the
    first analysis tilepy was not told, so its re-plan could point at the same field again)."""
    a = RES[(E.BASE.tag(), "A")]
    for site, g in a.groupby("site"):
        kept = g[g.step == 0]
        assert len(kept) == 1 and kept.time.iloc[0] == pd.Timestamp(E.A0.t)
        later = g[g.step == 1]
        assert later.time.min() >= kept.time.iloc[0] + pd.Timedelta(minutes=E.BASE.duration_min)
        d = np.hypot((later.ra - kept.ra.iloc[0]) * np.cos(np.radians(kept.dec.iloc[0])), later.dec - kept.dec.iloc[0])
        assert d.min() > E.BASE.fov_radius, (site, d.min())


def test_scoring_matches_tilepy_on_its_own_planning_map():
    """C plans on the Bilby map, which is also the Hfinal truth: tilepy's summed probability = our coverage."""
    sc = study.Scorer(ROOT / E.TRUTHS["Hfinal"], E.BASE.fov_radius)
    for site, g in RES[(E.BASE.tag(), "C")].groupby("site"):
        assert abs(sc.coverage(g) - g.pgw.sum()) < 0.01, site


def test_candidate_truth_map_is_a_point_at_AT2025ulz():
    import healpy as hp
    from rewindsky import skymaps as sm
    p, ns = sm.load_flat(E.ensure_candidate_truth())
    assert abs(p.sum() - 1) < 1e-9
    assert p.argmax() == hp.ang2pix(ns, *E.CAND, nest=True, lonlat=True)
    sc = study.Scorer(ROOT / E.TRUTHS["Hcand"], E.BASE.fov_radius)
    ra, dec = E.CAND
    assert sc.coverage(pd.DataFrame({"ra": [ra + 1.0], "dec": [dec]})) > 0.999
    assert sc.coverage(pd.DataFrame({"ra": [ra + 4.0], "dec": [dec]})) < 1e-6


def test_headline_numbers():
    s = study.summarise(RES, E.BASE.tag(), E.STRATEGIES, E.TRUTHS, E.BASE, E.T0)
    assert abs(s.loc["A", "cov_Hfinal"] - 0.6752) < 1e-3 and abs(s.loc["C", "cov_Hfinal"] - 0.7098) < 1e-3
    assert abs(s.loc["B", "cov_Hfinal"] - 0.0279) < 1e-3
    assert abs(s.loc["A", "t10_Hfinal_h"] - 2.01) < 0.02
    # A reaches the ZTF candidate's field 40 min after B, without knowing about it
    assert abs(s.loc["A", "t10_Hcand_h"] - 20.52) < 0.02 and abs(s.loc["B", "t10_Hcand_h"] - 19.86) < 0.02
