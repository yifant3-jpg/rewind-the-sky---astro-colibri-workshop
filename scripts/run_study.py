"""Run the S241125n strategy study (baseline + sensitivities) and print the summaries.

    .venv/bin/python -I scripts/run_study.py [baseline|all] [s241125n|s250206dm|s250818k]

Needs a real file (not stdin) because macOS multiprocessing re-imports the main module in the workers.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

import importlib  # noqa: E402

from rewindsky import study  # noqa: E402


def main(which: str = "baseline", event_module: str = "s241125n"):
    E = importlib.import_module(f"rewindsky.{event_module}")
    if hasattr(E, "ensure_candidate_truth"):
        E.ensure_candidate_truth()
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 40)
    setups = {"baseline": {"baseline": E.BASE}, "all": E.SENSITIVITY}[which]
    res = study.run_study(E.EVENT, E.STRATEGIES, list(setups.values()), workers=10)
    for name, su in setups.items():
        s = study.summarise(res, su.tag(), E.STRATEGIES, E.TRUTHS, su, E.T0)
        print(f"\n===== {name}  ({su.tag()}) =====")
        print(s.T.to_string())


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "baseline", sys.argv[2] if len(sys.argv) > 2 else "s241125n")
