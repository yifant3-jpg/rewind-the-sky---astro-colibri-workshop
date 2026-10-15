"""From the downloaded primary data to the event log:  fetch -> flat maps -> log.

    .venv/bin/python -I scripts/fetch_gw_event.py S250206dm
    .venv/bin/python -I scripts/build_gw_event.py S250206dm 2025-02-06T21:25:30 7

Needs data/gracedb/<event>/ and data/gcn/<event>/ (from fetch_gw_event.py); data/raw/event__gw_<event>_<i>.json
(Astro-COLIBRI revisions, optional) is used for the platform cross-check only.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from rewindsky import gweventlog, skymaps as sm  # noqa: E402


def main(event: str, t0: str, n_alerts: int):
    raw = ROOT / "data" / "gracedb" / event
    out = ROOT / "data" / "skymaps" / event
    for f in sorted(raw.glob("*.fits")):
        sm.ensure_flat(f, out / f"{f.stem}.fits.gz")
    p = gweventlog.write(event, t0, n_alerts)
    print("wrote", p)
    if gweventlog.UNMATCHED:
        print("circular subjects with no attribution rule (check!):")
        for s in gweventlog.UNMATCHED:
            print("  ", s)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], int(sys.argv[3]))
