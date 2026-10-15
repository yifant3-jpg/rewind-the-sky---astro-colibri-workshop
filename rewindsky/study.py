"""Replay observing strategies on an event with tilepy, using only information available at each decision.

A *strategy* is a sequence of decisions. Each `Step` says: "at time t, plan with this sky map (or this point
source)". When a later step arrives, tiles that have already started are kept and are passed to tilepy as
"already observed" (so they are not repeated); tiles that were only planned are discarded and re-planned.
The telescope is never double-booked: a re-plan cannot start before the last kept tile has finished.

Scoring is done against named *truth* maps (hypotheses about where the source really was). Scoring maps are used
for evaluation only, never for planning.

Everything is deterministic, cached per (event, setup, strategy, site) and runs in parallel across chains.
"""
from __future__ import annotations

import contextlib
import functools
import hashlib
import io
import json
import logging
import os
import shutil
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from pathlib import Path

import healpy as hp
import numpy as np
import pandas as pd

from . import strategies as S

ROOT = S.ROOT
OUT_DIR = ROOT / "tiling_out"
CACHE_DIR = ROOT / "data" / "strategies"

# Legacy policies with the OR semantics (Moon below 30/60 deg at any illumination, or <= 40/80 % lit). Kept so that
# old caches stay interpretable; use "moon40" / "moon80" (strategies.MOON) for new work.
S.MOON.setdefault("grey40", dict(moondown=-0.5, moongrey=30, moonphase=40, grey=True))
S.MOON.setdefault("grey80", dict(moondown=-0.5, moongrey=60, moonphase=80, grey=True))


@dataclass(frozen=True)
class Step:
    t: str                              # decision time, "YYYY-MM-DD HH:MM:SS" UTC = when the info arrived
    skymap: str | None = None           # flat HEALPix file, path relative to the project root
    gaussian: tuple | None = None       # (ra, dec, sigma_deg, nside) for a point-like target
    note: str = ""


@dataclass(frozen=True)
class Strategy:
    key: str
    label: str
    steps: tuple


@dataclass(frozen=True)
class Setup:
    sites: tuple = ("LaPalma",)
    fov_radius: float = 2.5             # circle RADIUS in degrees (= tilepy `fov`); diameter 5 deg
    delay_min: float = 0.0              # reaction time: earliest start after a decision
    moon: str = "dark"
    duration_min: int = 20
    max_nights: int = 2
    max_zenith: int = 60

    def tag(self) -> str:
        return (f"{'+'.join(self.sites)}_{self.moon}_r{self.fov_radius:g}_d{self.delay_min:g}_"
                f"n{self.max_nights}_z{self.max_zenith}_t{self.duration_min}")


def _hash(obj) -> str:
    return hashlib.sha1(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:8]


@functools.lru_cache(maxsize=None)
def _file_digest(path: str, mtime: float) -> str:
    return hashlib.sha1(Path(path).read_bytes()).hexdigest()[:12]


def _tilepy_version() -> str:
    try:
        from importlib.metadata import version
        return version("tilepy")
    except Exception:  # noqa: BLE001
        return "unknown"


def _chain_hash(strat: Strategy, setup: Setup) -> str:
    """Everything that can change a chain's tiles: the strategy, the Moon-policy VALUES, the tilepy config template,
    the site coordinates, the content of every sky map the strategy plans on, and the tilepy version."""
    maps = []
    for st in strat.steps:
        if st.skymap:
            p = ROOT / st.skymap
            maps.append(_file_digest(str(p), p.stat().st_mtime))
    return _hash([asdict(strat), S.MOON[setup.moon], S._CFG, {k: S.SITES[k] for k in setup.sites}, maps,
                  _tilepy_version()])


def _cfg_text(site: str, setup: Setup) -> str:
    lat, lon, h = S.SITES[site]
    cfg = S._CFG.format(name=site, lat=lat, lon=lon, height=h, zen=setup.max_zenith, fov=setup.fov_radius,
                        dur=setup.duration_min, **S.MOON[setup.moon])
    return cfg.replace("maxNights = 2", f"maxNights = {setup.max_nights}")


def _write_prev(tiles: pd.DataFrame, path: Path, site: str, setup: Setup) -> Path:
    """Already-observed tiles in tilepy's own output format (RA, Dec in columns 3 and 4)."""
    lines = ["Time[UTC] RA[deg] DEC[deg] PGW Round ObsName Duration FoV"]
    for _, r in tiles.iterrows():
        lines.append(f'"{r.time:%Y-%m-%d %H:%M:%S}" {r.ra:.4f} {r.dec:.4f} {r.pgw:.4f} 1 {site} '
                     f'{setup.duration_min:.1f} {setup.fov_radius:.1f}')
    path.write_text("\n".join(lines) + "\n")
    return path


