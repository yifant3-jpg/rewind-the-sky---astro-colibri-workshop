"""Figures for the replay. Every function takes the event log (and optionally a time T)
and only draws information that was available at T (default: everything, for the
retrospective view)."""
from __future__ import annotations

from datetime import timedelta

import matplotlib.pyplot as plt
import numpy as np

from .replay import parse_t, state_at

CAT_ORDER = ["LVK alert", "joint map", "general_report", "gamma_followup", "xray_followup",
             "optical_followup", "nir_followup", "spectroscopy", "radio_followup", "neutrino_followup", "vhe_followup"]
CAT_COLOR = {"LVK alert": "#d62728", "joint map": "#e377c2", "general_report": "#7f7f7f",
             "gamma_followup": "#8c564b", "xray_followup": "#9467bd", "optical_followup": "#1f77b4",
             "nir_followup": "#17becf", "spectroscopy": "#2ca02c", "radio_followup": "#ff7f0e",
             "neutrino_followup": "#8c6d31", "vhe_followup": "#bcbd22"}
TIMELINE_KINDS = ("gw_alert", "joint_skymap", "gcn_circular")


def _hours(log, t):
    return (parse_t(t) - parse_t(log["t0"])).total_seconds() / 3600


def _cat(row):
    if row["kind"] == "gw_alert":
        return "LVK alert"
    if row["kind"] == "joint_skymap":
        return "joint map"
    c = row["data"]["category"] or "general_report"
    c = {"spectroscopic": "spectroscopy"}.get(c, c)   # the platform's LLM labels are not fully consistent
    return c if c in CAT_ORDER else "general_report"


def timeline(log, T=None, ax=None, annotate=True):
    """Each dot = one piece of information, at the time it became available (log x-axis)."""
    ax = ax or plt.subplots(figsize=(11, 4.2))[1]
    allrows = [r for r in log["rows"] if r["kind"] in TIMELINE_KINDS]
    cats = [c for c in CAT_ORDER if any(_cat(r) == c for r in allrows)]   # only rows that have data
    rows = allrows if T is None else [r for r in allrows if parse_t(r["t"]) <= parse_t(T)]
    for i, cat in enumerate(cats):
        rs = [r for r in rows if _cat(r) == cat]
        xs = [max(_hours(log, r["t"]), 1e-3) for r in rs]
        ax.scatter(xs, [i] * len(xs), s=42, color=CAT_COLOR[cat], alpha=.85,
                   edgecolor="white", linewidth=.6, zorder=3)
        if annotate and cat in ("LVK alert", "joint map"):
            lx = np.log10(xs) if xs else []
            for k, (r, x) in enumerate(zip(rs, xs)):
                lab = r["label"].replace("Preliminary", "Prelim.")
                if r["revision"] == "S250818k_3":
                    lab += " (re-saved\nwith comment)"
                crowded = any(abs(lx[k] - lx[j]) < .2 for j in range(len(xs)) if j != k)
                sgn = 1 if cat == "LVK alert" else -1          # joint-map labels go below their row
                # crowded neighbours are fanned out left / up / right with thin leader lines
                off = [(-70, 22), (0, 38), (70, 22)][k % 3] if crowded else (0, 9)
                ax.annotate(lab, (x, i), textcoords="offset points", xytext=(off[0], sgn * off[1]),
                            ha="center", va="bottom" if sgn > 0 else "top", fontsize=7.5,
                            arrowprops=dict(arrowstyle="-", color="#999", lw=.6) if crowded else None)
    ax.set_yticks(range(len(cats)))
    ax.set_yticklabels([c.replace("_", " ") for c in cats])
    ax.set_xscale("log")
    xmax = max(_hours(log, r["t"]) for r in allrows)
    ax.set_xlim(3e-3, max(1.4e3, 1.5 * xmax) if xmax > 300 else 1.5 * xmax)
    marks = [(1, "1 h"), (24, "1 day"), (168, "1 week")]
    marks = [(h, l) for h, l in marks if ax.get_xlim()[0] < h < ax.get_xlim()[1]]
    for h, _ in marks:
        ax.axvline(h, color="#bbb", lw=.8, zorder=1)
    top = ax.secondary_xaxis("top")
    top.set_xticks([h for h, _ in marks])
    top.set_xticklabels([l for _, l in marks], fontsize=8, color="#666")
    top.tick_params(length=2)
    if T is not None:
        ax.axvline(max(_hours(log, T), 1e-3), color="k", lw=1.6, ls="--", zorder=4)
    ax.set_xlabel("hours since the GW event (log scale)")
    ax.set_ylim(len(cats) - 0.5, -1.9)
    ax.set_title(f'{log["event"]}: when each piece of information became available', pad=26)
    ax.grid(axis="x", alpha=.15)
    return ax


