"""Download the PRIMARY data of a gravitational-wave event into data/gracedb/<event>/ and data/gcn/<event>/.

    .venv/bin/python -I scripts/fetch_gw_event.py S241125n

Sources (public, no account): GraceDB superevent record, log, notice XMLs, em_bright / p_astro files and every sky map
that a notice references (including LVK+external joint maps); NASA GCN circulars that match the event name
(JSON, with the exact `createdOn` time). Existing files are kept, so re-running only fills gaps.
Sky maps are saved under our own key (bayestar_0, bilby_0, bilby_offline0_0, combined_0, ...), see gweventlog.MAP_NAMES.
"""
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from rewindsky.gweventlog import map_key  # noqa: E402

GDB = "https://gracedb.ligo.org/api/superevents"
GCN = "https://gcn.nasa.gov/circulars"


def get(url: str, timeout: int = 120) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "rewindsky"}), timeout=timeout) as r:
        return r.read()


def save(url: str, path: Path) -> bool:
    if path.exists() and path.stat().st_size > 0:
        return False
    path.write_bytes(get(url))
    return True


def main(event: str):
    gdb = ROOT / "data" / "gracedb" / event
    gcn = ROOT / "data" / "gcn" / event
    gdb.mkdir(parents=True, exist_ok=True)
    gcn.mkdir(parents=True, exist_ok=True)
    new = 0
    for name, ep in (("superevent.json", ""), ("logs.json", "logs/"), ("files.json", "files/")):
        new += save(f"{GDB}/{event}/{ep}", gdb / name)
    files = json.loads((gdb / "files.json").read_text())
    notices = sorted(f for f in files if re.fullmatch(rf"{event}-\d+-\w+\.xml", f))
    for f in notices:
        new += save(f"{GDB}/{event}/files/{f}", gdb / f)
    maps = set()
    for f in notices:
        root = ET.parse(gdb / f).getroot()
        for p in root.iter("Param"):
            if p.get("name") in ("skymap_fits", "joint_skymap_fits"):
                maps.add(p.get("value"))
    for url in sorted(maps):
        new += save(url, gdb / f"{map_key(url)}.fits")                 # multi-order files keep full resolution
    for f in files:
        if re.fullmatch(r"(em_bright|[a-z]+\.p_astro)\.json(,\d+)?", f):
            new += save(f"{GDB}/{event}/files/{f}", gdb / f.replace(",", "_"))
    html = get(f"{GCN}?query={event}&limit=100").decode("utf-8", "replace")
    nums = sorted({int(x) for x in re.findall(r"/circulars/(\d{4,6})", html)})
    for n in nums:
        new += save(f"{GCN}/{n}.json", gcn / f"{n}.json")
    print(f"{event}: {len(notices)} notices, {len(maps)} sky maps, {len(nums)} circulars; {new} files downloaded, rest already present")


if __name__ == "__main__":
    main(sys.argv[1])
