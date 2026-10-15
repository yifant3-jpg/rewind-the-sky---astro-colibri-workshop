"""Figures for the strategy studies (event-independent; the event specifics are passed in)."""
from __future__ import annotations

import healpy as hp
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from . import skymaps as sm

COLORS = {"A": "#d62728", "B": "#ff7f0e", "C": "#2ca02c", "D": "#1f77b4", "E": "#9467bd", "N": "#8c6d31",
          "F": "#e377c2", "R": "#000000"}
SITE_LOC = {"LaPalma": (28.76, -17.89, 2200), "Paranal": (-24.63, -70.40, 2635), "HESS": (-23.27, 16.50, 1800)}


def _h(t, t0):
    return (pd.Timestamp(t) - pd.Timestamp(t0)).total_seconds() / 3600


# ------------------------------------------------------------------------------------------ localisation
def localisation_evolution(log, ax=None, notes=(), label_first=3):
    """90 % credible area of the LVK-only map and of the LVK+external joint map vs time (log-log).

    Values are written next to the first `label_first` LVK-only points and next to every joint-map point;
    `notes` = [(hours, text)] draws labelled vertical lines."""
    ax = ax or plt.subplots(figsize=(10, 3.9))[1]
    t0 = log["t0"]
    series = (("gw_alert", "#d62728", "LVK-only map (the one referenced by each notice)", (0, 8), label_first),
              ("joint_skymap", "#e377c2", "LVK + Swift/BAT joint map", (10, -14), 99))
    for kind, color, label, off, nlab in series:
        rows = [r for r in log["rows"] if r["kind"] == kind]
        x = [_h(r["t"], t0) for r in rows]
        y = [r["data"]["area90"] for r in rows]
        ax.step(x, y, where="post", color=color, lw=2, label=label)
        ax.scatter(x, y, color=color, zorder=3, s=30)
        for k, (xi, yi) in enumerate(zip(x, y)):
            if k < nlab:
                ax.annotate(f"{yi:g}", (xi, yi), textcoords="offset points", xytext=off, ha="center",
                            fontsize=7.5, color=color)
    last = [r for r in log["rows"] if r["kind"] == "gw_alert"][-3:]
    ax.annotate("later LVK-only maps:\n" + " -> ".join(f'{r["data"]["area90"]:g}' for r in last) + " deg²",
                (_h(last[-1]["t"], t0), last[-1]["data"]["area90"]), textcoords="offset points",
                xytext=(-8, 26), ha="right", fontsize=7.5, color="#d62728")
    for h, txt in notes:
        ax.axvline(h, color="#777", lw=.9, ls=":")
        ax.text(h * 0.97, 56, txt, rotation=90, va="bottom", ha="right", fontsize=7.5, color="#555")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlim(5e-3, 60)
    ax.set_ylim(50, 6000)
    ax.set_xlabel("hours since the GW event (log scale)")
    ax.set_ylabel("90 % credible area (deg²)")
    ax.legend(frameon=False, fontsize=8, loc="lower left")
    ax.grid(alpha=.2, which="both")
    ax.set_title(f'{log["event"]}: how the localisation evolved', fontsize=10)
    return ax


# ------------------------------------------------------------------------------------------ visibility
def _alt_curves(site, times, targets):
    import astropy.units as u
    from astropy.coordinates import AltAz, EarthLocation, SkyCoord, get_body
    from astropy.time import Time
    from astropy.utils import iers
    iers.conf.auto_download = False
    iers.conf.iers_degraded_accuracy = "ignore"
    lat, lon, h = SITE_LOC[site]
    t = Time(pd.DatetimeIndex(times).to_pydatetime().tolist(), scale="utc")
    frame = AltAz(obstime=t, location=EarthLocation(lat=lat * u.deg, lon=lon * u.deg, height=h * u.m))
    sun = get_body("sun", t).transform_to(frame).alt.deg
    moon = get_body("moon", t).transform_to(frame).alt.deg
    alts = {k: SkyCoord(ra * u.deg, dec * u.deg).transform_to(frame).alt.deg for k, (ra, dec) in targets.items()}
    return sun, moon, alts


