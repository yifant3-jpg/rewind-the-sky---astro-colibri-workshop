"""Case study S250818k on the `study` framework: the three strategies of the first analysis, unchanged in their
definitions, re-run with already-observed tiles passed to tilepy, several truth hypotheses and equal-budget
metrics, so that the three case studies are scored the same way.

The EVENT LOG of this case stays platform-based (`eventlog.py`, Astro-COLIBRI archive revisions): it is the one case
that replays "what the platform showed". Decision times are therefore the knowledge times of that log (platform
`last_modified` for LVK, NASA `createdOn` rounded up for circulars), exactly as in the first analysis.
Sky maps are the flat nside-512 GraceDB files in data/skymaps/S250818k.

The tiles of the first analysis (its re-plan did not pass already-observed tiles to tilepy) are frozen in
data/strategies/S250818k_v1/<moon>/tiles_<strategy>.csv for comparison; the code that made them was removed.
"""
from __future__ import annotations

from pathlib import Path

from .study import ROOT, Setup, Step, Strategy

EVENT = "S250818k"
T0 = "2025-08-18 01:20:06"                      # GW event time (UTC)
SK = "data/skymaps/S250818k"
CAND = (237.9757129, 30.9023146)                # AT2025ulz / ZTF25abjmnps, GCN 41414
CAND_TRUTH = f"{SK}/AT2025ulz_point.fits.gz"
V1 = ROOT / "data" / "strategies" / "S250818k_v1"

A0 = Step("2025-08-18 01:20:43", f"{SK}/bayestar_0.fits.gz", note="Preliminary #1 (platform revision _0)")
A1 = Step("2025-08-18 01:25:20", f"{SK}/bayestar_1.fits.gz", note="Preliminary #2 (platform revision _1)")
B0 = Step("2025-08-18 17:01:31", gaussian=(CAND[0], CAND[1], 0.1, 128), note="GCN 41414, ZTF candidate AT2025ulz")
C0 = Step("2025-08-20 09:57:17", f"{SK}/bilby_0.fits.gz", note="Update #4 (platform revision _4), Bilby map")

STRATEGIES = [
    Strategy("A", "A  act at once, re-plan on the 2nd map", (A0, A1)),
    Strategy("B", "B  wait for the optical candidate (T+15.7 h)", (B0,)),
    Strategy("C", "C  wait for the LVK update (T+56.6 h)", (C0,)),
]

# Hypotheses used for scoring only.
TRUTHS = {
    "Hfinal": f"{SK}/bilby_0.fits.gz",          # best LVK map (the only truth of the first analysis)
    "Hearly": f"{SK}/bayestar_1.fits.gz",       # the map known at T+5 min (how much the map moved)
    "Hcand": CAND_TRUTH,                        # AT2025ulz IS the counterpart (point source)
}

REAL_ZTF = {"start_h": 2.7, "coverage": 0.252, "note": "ZTF, 47 deg2 FoV, from GCN 41414"}

# The first analysis: La Palma + Paranal, grey time (Moon below 30 deg at any phase, or higher if <= 30 % lit).
SITES2 = ("LaPalma", "Paranal")
BASE = Setup(sites=SITES2, fov_radius=2.5, delay_min=0, moon="grey")
SENSITIVITY = {
    "baseline (2 sites, grey)": BASE,
    "dark time": Setup(sites=SITES2, moon="dark"),
    "Moon up if <= 40 % lit": Setup(sites=SITES2, moon="moon40"),
    "La Palma only": Setup(sites=("LaPalma",), moon="grey"),
    "FoV radius 2.15 (LST-1)": Setup(sites=SITES2, fov_radius=2.15, moon="grey"),
    "delay 30 min": Setup(sites=SITES2, delay_min=30, moon="grey"),
    "delay 120 min": Setup(sites=SITES2, delay_min=120, moon="grey"),
}


def first_version_tiles(moon: str) -> dict:
    """Tiles of the first analysis ("grey" or "dark"), {strategy: DataFrame}."""
    import pandas as pd
    return {k: pd.read_csv(V1 / moon / f"tiles_{k}.csv", parse_dates=["time"]) for k in "ABC"}


def ensure_candidate_truth(sigma_deg: float = 0.05) -> Path:
    """Point-like truth map at AT2025ulz (Gaussian, sigma well below one tile), flat NESTED nside 512."""
    import healpy as hp
    import numpy as np

    from . import skymaps as sm
    out = ROOT / CAND_TRUTH
    if out.exists():
        return out
    pix = np.arange(hp.nside2npix(sm.NSIDE))
    vec = np.array(hp.pix2vec(sm.NSIDE, pix, nest=True))
    d = np.arccos(np.clip(vec.T @ hp.ang2vec(*CAND, lonlat=True), -1, 1))
    p = np.exp(-0.5 * (d / np.radians(sigma_deg)) ** 2)
    return sm.write_flat(p / p.sum(), out)
