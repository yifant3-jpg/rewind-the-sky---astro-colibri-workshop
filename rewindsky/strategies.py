"""tilepy configuration shared by all strategy studies (`study.py`): sites, the config template and the Moon policies."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SITES = {  # name: (lat, lon, height m)
    "LaPalma": (28.76, -17.89, 2200),
    "Paranal": (-24.63, -70.40, 2635),
    "HESS": (-23.27, 16.50, 1800),               # H.E.S.S., Namibia
}
# NB: tilepy's `fov` option is the circle RADIUS (verified: its own reported probability equals the map probability
# inside circles of radius `fov`). `study.Setup.fov_radius` is passed as is.

_CFG = """[observatory]
name = {name}
lat = {lat}
lon = {lon}
height = {height}

[visibility]
sundown = -18
moondown = {moondown}
earthdown = 0
moongrey = {moongrey}
moonphase = {moonphase}
minmoonsourceseparation = 30
maxmoonsourceseparation = 0
SAAThreshold = 0

[operations]
maxzenith = {zen}
fov = {fov}
maxRuns = 20
maxNights = 2
duration = {dur}
minduration = 10
useGreytime = {grey}
minSlewing = 0
shape = circle
numberSides = 0
FoVRotation = 0

[tiling]
locCut = 100000
minimumprobcutforcatalogue = 0.01
minProbcut = 0.005
distcut = 400
doPlot = False
secondRound = False
zenithWeighting = 0
percentageMOC = 0.9
reducedNside = 256
hrnside = 512
mangrove = False
algorithm = 2D
strategy = integrated
doRank = False
countPrevious = False
countSubtractedPointingsOutside = False
alphaR = 0
betaR = 0

[general]
downloadMaxRetry = 3
downloadWaitPeriodRetry = 5
"""


# Moon policies. tilepy's grey-time semantics (read in PointingTools.get_time_window and confirmed on S250206dm,
# where the first "grey" tile starts exactly when the 67 %-lit Moon sinks below 30 deg):
#   an interval is allowed if the Moon is BELOW `moongrey` (at ANY illumination), OR if it is above `moongrey`
#   and its illumination is below `moonphase`.  It is an OR, not an AND.
#   dark   : Moon below -0.5 deg (tilepy's convention for IACTs).
#   grey   : Moon below 30 deg at any illumination, or higher if <= 30 % lit (used for S250818k).
#   moon40 : Moon down, or up at any altitude if <= 40 % lit (close to the H.E.S.S. rule, which also
#            requires 45-145 deg Moon separation; tilepy only masks 30 deg around the Moon).
#   moon80 : Moon up if <= 80 % lit ("moonlight mode", reduced HV / UV filters; the 60-80 % sensitivity loss of
#            such modes is NOT modelled).
#   none   : Moon ignored entirely (upper bound; also drops the 30 deg separation, so not realistic).
# NB: moongrey=90 silently disables the whole Moon constraint, never use it as "any altitude".
MOON = {
    "dark": dict(moondown=-0.5, moongrey=0, moonphase=0, grey=False),
    "grey": dict(moondown=-0.5, moongrey=30, moonphase=30, grey=True),
    "moon40": dict(moondown=-0.5, moongrey=0, moonphase=40, grey=True),     # tilepy reads moongrey as int
    "moon80": dict(moondown=-0.5, moongrey=0, moonphase=80, grey=True),
    "none": dict(moondown=90, moongrey=0, moonphase=0, grey=False),
}