def night_visibility(t0, site, targets, hours=(0, 36), marks=(), ax=None, max_zenith=60):
    """Altitude of the target(s), dark time (Sun < -18 and Moon < -0.5 deg) and the Moon, vs time."""
    ax = ax or plt.subplots(figsize=(11, 3.6))[1]
    times = pd.Timestamp(t0) + pd.to_timedelta(np.linspace(hours[0], hours[1], 900), unit="h")
    hrs = np.linspace(hours[0], hours[1], 900)
    sun, moon, alts = _alt_curves(site, times, targets)
    dark = (sun < -18) & (moon < -0.5)
    night = sun < -18
    ax.fill_between(hrs, 0, 90, where=night & ~dark, color="#ffd27f", alpha=.35, lw=0,
                    label="astronomical night, Moon up")
    ax.fill_between(hrs, 0, 90, where=dark, color="#223", alpha=.14, lw=0, label="dark time (Sun < -18°, Moon < -0.5°)")
    ax.plot(hrs, moon, color="#999", lw=1, ls="--", label="Moon altitude")
    for (name, a), col in zip(alts.items(), ("#2ca02c", "#1f77b4", "#d62728")):
        ax.plot(hrs, a, color=col, lw=2, label=name)
    ax.axhline(90 - max_zenith, color="k", lw=.7, ls=":")
    ax.text(hours[0], 90 - max_zenith + 1.5, f"zenith {max_zenith}°", fontsize=7.5)
    for h, txt, col in marks:
        ax.axvline(h, color=col, lw=1.3)
        ax.text(h, 88, " " + txt, rotation=90, va="top", ha="right", fontsize=7.5, color=col)
    ax.set_ylim(-5, 90)
    ax.set_xlim(*hours)
    ax.set_xlabel("hours since the GW event")
    ax.set_ylabel(f"altitude at {site} (°)")
    ax.legend(loc="upper right", fontsize=7.5, frameon=True, framealpha=.9, ncol=2)
    return ax


def visible_probability(map_path, site, t0, hours, step_h=0.25, max_zenith=60, nside=64):
    """Fraction of the map probability above (90 - max_zenith) deg at `site`, vs time (geometry only)."""
    import astropy.units as u
    from astropy.coordinates import AltAz, EarthLocation, SkyCoord
    from astropy.time import Time
    prob, ns = sm.load_flat(map_path)
    low = hp.ud_grade(prob, nside, order_in="NESTED", order_out="NESTED", power=-2) * (hp.nside2npix(ns) / hp.nside2npix(nside))
    low = low / low.sum()
    ra, dec = hp.pix2ang(nside, np.arange(len(low)), nest=True, lonlat=True)
    sc = SkyCoord(ra * u.deg, dec * u.deg)
    lat, lon, h = SITE_LOC[site]
    loc = EarthLocation(lat=lat * u.deg, lon=lon * u.deg, height=h * u.m)
    hrs = np.arange(hours[0], hours[1], step_h)
    out = []
    for hh in hrs:
        t = Time((pd.Timestamp(t0) + pd.Timedelta(hours=float(hh))).to_pydatetime(), scale="utc")
        alt = sc.transform_to(AltAz(obstime=t, location=loc)).alt.deg
        out.append(float(low[alt > 90 - max_zenith].sum()))
    return hrs, np.array(out)


# ------------------------------------------------------------------------------------------ strategies
def coverage_vs_time(results, tag, strategies, truths, setup, t0, ax_pair=None, xlim=None, marks=(),
                     real=None, radius=None, xlims=None):
    """Coverage of each truth map vs time since the event, one panel per truth."""
    from .study import ROOT, Scorer
    radius = radius or setup.fov_radius
    fig, axes = (None, ax_pair) if ax_pair is not None else plt.subplots(1, len(truths), figsize=(6 * len(truths), 3.8),
                                                                       sharey=False)
    axes = np.atleast_1d(axes)
    for ax, (tname, tpath) in zip(axes, truths.items()):
        sc = Scorer(ROOT / tpath, radius)
        for st in strategies:
            tiles = results[(tag, st.key)]
            if not len(tiles):
                continue
            cur = sc.cumulative(tiles)
            x = np.r_[_h(st.steps[0].t, t0), [_h(t, t0) for t in cur.time]]
            y = np.r_[0, cur.coverage.values]
            ax.step(x, y, where="post", color=COLORS[st.key], lw=2, label=st.label)
            lim = (xlims or {}).get(tname, xlim)
            if lim is None or lim[0] <= x[0] <= lim[1]:       # an unclipped marker outside the axes would wreck tight_layout
                ax.plot(x[0], 0, marker="v", ms=8, color=COLORS[st.key], clip_on=False)
        for h, txt, col in marks:
            ax.axvline(h, color=col, lw=1, ls="--")
            ax.text(h, ax.get_ylim()[1] * .98, " " + txt, rotation=90, va="top", ha="right", fontsize=7, color=col)
        lim = (xlims or {}).get(tname, xlim)
        if lim:
            ax.set_xlim(*lim)
        ax.set_xlabel("hours since the GW event")
        ax.set_ylabel("probability covered")
        ax.set_title(f"truth hypothesis {tname}", fontsize=10)
        ax.grid(alpha=.2)
    return axes