def _tilepy_run(name: str, site: str, setup: Setup, obs_time: pd.Timestamp, step: Step,
                prev: pd.DataFrame) -> pd.DataFrame:
    from tilepy.include.CampaignDefinition import ObservationParameters
    from tilepy.include.ObservationScheduler import GetSchedule
    from tilepy.include.PointingTools import getdate

    work = OUT_DIR / name
    work.mkdir(parents=True, exist_ok=True)
    cfg = work / "config.ini"
    cfg.write_text(_cfg_text(site, setup))
    prev_file = _write_prev(prev, work / "prev.txt", site, setup) if len(prev) else None
    out_name = "run"
    shutil.rmtree(work / out_name, ignore_errors=True)   # never read pointings left by an earlier run
    obspar = ObservationParameters()
    mode = "healpix" if step.skymap else "gaussian"
    g = step.gaussian or (None, None, None, None)
    obspar.add_parsed_args(str(ROOT / step.skymap) if step.skymap else None,
                           getdate(obs_time.strftime("%Y-%m-%d %H:%M:%S")), None, "Gladeplus.h5",
                           str(work), str(prev_file) if prev_file else None, None, out_name, mode, *g, None)
    obspar.from_configfile(str(cfg))
    logging.disable(logging.CRITICAL)
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            GetSchedule(obspar)
    finally:
        logging.disable(logging.NOTSET)
    files = list((work / out_name).rglob("SuggestedPointings_*.txt"))
    if not files:
        return pd.DataFrame(columns=["time", "ra", "dec", "pgw", "site"])
    df = pd.read_csv(files[0], sep=r"\s+", quotechar='"')
    return pd.DataFrame({"time": pd.to_datetime(df["Time[UTC]"]), "ra": df["RA[deg]"], "dec": df["DEC[deg]"],
                         "pgw": df["PGW"], "site": site})


def run_chain(event: str, strat: Strategy, site: str, setup: Setup) -> pd.DataFrame:
    """All tiles of one strategy at one site. Cached; safe to call from a worker process."""
    os.chdir(ROOT)                                           # tilepy/skyfield look for the ephemeris here
    cache = CACHE_DIR / event / setup.tag()
    cache.mkdir(parents=True, exist_ok=True)
    f = cache / f"chain_{strat.key}-{_chain_hash(strat, setup)}_{site}.csv"
    if f.exists():
        return pd.read_csv(f, parse_dates=["time"])
    tiles = pd.DataFrame(columns=["time", "ra", "dec", "pgw", "site", "step"])
    for k, step in enumerate(strat.steps):
        t_dec = pd.Timestamp(step.t) + pd.Timedelta(minutes=setup.delay_min)
        kept = tiles[tiles.time < t_dec]                    # already started when the new information arrives
        start = t_dec
        if len(kept):
            start = max(t_dec, kept.time.max() + pd.Timedelta(minutes=setup.duration_min))
        name = f"{event}/{setup.tag()}/{strat.key}{k}_{site}"
        new = _tilepy_run(name, site, setup, start, step, kept)
        new = new[new.time >= start].assign(step=k)
        tiles = pd.concat([kept, new], ignore_index=True)
    tiles = tiles.sort_values("time").reset_index(drop=True)
    tiles.to_csv(f, index=False)
    return tiles


def run_study(event: str, strategies: list[Strategy], setups: list[Setup], workers: int = 8,
              force: bool = False) -> dict:
    """{(setup.tag(), strategy.key): tiles of all sites}. Missing chains are computed in parallel."""
    jobs = []
    for su in setups:
        for st in strategies:
            for site in su.sites:
                f = CACHE_DIR / event / su.tag() / f"chain_{st.key}-{_chain_hash(st, su)}_{site}.csv"
                if force and f.exists():
                    f.unlink()
                jobs.append((su, st, site, f.exists()))
    todo = [(su, st, site) for su, st, site, done in jobs if not done]
    if todo:
        with ProcessPoolExecutor(max_workers=min(workers, len(todo))) as ex:
            futs = {ex.submit(run_chain, event, st, site, su): (su.tag(), st.key, site) for su, st, site in todo}
            for fu in as_completed(futs):
                fu.result()                                  # re-raise any worker error
    out = {}
    for su in setups:
        for st in strategies:
            parts = [run_chain(event, st, site, su) for site in su.sites]
            out[(su.tag(), st.key)] = pd.concat(parts, ignore_index=True).sort_values("time").reset_index(drop=True)
    return out