def _split_wrap(line):
    """Split a [ra,dec] polyline where it wraps around ra=0/360."""
    a = np.array(line, float)
    breaks = np.where(np.abs(np.diff(a[:, 0])) > 180)[0] + 1
    return np.split(a, breaks)


def skymap(log, T, ax=None, center_ra=180.0, kind="alert", marks=()):
    """Mollweide map of the 50%/90% contours of the latest LVK alert (kind="alert") or LVK+external
    joint map (kind="joint") known at T. `marks` = [(ra, dec, label), ...] extra points of interest."""
    ax = ax or plt.subplots(subplot_kw={"projection": "mollweide"}, figsize=(7, 3.8))[1]
    snap = state_at(log, T)
    a = snap["latest_alert"] if kind == "alert" else snap["latest_joint"]
    row_kind = "gw_alert" if kind == "alert" else "joint_skymap"
    ax.grid(alpha=.3)
    if a is None:
        ax.set_title("nothing yet", fontsize=10)
        return ax
    row = next(r for r in log["rows"] if r["kind"] == row_kind and r["label"] == a["label"]
               and r["t"] == a["available_at"])
    for f in row["data"]["contours"]["features"]:
        lvl = f["properties"]["credible_level"]
        g = f["geometry"]
        lines = g["coordinates"] if g["type"] == "MultiLineString" else [g["coordinates"]]
        for ln in lines:
            for seg in _split_wrap(ln):
                ra = np.radians(((seg[:, 0] - center_ra + 180) % 360) - 180)
                ax.plot(-ra, np.radians(seg[:, 1]), color="#d62728" if lvl == .9 else "#1f77b4",
                        lw=1.2 if lvl == .9 else 1.0)
    pra = np.radians(((a["peak_ra"] - center_ra + 180) % 360) - 180)
    ax.plot(-pra, np.radians(a["peak_dec"]), marker="*", ms=13, color="gold",
            markeredgecolor="k", ls="none", zorder=5)
    for ra, dec, lab in marks:
        x = np.radians(((ra - center_ra + 180) % 360) - 180)
        ax.plot(-x, np.radians(dec), marker="D", ms=6, color="limegreen", markeredgecolor="k", ls="none",
                zorder=6, label=lab)
    ax.set_xticklabels([])
    ax.set_title(f'{a["label"]}  (T0+{snap["hours_since_event"]:.2f} h)\n'
                 f'90%: {a["area90_deg2"]:g} deg²   ★ = peak pixel', fontsize=9)
    return ax


def skymap_sequence(log, labels_hours, fig=None):
    fig = fig or plt.figure(figsize=(5.2 * len(labels_hours), 3.6))
    for i, h in enumerate(labels_hours):
        ax = fig.add_subplot(1, len(labels_hours), i + 1, projection="mollweide")
        skymap(log, parse_t(log["t0"]) + timedelta(hours=h), ax=ax)
    fig.suptitle("Localisation as known at each moment  (blue 50%, red 90%)", y=1.02)
    fig.tight_layout()
    return fig


