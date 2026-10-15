"""Quiz mode: show what was known at time T, ask what you would do, reveal what came next.

    q = Quiz(log)
    q.ask(hours=0.1)          # prints the snapshot at T0 + 0.1 h and the question
    q.reveal(hours=0.1)       # prints what became known in the next window and what actually happened

The snapshot comes from `replay.state_at`, so it is leak-free by construction.
"""
from __future__ import annotations

from datetime import timedelta

from .replay import format_snapshot, parse_t, state_at, t_after

QUESTIONS = (
    "Which observatories could start tonight, and on which part of the sky?",
    "Do you tile the whole localisation now, or wait for more information? What would change your mind?",
)
NOISE_QUESTION = "How many hours of telescope time are you willing to spend on a {p_terr:.0%} chance that this is noise?"
JOINT_QUESTION = ("A sub-threshold gamma-ray candidate is reported in coincidence (joint FAR {far:.1e} Hz as stated now). "
                  "How likely do you think it is the counterpart, and does it change where you point?")


class Quiz:
    def __init__(self, log: dict):
        self.log = log

    def snapshot(self, **delta) -> dict:
        return state_at(self.log, t_after(self.log, **delta))

    def ask(self, **delta) -> None:
        snap = self.snapshot(**delta)
        print(format_snapshot(snap))
        a = snap["latest_alert"]
        print("\n--- Your turn ---")
        qs = list(QUESTIONS)
        if a is not None and a["p_terrestrial"] >= 0.05:
            qs.append(NOISE_QUESTION.format(p_terr=a["p_terrestrial"]))
        j = snap.get("latest_joint")
        if j:
            qs.append(JOINT_QUESTION.format(far=j["joint_far_hz"]))
        for i, q in enumerate(qs, 1):
            print(f"{i}. {q}")

    def reveal(self, window_hours: float = 12.0, **delta) -> None:
        """Everything that became known in (T, T + window_hours]."""
        T = t_after(self.log, **delta)
        end = T + timedelta(hours=window_hours)
        public = ("gw_alert", "joint_skymap", "gcn_circular")          # not the early GraceDB files
        new = [r for r in self.log["rows"] if r["kind"] in public and T < parse_t(r["t"]) <= end]
        print(f"=== Reveal: what arrived in the next {window_hours:g} h (T0 + {(T - parse_t(self.log['t0'])).total_seconds() / 3600:.2f} h -> +{window_hours:g} h) ===")
        if not new:
            print("Nothing new. This is the information vacuum you had to decide in.")
        for r in new:
            h = (parse_t(r["t"]) - parse_t(self.log["t0"])).total_seconds() / 3600
            subj = r["data"].get("subject") or (
                f'{r["label"]}: 90% area {r["data"]["area90"]:g} deg2' if "area90" in r["data"] else r["label"])
            print(f"  T0+{h:7.2f} h  {r['source']:12} {r['label']:12} {subj[:78]}")