# --------------------------------------------------------------------------------------------- scoring
class Scorer:
    """Probability of a truth map inside a union of circular fields. The map is read once."""

    def __init__(self, path: str | Path, radius: float):
        self.ring = hp.read_map(str(path), field=0, nest=False)
        self.nside = hp.get_nside(self.ring)
        self.ring = self.ring / self.ring.sum()
        self.radius = np.radians(radius)

    def pixels(self, ra: float, dec: float) -> np.ndarray:
        return hp.query_disc(self.nside, hp.ang2vec(ra, dec, lonlat=True), self.radius, nest=False)

    def coverage(self, tiles: pd.DataFrame) -> float:
        mask = np.zeros(len(self.ring), bool)
        for ra, dec in zip(tiles.ra, tiles.dec):
            mask[self.pixels(ra, dec)] = True
        return float(self.ring[mask].sum())

    def cumulative(self, tiles: pd.DataFrame) -> pd.DataFrame:
        tiles = tiles.sort_values("time").reset_index(drop=True)
        mask = np.zeros(len(self.ring), bool)
        out = []
        for _, r in tiles.iterrows():
            mask[self.pixels(r.ra, r.dec)] = True
            out.append({"time": r.time, "coverage": float(self.ring[mask].sum())})
        return pd.DataFrame(out)


def summarise(results: dict, tag: str, strategies: list[Strategy], truths: dict, setup: Setup,
              t0: str, levels=(0.1, 0.25, 0.5), budgets=(1, 3, 6, 12)) -> pd.DataFrame:
    """One row per strategy: timing and coverage under every truth hypothesis.

    `cov_<truth>_first<n>` is the coverage after the first n tiles in time order, i.e. at an EQUAL telescope-time
    budget of n x duration (12 tiles of 20 min = 4 h, the effort MAGIC+LST-1 actually spent)."""
    t0 = pd.Timestamp(t0)
    scorers = {k: Scorer(ROOT / p, setup.fov_radius) for k, p in truths.items()}
    rows = []
    for st in strategies:
        tiles = results[(tag, st.key)]
        dec = pd.Timestamp(st.steps[0].t)
        row = {"strategy": st.key, "decision_h": round((dec - t0).total_seconds() / 3600, 2),
               "n_tiles": len(tiles)}
        if len(tiles):
            first = tiles.time.min()
            row["first_tile_h"] = round((first - t0).total_seconds() / 3600, 2)
            row["wait_after_decision_h"] = round((first - dec).total_seconds() / 3600, 2)
        else:
            row["first_tile_h"] = row["wait_after_decision_h"] = np.nan
        for name, sc in scorers.items():
            cur = sc.cumulative(tiles) if len(tiles) else pd.DataFrame(columns=["time", "coverage"])
            row[f"cov_{name}"] = round(float(cur.coverage.iloc[-1]), 4) if len(cur) else 0.0
            for n in budgets:
                row[f"cov_{name}_first{n}"] = (round(float(cur.coverage.iloc[min(n, len(cur)) - 1]), 4)
                                               if len(cur) else 0.0)
            for lv in levels:
                hit = cur[cur.coverage >= lv] if len(cur) else cur
                row[f"t{int(lv * 100)}_{name}_h"] = (round(float((hit.time.iloc[0] - t0).total_seconds() / 3600), 2)
                                                     if len(hit) else np.nan)
        rows.append(row)
    return pd.DataFrame(rows).set_index("strategy")


def prune_cache(event: str, strategies: list[Strategy], setups: list[Setup]) -> int:
    """Delete cached chains that no current (strategy, setup) produces. Returns the number of files removed."""
    keep = {(su.tag(), f"chain_{st.key}-{_chain_hash(st, su)}_{site}.csv")
            for su in setups for st in strategies for site in su.sites}
    n = 0
    for f in (CACHE_DIR / event).glob("*/chain_*.csv"):
        if (f.parent.name, f.name) not in keep:
            f.unlink()
            n += 1
    for d in (CACHE_DIR / event).glob("*"):
        if d.is_dir() and not any(d.iterdir()):
            d.rmdir()
    return n