def coverage_vs_tiles(results, tag, strategies, truths, setup, ax_pair=None, nmax=30, radius=None):
    """Equal-telescope-time view: coverage after the first n tiles (n x 20 min)."""
    from .study import ROOT, Scorer
    radius = radius or setup.fov_radius
    axes = np.atleast_1d(ax_pair if ax_pair is not None else plt.subplots(1, len(truths), figsize=(6 * len(truths), 3.6))[1])
    for ax, (tname, tpath) in zip(axes, truths.items()):
        sc = Scorer(ROOT / tpath, radius)
        for st in strategies:
            tiles = results[(tag, st.key)]
            if not len(tiles):
                continue
            cur = sc.cumulative(tiles)
            n = np.arange(0, min(len(cur), nmax) + 1)
            y = np.r_[0, cur.coverage.values][: len(n)]
            ax.step(n, y, where="post", color=COLORS[st.key], lw=2, label=st.key)
        ax.set_xlabel(f"tiles observed (1 tile = {setup.duration_min} min of telescope time)")
        ax.set_ylabel("probability covered")
        ax.set_title(f"equal-budget view, truth {tname}", fontsize=10)
        ax.grid(alpha=.2)
    return axes


def expected_coverage(summ, strategies, budgets, ax=None, truth_pair=("H1", "H0")):
    """E[coverage](p) = p * cov(H1) + (1 - p) * cov(H0) at several equal budgets (log p axis)."""
    ax = ax or plt.subplots(figsize=(7, 4))[1]
    p = np.logspace(-3, 0, 200)
    ls = {1: ":", 3: "-.", 6: "--", 12: "-"}
    for st in strategies:
        for n in budgets:
            c1 = summ.loc[st.key, f"cov_{truth_pair[0]}_first{n}"]
            c0 = summ.loc[st.key, f"cov_{truth_pair[1]}_first{n}"]
            ax.plot(p, p * c1 + (1 - p) * c0, color=COLORS[st.key], ls=ls.get(n, "-"), lw=1.6,
                    label=f"{st.key}, {n} tiles" if n == budgets[-1] else None)
    ax.set_xscale("log")
    ax.set_xlabel("assumed probability p that the Swift/BAT burst is the counterpart")
    ax.set_ylabel("expected probability covered")
    ax.grid(alpha=.2, which="both")
    return ax


# ------------------------------------------------------------------------------------------ tiles on sky
def _circle(ra, dec, r, n=60):
    """Points of a small circle of radius r (deg) around (ra, dec), in degrees."""
    th = np.linspace(0, 2 * np.pi, n)
    d = np.radians(dec); a = np.radians(ra); rr = np.radians(r)
    lat = np.arcsin(np.sin(d) * np.cos(rr) + np.cos(d) * np.sin(rr) * np.cos(th))
    lon = a + np.arctan2(np.sin(th) * np.sin(rr) * np.cos(d), np.cos(rr) - np.sin(d) * np.sin(lat))
    return np.degrees(lon) % 360, np.degrees(lat)


def tiles_on_sky(tiles, map_path, radius, ax=None, center_ra=180.0, color="k", levels=(0.5, 0.9), title="",
                 marks=()):
    """Mollweide map of a probability map's contours with the tile footprints over them."""
    ax = ax or plt.subplots(subplot_kw={"projection": "mollweide"}, figsize=(7, 3.8))[1]
    gj = sm.contours_geojson(map_path, levels=levels)
    for f in gj["features"]:
        col = "#d62728" if f["properties"]["credible_level"] == .9 else "#1f77b4"
        for ln in f["geometry"]["coordinates"]:
            a = np.array(ln)
            for seg in np.split(a, np.where(np.abs(np.diff(a[:, 0])) > 180)[0] + 1):
                ax.plot(-np.radians(((seg[:, 0] - center_ra + 180) % 360) - 180), np.radians(seg[:, 1]), color=col, lw=.9)
    for ra, dec in zip(tiles.ra, tiles.dec):
        lon, lat = _circle(ra, dec, radius)
        for seg in np.split(np.c_[lon, lat], np.where(np.abs(np.diff(lon)) > 180)[0] + 1):
            ax.fill(-np.radians(((seg[:, 0] - center_ra + 180) % 360) - 180), np.radians(seg[:, 1]),
                    color=color, alpha=.35, lw=.5)
    for ra, dec, lab in marks:
        ax.plot(-np.radians(((ra - center_ra + 180) % 360) - 180), np.radians(dec), marker="D", ms=6,
                color="limegreen", markeredgecolor="k", ls="none", zorder=6, label=lab)
    ax.grid(alpha=.3)
    ax.set_xticklabels([])
    ax.set_title(title, fontsize=9)
    return ax


