"""Case study S241125n: strategies, truth hypotheses and the real MAGIC + LST-1 history.

Decision times are the moments the information reached the public (LVK notice distribution times, NASA GCN
circular creation time), see `gweventlog` for the rules. Sky maps are the flat nside-512 files in data/skymaps.
"""
from __future__ import annotations

from .study import Setup, Step, Strategy

EVENT = "S241125n"
T0 = "2024-11-25 01:01:16"                      # GW event time (UTC), GCN 38305
SK = "data/skymaps/S241125n"
BAT = (58.079, 69.689)                          # Swift/BAT-GUANO candidate, GCN 38308 (5' at 50 %)
BAT_SIGMA_DEG = 0.07                            # 5' 50 % containment radius -> Gaussian sigma ~ 0.07 deg

N1 = Step("2024-11-25 01:01:50", f"{SK}/bayestar_1.fits.gz", note="notice #2, PyCBC, first significant alert")
N3 = Step("2024-11-25 01:06:30", f"{SK}/bayestar_2.fits.gz", note="notice #3")
N5_BILBY = Step("2024-11-25 18:03:24", f"{SK}/bilby_0.fits.gz", note="notice #5, first Bilby map")
N7_BILBY = Step("2024-11-25 21:58:12", f"{SK}/bilby_offline0_0.fits.gz", note="notice #7, offline Bilby")
N5_J0 = Step("2024-11-25 18:03:24", f"{SK}/combined_0.fits.gz", note="notice #5, joint map v0 (873 deg2)")
N6_J1 = Step("2024-11-25 20:38:34", f"{SK}/combined_1.fits.gz", note="notice #6, joint map v1 (174 deg2)")
N7_J2 = Step("2024-11-25 21:58:12", f"{SK}/combined_2.fits.gz", note="notice #7, joint map v2 (76 deg2)")
C38308 = Step("2024-11-25 18:29:14", gaussian=(BAT[0], BAT[1], BAT_SIGMA_DEG, 512), note="GCN 38308, BAT position")

STRATEGIES = [
    Strategy("A", "A  act at once, follow the LVK-only maps", (N1, N3, N5_BILBY, N7_BILBY)),
    Strategy("B", "B  wait for the LVK parameter-estimation map", (N5_BILBY, N7_BILBY)),
    Strategy("C", "C  point at the Swift/BAT candidate (what MAGIC+LST-1 did)", (C38308,)),
    Strategy("D", "D  tile the LVK+Swift joint map from its first version", (N5_J0, N6_J1, N7_J2)),
    Strategy("E", "E  hybrid: LVK-only tiling at night, switch to the BAT candidate when it appears",
             (N1, N3, C38308, N6_J1, N7_J2)),
]

# Hypotheses about where the source really is. Used for scoring only.
TRUTHS = {
    "H1": f"{SK}/combined_2.fits.gz",           # the BAT burst IS the counterpart (final LVK+Swift map)
    "H0": f"{SK}/bilby_offline0_0.fits.gz",     # no association: final LVK-only map
}

# What MAGIC + LST-1 really did (arXiv:2607.19972 Sect. 4.2, GCN 38443)
REAL = {
    "lst1_start": "2024-11-25 20:01:49", "magic_delay_min": 29, "duration_h": 4.0,
    "target": BAT, "zenith_start_deg": 55, "zenith_end_deg": 40,
    "effective_joint_min_total": 201.56, "effective_joint_min_after_quality": 19.72,
    "weather": "suboptimal: persistent clouds, LIDAR transmission at 9 km fell 0.8 -> 0.4",
    "lst1_fov_deg": 4.3, "magic_fov_deg": 3.5,
}

# Instrument/operations settings: the baseline and one-at-a-time sensitivities.
BASE = Setup(sites=("LaPalma",), fov_radius=2.5, delay_min=0, moon="dark")
SENSITIVITY = {
    "baseline": BASE,
    "delay 30 min": Setup(sites=BASE.sites, fov_radius=2.5, delay_min=30, moon="dark"),
    "delay 120 min": Setup(sites=BASE.sites, fov_radius=2.5, delay_min=120, moon="dark"),
    "FoV radius 2.15 (LST-1)": Setup(sites=BASE.sites, fov_radius=2.15, delay_min=0, moon="dark"),
    "FoV radius 1.75 (MAGIC)": Setup(sites=BASE.sites, fov_radius=1.75, delay_min=0, moon="dark"),
    "Moon up if <= 40 % lit": Setup(sites=BASE.sites, fov_radius=2.5, delay_min=0, moon="moon40"),
    "La Palma + Paranal": Setup(sites=("LaPalma", "Paranal"), fov_radius=2.5, delay_min=0, moon="dark"),
}
