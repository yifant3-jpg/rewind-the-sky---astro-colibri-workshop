# Rewind the Sky — what did we know then?

Replay the information available as a transient event unfolded, to train observers, compare follow-up
strategies and review where decisions could have been different.

Three case studies:

| | event | notebook | report |
|---|---|---|---|
| 1 | **S250818k** — low-significance LVK compact-binary candidate, 2025-08-18, later linked to AT 2025ulz | [`rewind_sky_S250818k.ipynb`](rewind_sky_S250818k.ipynb) | [`REPORT_S250818k.md`](REPORT_S250818k.md) |
| 2 | **S241125n** — BBH alert + sub-threshold Swift/BAT-GUANO candidate, 2024-11-25; compared with the real MAGIC+LST-1 observation | [`rewind_sky_S241125n.ipynb`](rewind_sky_S241125n.ipynb) | [`REPORT_S241125n.md`](REPORT_S241125n.md) |
| 3 | **S250206dm** — high-significance NSBH/BNS alert, improving localisation, 67 % Moon, IceCube and FRB candidates; no IACT history | [`rewind_sky_S250206dm.ipynb`](rewind_sky_S250206dm.ipynb) | [`REPORT_S250206dm.md`](REPORT_S250206dm.md) |

A Chinese self-study script that explains the whole project from scratch: [`TALK_NOTES_zh.md`](TALK_NOTES_zh.md).

All notebooks are already executed (figures in [`figures/<event>/`](figures/)).
Case study 2 is the research-grade one: primary sources only (LVK notices, GraceDB maps, NASA GCN circulars), cross-checked against the platform, the
circulars and the MAGIC+LST-1 paper; strategies compared at equal telescope-time budgets. All three case studies run their strategies on the
same framework (`study.py`); the event log of case study 1 is deliberately kept platform-based (it replays what Astro-COLIBRI showed).

## Quick start (offline, no API key needed)

```bash
# open rewind_sky_<event>.ipynb in VS Code (or any Jupyter front end) and pick the kernel "RewindSky (.venv)"
# (JupyterLab itself is not installed: `.venv/bin/pip install jupyterlab` if you want it)
.venv/bin/python -m pytest tests            # 45 tests: leak guard, cross-checks against primary sources, scoring consistency
```

The notebooks run entirely from cached data in `data/`. Rebuild it with
`.venv/bin/python scripts/build_notebook_<event>.py` then execute with `jupyter nbconvert --execute --inplace`.

To recreate the environment: `python -m venv .venv && .venv/bin/pip install -r requirements.txt`
(then `python -m ipykernel install --prefix .venv --name rewindsky`).

## What is where

| Path | Content |
|---|---|
| `rewindsky/gweventlog.py`, `skymaps.py` | **Case study 2**: event log from primary sources (knowledge-time rules inside) and sky-map utilities |
| `rewindsky/study.py`, `s241125n.py`, `plots_study.py` | **Case study 2**: strategy framework (multi-step re-planning, already-observed tiles, parallel, cached), the event's strategies/hypotheses/real history, research figures |
| `scripts/fetch_gw_event.py` | download the primary data of a GW event (GraceDB + NASA GCN) |
| `scripts/build_gw_event.py` | rasterise the sky maps and build the event log from the downloaded data |
| `rewindsky/s250206dm.py` | **Case study 3**: strategies (incl. IceCube and FRB candidates), hypotheses, Moon/site sensitivities |
| `rewindsky/s250818k.py` | **Case study 1** on the same framework: the three original strategies, hypotheses Hfinal/Hearly/Hcand, sensitivities |
| `scripts/run_study.py` | run a strategy study: `run_study.py all s241125n` (or `s250206dm`, `s250818k`; needs a real file because of macOS multiprocessing) |
| `rewindsky/client.py` | Astro-COLIBRI API client: on-disk cache + daily request counter (limit 100, safety margin 5). Reads `COLIBRI_UID` from the environment or `.env`; the uid is never written to disk caches |
| `rewindsky/eventlog.py` | Case study 1: builds the event log from cached Astro-COLIBRI responses (platform knowledge-time rules live here) |
| `rewindsky/replay.py` | `state_at(log, T)` and the hard leak guard `check_no_leak` |
| `rewindsky/plots.py` | Timeline, sky maps, knowledge growth, visibility, strategy figure |
| `rewindsky/strategies.py` | tilepy configuration (sites, config template, Moon policies) shared by all studies |
| `rewindsky/quiz.py` | Observer-training quiz mode |
| `data/events/S250818k.json` | The event log (55 items); the only input the replay needs |
| `data/skymaps/<event>/` | Flat nside-512 HEALPix maps from public GraceDB (plus derived point-source truth maps) |
| `data/raw/` | Raw Astro-COLIBRI responses (git-ignored) |
| `data/strategies/<event>/` | Cached tilepy chains of the strategy studies |
| `data/strategies/S250818k_v1/` | Frozen tiles of the first version of case study 1 (for the comparison in its notebook) |
| `REPORT_<event>.md` | Per-event review: what was done, what can be trusted, errors found and fixed, limitations (Chinese, plain language) |

## Method in one paragraph

