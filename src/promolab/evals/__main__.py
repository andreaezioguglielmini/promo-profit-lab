"""python -m promolab.evals --policy scripted|claude [--model claude-opus-5-5]"""

import argparse

from promolab.agent import DEFAULT_MODEL, ClaudePolicy, ScriptedPolicy
from promolab.evals import run_suite, save


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--policy", choices=["scripted", "claude"], default="scripted")
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--effort", default="medium")
    p.add_argument("--seeds", type=int, default=3, help="replicates of each scenario")
    p.add_argument("--out", default="evals")
    args = p.parse_args()

    policy = ScriptedPolicy() if args.policy == "scripted" else ClaudePolicy(args.model, args.effort)
    cases, summary = run_suite(policy, seeds=tuple(range(args.seeds)))
    path = save(policy.name, cases, summary, args.out)
    for k, v in summary.items():
        print(f"{k:28s} {v}")
    print(f"\nwritten to {path}")


if __name__ == "__main__":
    main()