def knowledge_growth(log, ax=None):
    """Cumulative number of GCN circulars by category, with LVK localisation area on top."""
    ax = ax or plt.subplots(figsize=(11, 3.8))[1]
    circ = [r for r in log["rows"] if r["kind"] == "gcn_circular" and not r["data"].get("duplicate_of")]
    xs = np.array([_hours(log, r["t"]) for r in circ])
    cats = [_cat(r) for r in circ]
    xmax = max(1.4e3 if xs.max() > 300 else 1.5 * xs.max(), 1)
    grid = np.logspace(-2, np.log10(xmax), 400)
    bottom = np.zeros_like(grid)
    for cat in CAT_ORDER[1:]:
        t = np.array([x for x, c in zip(xs, cats) if c == cat])
        if not len(t):
            continue
        cum = np.array([(t <= g).sum() for g in grid])
        ax.fill_between(grid, bottom, bottom + cum, step="post", color=CAT_COLOR[cat],
                        alpha=.8, label=cat.replace("_", " ") + f" ({len(t)})")
        bottom = bottom + cum
    ax.set_xscale("log")
    ax.set_xlim(8e-3, xmax)
    ax.set_ylabel("GCN circulars so far (duplicates removed)")
    ax.set_xlabel("hours since the GW event (log scale)")
    ax.legend(loc="upper left", fontsize=8, ncol=2, frameon=False)
    ax.set_title("How much was known: circulars accumulated over time")
    return ax


def lobe_loops(log, T, min_points=50):
    """Points of the large 90% contour loops of the latest alert known at T (one array per lobe)."""
    a = state_at(log, T)["latest_alert"]
    row = next(r for r in log["rows"] if r["kind"] == "gw_alert" and r["label"] == a["label"]
               and r["t"] == a["available_at"])
    loops = []
    for f in row["data"]["contours"]["features"]:
        if f["properties"]["credible_level"] != 0.9:
            continue
        g = f["geometry"]
        lines = g["coordinates"] if g["type"] == "MultiLineString" else [g["coordinates"]]
        loops += [np.array(l, float) for l in lines if len(l) >= min_points]
    return loops