# ------------------------------------------------------------------------------------------ sensitivity
def sensitivity_figure(frames: dict, strategies, metrics=None, fig=None):
    """Dot plot: one panel per metric, one row per setup, one dot per strategy.

    frames = {setup name: summary DataFrame (index = strategy key)}."""
    metrics = metrics or [("first_tile_h", "first tile (h after the event)"),
                          ("cov_H1_first12", "covered after 12 tiles, if BAT = counterpart (H1)"),
                          ("cov_H0_first12", "covered after 12 tiles, if unrelated (H0)")]
    names = list(frames)
    fig = fig or plt.figure(figsize=(5.2 * len(metrics), 0.55 * len(names) + 1.8))
    for j, (col, title) in enumerate(metrics):
        ax = fig.add_subplot(1, len(metrics), j + 1)
        for i, name in enumerate(names):
            for k, st in enumerate(strategies):
                v = frames[name].loc[st.key, col] if st.key in frames[name].index else np.nan
                ax.scatter(v, i + (k - (len(strategies) - 1) / 2) * 0.13, s=34, color=COLORS[st.key],
                           label=st.key if i == 0 else None, zorder=3, edgecolor="white", linewidth=.5)
        ax.set_yticks(range(len(names)))
        ax.set_yticklabels(names if j == 0 else [], fontsize=8)
        ax.invert_yaxis()
        ax.set_title(title, fontsize=9)
        ax.grid(alpha=.25)
        if j == 0:
            ax.legend(ncol=5, fontsize=7.5, loc="lower center", bbox_to_anchor=(.5, 1.12), frameon=False)
    fig.tight_layout()
    return fig


def dark_windows(t0, sites, hours=(0, 48), marks=(), ax=None, step_min=5):
    """One row per site: astronomical night (Sun < -18 deg) in light grey, dark time (also Moon < -0.5 deg) in dark."""
    ax = ax or plt.subplots(figsize=(11, 0.6 * len(sites) + 1.4))[1]
    n = int((hours[1] - hours[0]) * 60 / step_min) + 1
    hrs = np.linspace(hours[0], hours[1], n)
    times = pd.Timestamp(t0) + pd.to_timedelta(hrs, unit="h")
    tot = {}
    for i, site in enumerate(sites):
        sun, moon, _ = _alt_curves(site, times, {})
        night, dark = sun < -18, (sun < -18) & (moon < -0.5)
        for mask, col, lab in ((night, "#c9c9d6", "night, Moon up"), (dark, "#223", "dark time")):
            edges = np.flatnonzero(np.diff(np.r_[0, mask.astype(int), 0]))
            for a, b in zip(edges[::2], edges[1::2]):
                ax.barh(i, hrs[min(b, n - 1)] - hrs[a], left=hrs[a], height=.55, color=col,
                        label=lab if (i == 0 and a == edges[0]) else None)
        tot[site] = (night.sum() * step_min / 60, dark.sum() * step_min / 60)
    for h, txt, col in marks:
        ax.axvline(h, color=col, lw=1.2, ls="--")
        ax.text(h, -0.6, " " + txt, rotation=0, va="bottom", ha="left", fontsize=7.5, color=col)
    ax.set_yticks(range(len(sites)))
    ax.set_yticklabels([f"{s}\n(night {tot[s][0]:.1f} h, dark {tot[s][1]:.1f} h)" for s in sites], fontsize=8)
    ax.invert_yaxis()
    ax.set_xlim(*hours)
    ax.set_xlabel("hours since the GW event")
    ax.legend(loc="lower right", fontsize=7.5, frameon=True)
    return ax, tot
