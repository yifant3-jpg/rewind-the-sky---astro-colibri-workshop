"""Case study S250206dm: a high-significance NSBH/BNS alert with an improving localisation, two
low-prior counterpart candidates (an IceCube track and an FRB) and a bright Moon (67 % lit).

No IACT follow-up was reported for this event (none of the 62 circulars mentions MAGIC, LST, H.E.S.S., VERITAS,
CTAO), so there is no real history to compare with. The study asks how the Moon and the improving localisation
shape what an IACT could have done.
"""
from __future__ import annotations

from .study import Setup, Step, Strategy

EVENT = "S250206dm"
T0 = "2025-02-06 21:25:30"                      # GW event time (UTC), GCN 39175
SK = "data/skymaps/S250206dm"
ICECUBE = (149.16, -17.94)                      # IceCube track 1, 90 % radius 0.43 deg, p = 0.008 (GCN 39176)
ICECUBE_SIGMA_DEG = 0.2                         # 90 % radius 0.43 deg -> Gaussian sigma ~ 0.2 deg
FRB = (338.703, 12.1699)                        # CHIME/FRB 20250206A, +-0.4 arcmin (GCN 39216)
FRB_SIGMA_DEG = 0.05

N2 = Step("2025-02-06 21:30:52", f"{SK}/bayestar_1.fits.gz", note="notice #2: first alert with a low terrestrial probability")
N4 = Step("2025-02-06 23:39:39", f"{SK}/bilby_0.fits.gz", note="notice #4: first Bilby (parameter-estimation) map, 1626 deg2")
N6 = Step("2025-02-07 02:46:08", f"{SK}/bilby_1.fits.gz", note="notice #6: 910 deg2")
N7 = Step("2025-02-08 11:06:27", f"{SK}/bilby_offline1_0.fits.gz", note="notice #7: final map, 547 deg2")
ICE = Step("2025-02-06 22:36:53", gaussian=(ICECUBE[0], ICECUBE[1], ICECUBE_SIGMA_DEG, 512), note="GCN 39176, IceCube track 1")
FRBSTEP = Step("2025-02-07 21:26:32", gaussian=(FRB[0], FRB[1], FRB_SIGMA_DEG, 512), note="GCN 39216, CHIME/FRB position")

STRATEGIES = [
    Strategy("A", "A  act at once, follow the LVK maps", (N2, N4, N6, N7)),
    Strategy("B", "B  wait for the first Bilby map", (N4, N6, N7)),
    Strategy("C", "C  wait until the area is < 1000 deg2", (N6, N7)),
    Strategy("D", "D  wait for the final map", (N7,)),
    Strategy("N", "N  point at the IceCube track (T+1.2 h)", (ICE,)),
    Strategy("F", "F  point at the FRB position (T+24 h)", (FRBSTEP,)),
]

# Hypotheses used for scoring only. The truth is unknown; the final map is the best estimate.
TRUTHS = {
    "Hfinal": f"{SK}/bilby_offline1_0.fits.gz",   # final LVK map (T+37.7 h)
    "Hearly": f"{SK}/bayestar_1.fits.gz",         # the map known at T+5 min (how much the map moved)
}

CANDIDATES = {
    "IceCube track 1": ICECUBE, "IceCube track 2": (354.59, 32.79), "FRB 20250206A": FRB,
}

LP = ("LaPalma",)
ALL3 = ("LaPalma", "HESS", "Paranal")
BASE = Setup(sites=LP, fov_radius=2.5, delay_min=0, moon="dark")
SENSITIVITY = {
    "baseline (La Palma, dark time)": BASE,
    "Moon up if <= 40 % lit (H.E.S.S.-like)": Setup(sites=LP, moon="moon40"),
    "moonlight mode (Moon <= 80 % lit)": Setup(sites=LP, moon="moon80"),
    "3 sites, dark time": Setup(sites=ALL3, moon="dark"),
    "3 sites, moonlight mode": Setup(sites=ALL3, moon="moon80"),
    "FoV radius 2.15 (LST-1)": Setup(sites=LP, fov_radius=2.15, moon="dark"),
    "delay 30 min": Setup(sites=LP, delay_min=30, moon="dark"),
    "delay 120 min": Setup(sites=LP, delay_min=120, moon="dark"),
}