Each item gets a *knowledge time*: for LVK alerts the `last_modified` of the first five Astro-COLIBRI archive
revisions (the later ones are platform re-archiving), for GCN circulars NASA's `createdOn` rounded up to the next second. `state_at(log, T)` summarises
only items with time ≤ T and then re-derives the allowed set independently and raises if anything later slips in.
Strategies decide using only information available at their decision time, are tiled with tilepy, and are then scored
against the best localisation (hindsight, evaluation only).

## Headline results

### S241125n (case study 2)

LVK's own localisation never improved (3298 → 2196 deg²); only the external Swift/BAT-GUANO coincidence shrank it (873 → 174 → 76 deg²). MAGIC+LST-1 started 25 min after the
earliest start the sky allowed, so the *decision* was not the bottleneck. Coverage after the first 12 tiles (4 h, the real effort), La Palma, FoV radius 2.5°:

| | A LVK-only, at once | B wait for LVK PE map | **C point at BAT (real)** | D tile the joint map | E hybrid |
|---|---|---|---|---|---|
| tiles needed to cover > 50 % of the joint map (H1) | never (33 tiles) | 23 | **1** | 4 | 6 |
| covered of the joint map (H1) | 1.5 % | 1.6 % | **85.1 %** | 88.2 % | 87.8 % |
| covered of the LVK-only map (H0) | 16.8 % | 18.1 % | 0.5 % | 7.1 % | 6.8 % |

Using the BAT candidate is a bet: it wins if the probability that the burst is the counterpart exceeds ~10–17 % (4 h budget). LVK itself revised the association's significance from
"one in ~10²–10³ yr" to "one in ~6 yr" three days later (GCN 38356). See `REPORT_S241125n.md` for the validation, the errors found and fixed, and the limitations.

### S250206dm (case study 3)

The Moon (67 % lit) decides everything: with dark time only, La Palma gets 2 tiles in two nights (0.5 % of the final map); with a
moonlight mode (Moon ≤ 80 % lit, sensitivity loss not modelled) acting at once covers ~50 % in 4 h and waiting for a < 1000 deg² map ~57 %;
waiting for the final map misses every usable night. The IceCube track slides from the 85 % to the 98 % credible level as the map improves;
the FRB is 32° from the Sun.

**Correction found here:** tilepy's grey time is an OR (Moon below the altitude threshold at any illumination, or above it if under the limit),
not an AND as described earlier. Numbers of the first two case studies are unchanged (checked); descriptions are fixed. See `REPORT_S250206dm.md` §6.

### S250818k (case study 1)

Two sites (La Palma, Paranal), circular field of view of 5° diameter, Moon allowed if below 30° (any illumination) or, higher up, if ≤ 30 % lit;
run on the `study.py` framework (2026-10-15; first-version numbers in brackets):

| | A act at once | B wait for optical candidate | C wait for LVK update |
|---|---|---|---|
| first tile (after event) | 0 h | 19.9 h | 67.8 h |
| probability of the best (Bilby) map covered | 67.5 % (65.6 %) | 2.8 % | 71.0 % |
| time to 10 % | 2.0 h (2.1 h) | — | 68.5 h |
| covered after the first 12 tiles (4 h of telescope time) | 14.0 % | 2.8 % | 27.0 % |
| field of AT 2025ulz first observed | T+20.5 h (without knowing it) | T+19.9 h | T+68.5 h |

B and C give the very same tiles in both frameworks; A changes by < 2 points because its re-plan now knows which field is already being observed.
Per tile C is more productive (A's first-night tiles under the Moon yield ~1 % each); betting on the optical candidate gained only 40 min, because it
lay at the 34–43 % credible level where any greedy tiling goes early. The ranking holds for all sensitivities (Moon, sites, FoV, reaction delay).
(The numbers depend on the idealisations listed below; see `REPORT_S250818k.md` for the full review, including the errors found and fixed.)

## Full review (2026-10-14)

An independent code review (a separate agent reading only the code) found no leak and no scoring error; it flagged latent risks
(stale tilepy output folders, incomplete cache keys), pixel-inflated 50 % areas of the joint maps, and circular times truncated to the
second. All were fixed, every cache was deleted and all three studies were recomputed from scratch: the 1660 summary numbers of S241125n
and S250206dm are identical to before; a regression I had introduced in S250818k (it iterated over the global site table, which had
gained H.E.S.S.) was fixed and its published numbers are reproduced exactly. Details at the end of each report.

## Known limitations

See the last section of the notebook. The most important: the data are a *lower bound* of what was known
(only Astro-COLIBRI + GCN circulars); old events have back-filled archive timestamps and cannot be replayed this way;
the strategy comparison assumes zero reaction time, no weather and a generic field of view; coverage is not a detection
probability; moonlight sensitivity loss is not modelled; with several sites each site plans independently (re-observing fields, so
multi-site numbers are lower bounds); the Moon-policy semantics were read from tilepy's source; three events only, all gravitational-wave.

## Next steps

* Export per-event JSON snapshots and build the static web viewer (slider over *T*): `state_at` output is already JSON-serialisable.
* Replace the generic field of view with a real instrument configuration (CTAO LST/MST) and its Moon limits.