def visibility(log, lobes, sites=None, hours=36, ax=None, loops=None):
    """Altitude of the two sky-map lobe centres at a few sites, with dark time shaded.

    Computed locally with astropy (no API requests)."""
    import astropy.units as u
    from astropy.coordinates import AltAz, EarthLocation, SkyCoord, get_body
    from astropy.time import Time
    from astropy.utils import iers
    iers.conf.auto_download = False
    iers.conf.iers_degraded_accuracy = "ignore"

    sites = sites or {"La Palma (CTAO-N/MAGIC)": (28.76, -17.89, 2200),
                      "Paranal (CTAO-S)": (-24.63, -70.40, 2635),
                      "H.E.S.S. (Namibia)": (-23.27, 16.50, 1800)}
    t0 = Time(parse_t(log["t0"]).isoformat(), scale="utc")
    times = t0 + np.linspace(0, hours, 600) * u.hour
    axes = ax if ax is not None else plt.subplots(len(sites), 1, figsize=(11, 2.3 * len(sites)),
                                                  sharex=True)[1]
    axes = np.atleast_1d(axes)
    hrs = np.linspace(0, hours, 600)
    for axi, (name, (lat, lon, h)) in zip(axes, sites.items()):
        frame = AltAz(obstime=times, location=EarthLocation(lat=lat * u.deg, lon=lon * u.deg,
                                                            height=h * u.m))
        sun = get_body("sun", times).transform_to(frame).alt.deg
        dark = sun < -18
        axi.fill_between(hrs, 0, 90, where=dark, color="#223", alpha=.12, lw=0)
        for k, (lb, col) in enumerate(zip(lobes, ("#d62728", "#1f77b4"))):
            alt = SkyCoord(lb["ra"] * u.deg, lb["dec"] * u.deg).transform_to(frame).alt.deg
            if loops is not None:
                # altitude range over the whole 90% contour of this lobe (the lobe is a long arc)
                lp = min(loops, key=lambda L: abs(((L[:, 0].mean() - lb["ra"] + 180) % 360) - 180)
                         + abs(L[:, 1].mean() - lb["dec"]))
                pts = lp[:: max(1, len(lp) // 25)]
                c = SkyCoord(pts[:, 0] * u.deg, pts[:, 1] * u.deg)[:, None]
                alts = c.transform_to(AltAz(obstime=times[None, :], location=frame.location)).alt.deg
                axi.fill_between(hrs, alts.min(0), alts.max(0), color=col, alpha=.18, lw=0)
            axi.plot(hrs, alt, color=col, lw=1.8,
                     label=f'lobe centre ({lb["ra"]:.0f}°, {lb["dec"]:+.0f}°); band = whole 90% contour')
        axi.axhline(30, color="k", lw=.7, ls=":")
        axi.set_ylim(0, 90)
        axi.set_ylabel("altitude (°)")
        axi.set_title(name, fontsize=9, loc="left")
    axes[0].legend(loc="upper right", fontsize=7.5, ncol=1, frameon=True, framealpha=.9)
    axes[-1].set_xlabel("hours since the GW event  (grey = astronomical night; dotted = zenith 60°; Moon NOT included)")
    return axes


STRAT_COLOR = {"A": "#d62728", "B": "#ff7f0e", "C": "#2ca02c"}   # same as plots_study.COLORS
STRAT_LABEL = {"A": "A  act at once (T+1 min, re-plan T+5 min)",
               "B": "B  wait for optical candidate (GCN 41414, T+15.7 h)",
               "C": "C  wait for LVK update (notice #4, T+56.6 h)"}


def strategies_figure(tiles, cur, real=None, T0=None, cur_dark=None):
    """Top: coverage of the best localisation reached vs time. Bottom: when/where tiles run."""
    import pandas as pd
    T0 = T0 or pd.Timestamp("2025-08-18 01:20:06")
    fig, (ax, ax2) = plt.subplots(2, 1, figsize=(11, 7.2), sharex=True,
                                  gridspec_kw={"height_ratios": [2.2, 1.3]})
    dec_h = {"A": 0.01, "B": 15.69, "C": 56.62}
    for k, c in cur.items():
        x = np.r_[dec_h[k], c.hours.values]
        y = np.r_[0, c.coverage.values]
        ax.step(np.maximum(x, 1e-2), y, where="post", color=STRAT_COLOR[k], lw=2, label=STRAT_LABEL[k])
        ax.plot(max(dec_h[k], 1e-2), 0, marker="v", ms=9, color=STRAT_COLOR[k], clip_on=False)
    if cur_dark:
        for k, c in cur_dark.items():
            x = np.r_[dec_h[k], c.hours.values]
            y = np.r_[0, c.coverage.values]
            ax.step(np.maximum(x, 1e-2), y, where="post", color=STRAT_COLOR[k], lw=1.2, ls="--", alpha=.7)
        ax.plot([], [], color="grey", ls="--", lw=1.2, label="dashed: strict dark-only (Moon must be below the horizon)")
    if real:
        ax.plot(real["start_h"], real["coverage"], marker="*", ms=14, color="k", ls="none",
                label="real history: ZTF started T+2.7 h, covered 25% (different instrument and map)")
    ax.set_ylabel("probability of the best (Bilby) map\ncovered by 5° tiles, 2 sites")
    ax.set_ylim(0, .85)
    ax.legend(loc="upper left", fontsize=8, frameon=False)
    ax.set_title("S250818k: three follow-up strategies, each using only what was known at its decision (▼)\n"
                 "solid: Moon allowed if below 30° (any phase) or ≤30% lit", fontsize=10)
    ax.grid(alpha=.2)
    rows = [(k, s) for k in "ABC" for s in ("LaPalma", "Paranal")]
    for i, (k, s) in enumerate(rows):
        t = tiles[k][tiles[k].site == s]
        h = (t.time - T0).dt.total_seconds() / 3600
        ax2.scatter(np.maximum(h, 1e-2), [i] * len(h), s=34, color=STRAT_COLOR[k],
                    marker="s" if s == "Paranal" else "o", alpha=.85)
    ax2.set_yticks(range(len(rows)))
    ax2.set_yticklabels([f"{k}  {s}" for k, s in rows], fontsize=8)
    ax2.invert_yaxis()
    ax2.set_xscale("log")
    ax2.set_xlim(8e-3, 150)
    ax2.set_xlabel("hours since the GW event (log scale).  Each mark = one 20-min tile.  "
                   "Gaps = daylight, Moon, or target below zenith 60°")
    ax2.grid(axis="x", alpha=.2)
    fig.tight_layout()
    return fig
