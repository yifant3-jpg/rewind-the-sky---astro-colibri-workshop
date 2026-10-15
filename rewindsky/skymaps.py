"""Sky-map helpers: one flat, NESTED, nside=512 file per map, shared by the scheduler and the scorer.

LVK maps come as multi-order (UNIQ) or flat FITS; the combined LVK+external maps are multi-order with
arc-minute pixels. Everything is rasterised once to `NSIDE` so that tilepy (which plans on the file) and
`covered_probability` (which scores on the file) look at exactly the same numbers. Probability is conserved by
the rasterisation, so tile-scale quantities (>> 0.1 deg) are unaffected; credible areas come from LVK's
`crossmatch` on the original multi-order map (`credible_area`), so arc-minute regions are not inflated.
"""
from __future__ import annotations

import warnings
from pathlib import Path

import healpy as hp
import numpy as np

NSIDE = 512


def read_prob(path: str | Path, nside: int = NSIDE) -> np.ndarray:
    """Probability per pixel (NESTED, sums to 1) at `nside`, from a flat or multi-order LVK FITS file."""
    from ligo.skymap import moc
    from ligo.skymap.io import read_sky_map

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        t = read_sky_map(str(path), moc=True)
        dens = moc.rasterize(t, order=int(np.log2(nside)))["PROBDENSITY"]
    p = np.asarray(dens, dtype=float) * hp.nside2pixarea(nside)
    return p / p.sum()


def write_flat(prob: np.ndarray, out: str | Path, nside: int = NSIDE) -> Path:
    """Write a flat NESTED map that tilepy's reader (column PROB) and healpy can both read."""
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    hp.write_map(str(out), prob, nest=True, column_names=["PROB"], column_units=["pix-1"],
                 coord="C", overwrite=True, dtype=np.float64)
    return out


def ensure_flat(src: str | Path, out: str | Path, nside: int = NSIDE) -> Path:
    """Convert `src` to a flat map at `out` unless it already exists."""
    out = Path(out)
    if not out.exists():
        write_flat(read_prob(src, nside), out, nside)
    return out


def load_flat(path: str | Path) -> tuple[np.ndarray, int]:
    """Flat file written by `write_flat` (or any flat HEALPix) as a NESTED probability array."""
    m = hp.read_map(str(path), field=0, nest=True)
    return np.asarray(m, dtype=float) / m.sum(), hp.get_nside(m)


def credible_area(src: str | Path, level: float, nside: int | None = None) -> float:
    """Area (deg2) of the `level` credible region, computed by LVK's own tool (`ligo.skymap.postprocess.crossmatch`)
    on the original multi-order map, i.e. at native resolution with interpolation inside the last pixel.

    When the region is smaller than one pixel of the map (the LVK+Swift joint maps at 50 %), the value is below the
    map's resolution and should be quoted as an upper limit. `nside` is ignored (backward compatibility)."""
    from ligo.skymap.io import read_sky_map
    from ligo.skymap.postprocess import crossmatch

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        t = read_sky_map(str(src), moc=True)
        return float(crossmatch(t, contours=(level,)).contour_areas[0])


def peak(prob: np.ndarray, nside: int) -> tuple[float, float]:
    ra, dec = hp.pix2ang(nside, int(np.argmax(prob)), nest=True, lonlat=True)
    return float(ra), float(dec)


def prob_in_disc(prob: np.ndarray, nside: int, ra: float, dec: float, radius_deg: float) -> float:
    pix = hp.query_disc(nside, hp.ang2vec(ra, dec, lonlat=True), np.radians(radius_deg), nest=True)
    return float(prob[pix].sum())


def contours_geojson(src: str | Path, levels=(0.5, 0.9), nside: int = 256) -> dict:
    """50 % / 90 % credible contours as a GeoJSON FeatureCollection of MultiLineStrings in [ra, dec] degrees.

    Same structure as the contours that the Astro-COLIBRI API returns (so the plotting code is shared)."""
    from ligo.skymap.postprocess import contour, find_greedy_credible_levels

    p = read_prob(src, nside)
    ring = hp.reorder(p, n2r=True)
    cls = 100 * find_greedy_credible_levels(ring)          # credible level (%) of every pixel
    paths = contour(cls, [100 * l for l in levels], nest=False, degrees=True, simplify=False)
    feats = []
    for lvl, lines in zip(levels, paths):
        coords = [[[float(ra), float(dec)] for ra, dec in line] for line in lines]
        feats.append({"type": "Feature", "properties": {"credible_level": lvl},
                      "geometry": {"type": "MultiLineString", "coordinates": coords}})
    return {"type": "FeatureCollection", "features": feats}
