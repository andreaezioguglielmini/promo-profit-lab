"""Command line entry point.

promolab simulate data/synthetic/demo           # write synthetic exports
promolab analyze data/synthetic/demo            # run the agent on a folder of exports
promolab analyze data/synthetic/demo --policy scripted --trace
"""

import argparse
import json
from dataclasses import asdict

from promolab import simulate
from promolab.agent import ClaudePolicy, PromoAgent, ScriptedPolicy, default_policy
from promolab.tools import Workspace


def main() -> None:
    p = argparse.ArgumentParser(prog="promolab")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("simulate", help="write synthetic Deliveroo-style exports")
    s.add_argument("out")
    s.add_argument("--uplift", type=float, default=0.35)
    s.add_argument("--discount", type=float, default=0.20)
    s.add_argument("--days", type=int, default=140)
    s.add_argument("--seed", type=int, default=7)

    a = sub.add_parser("analyze", help="run the agent on a folder of exports")
    a.add_argument("folder")
    a.add_argument("--policy", choices=["auto", "scripted", "claude"], default="auto")
    a.add_argument("--language", default="Italian")
    a.add_argument("--question", default="Is my current promo making me money? What should I do next?")
    a.add_argument("--trace", action="store_true", help="print every tool call")
    a.add_argument("--json", action="store_true")

    args = p.parse_args()
    if args.cmd == "simulate":
        cfg = simulate.RestaurantConfig(true_uplift=args.uplift, promo_discount=args.discount, days=args.days, seed=args.seed)
        out = simulate.write_exports(simulate.simulate(cfg), args.out)
        print(f"wrote exports to {out}")
        return

    policy = {"auto": default_policy, "scripted": ScriptedPolicy, "claude": ClaudePolicy}[args.policy]()
    res = PromoAgent(policy, Workspace.from_folder(args.folder), language=args.language).run(args.question)
    if args.json:
        print(
            json.dumps(
                {"report": res.report, "steps": [asdict(st) for st in res.steps], "usage": res.usage},
                default=str,
                indent=2,
                ensure_ascii=False,
            )
        )
        return
    if args.trace:
        for st in res.steps:
            print(f"-> {st.tool}({json.dumps(st.input)}) {'ERROR' if st.is_error else 'ok'} {st.ms:.0f} ms")
        print()
    print(f"[{res.policy}] {res.stopped} after {res.turns} turns, {len(res.steps)} tool calls\n")
    print(res.report["report_markdown"] if res.report else "No report submitted.")


if __name__ == "__main__":
    main()
