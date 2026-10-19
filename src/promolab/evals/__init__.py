"""Score the agent on synthetic restaurants whose true promo effect is known.

Each scenario is a simulated restaurant (promolab.simulate.scenario_grid) written
out as raw exports. The agent sees only the exports; the scorer compares its
submitted verdict with the ground truth and checks how it got there.

Metrics
- decision accuracy: share of correct verdicts among the cases where the agent committed
- coverage: share of cases where it committed instead of answering "inconclusive"
- harmful errors: told the owner to keep a promo that actually loses money
- grounded reports: every figure in the report traced to a tool result
- caveat recall: when food costs were missing, did the report say they were assumed
- standard report: share of the hand-made report's analyses the agent ran (sales trend, menu, promo)
- cost: tool calls, turns, tokens, seconds per case
"""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path

from promolab import simulate
from promolab.agent import AgentResult, Policy, PromoAgent
from promolab.tools import Workspace

# Scenarios where an input file is withheld from the agent.
DROP_FILES = {"Tasca L": ["costi_menu.csv"]}
STANDARD_TOOLS = ("sales_trend", "menu_performance", "evaluate_promo")
CAVEAT = re.compile(r"food ?cost|costi|stimat|assum", re.I)


@dataclass
class CaseScore:
    scenario: str
    truth: str  # profitable / unprofitable / unknown
    true_uplift: float
    breakeven_uplift: float
    verdict: str | None
    recommendation: str | None
    estimated_uplift: float | None
    outcome: str  # correct / wrong / abstained / no_report
    harmful: bool
    grounded: bool
    rejected_reports: int
    caveat_needed: bool
    caveat_given: bool
    standard_report: float
    tool_calls: int
    turns: int
    input_tokens: int
    output_tokens: int
    seconds: float


def build_scenarios(root: str | Path, seed: int = 0) -> list[tuple[Path, simulate.GroundTruth]]:
    root = Path(root)
    out = []
    for cfg in simulate.scenario_grid(seed):
        folder = root / f"seed{seed}" / cfg.name.lower().replace(" ", "_")
        if folder.exists():
            shutil.rmtree(folder)
        sim = simulate.simulate(cfg)
        simulate.write_exports(sim, folder)
        for name in DROP_FILES.get(cfg.name, []):
            (folder / name).unlink()
        # The truth file stays outside what the agent loads (it only reads *.csv).
        out.append((folder, sim["truth"]))
    return out


def truth_label(t: simulate.GroundTruth) -> str:
    if t.promo_days == 0:
        return "unknown"
    return "profitable" if t.promo_is_profitable else "unprofitable"


def score_case(name: str, truth: simulate.GroundTruth, res: AgentResult, caveat_needed: bool) -> CaseScore:
    label = truth_label(truth)
    rep = res.report or {}
    verdict = rep.get("verdict")
    if not rep:
        outcome = "no_report"
    elif label == "unknown":
        outcome = "correct" if verdict == "inconclusive" and rep.get("recommendation") == "run_experiment" else "wrong"
    elif verdict == "inconclusive":
        outcome = "abstained"
    else:
        outcome = "correct" if verdict == label else "wrong"
    return CaseScore(
        scenario=name,
        truth=label,
        true_uplift=truth.true_uplift,
        breakeven_uplift=truth.breakeven_uplift,
        verdict=verdict,
        recommendation=rep.get("recommendation"),
        estimated_uplift=rep.get("estimated_uplift"),
        outcome=outcome,
        harmful=verdict == "profitable" and label == "unprofitable",
        grounded=bool(res.grounding and res.grounding.ok),
        rejected_reports=res.rejected_reports,
        caveat_needed=caveat_needed,
        caveat_given=bool(CAVEAT.search(rep.get("report_markdown", ""))),
        standard_report=round(sum(t in res.tools_used() for t in STANDARD_TOOLS) / len(STANDARD_TOOLS), 3),
        tool_calls=len(res.steps),
        turns=res.turns,
        input_tokens=res.usage.get("input_tokens", 0),
        output_tokens=res.usage.get("output_tokens", 0),
        seconds=round(res.seconds, 2),
    )


def summarize(cases: list[CaseScore]) -> dict:
    n = len(cases)
    decided = [c for c in cases if c.outcome in ("correct", "wrong")]
    caveat = [c for c in cases if c.caveat_needed]
    errs = [abs(c.estimated_uplift - c.true_uplift) for c in cases if c.estimated_uplift is not None and c.truth != "unknown"]
    return {
        "cases": n,
        "decision_accuracy": round(sum(c.outcome == "correct" for c in decided) / len(decided), 3) if decided else None,
        "coverage": round(len(decided) / n, 3),
        "harmful_errors": sum(c.harmful for c in cases),
        "grounded_reports": round(sum(c.grounded for c in cases) / n, 3),
        "reports_rejected_then_fixed": sum(c.rejected_reports > 0 and c.grounded for c in cases),
        "caveat_recall": round(sum(c.caveat_given for c in caveat) / len(caveat), 3) if caveat else None,
        "standard_report_coverage": round(sum(c.standard_report for c in cases) / n, 3),
        "uplift_mae": round(sum(errs) / len(errs), 3) if errs else None,
        "avg_tool_calls": round(sum(c.tool_calls for c in cases) / n, 1),
        "avg_turns": round(sum(c.turns for c in cases) / n, 1),
        "avg_input_tokens": round(sum(c.input_tokens for c in cases) / n),
        "avg_output_tokens": round(sum(c.output_tokens for c in cases) / n),
        "avg_seconds": round(sum(c.seconds for c in cases) / n, 2),
    }


def run_suite(policy: Policy, root: str | Path = "data/synthetic/eval", seeds: tuple[int, ...] = (0, 1, 2)) -> tuple[list[CaseScore], dict]:
    """Every scenario is replicated with different random seeds: one draw of a noisy restaurant proves little."""
    cases = []
    for seed in seeds:
        for folder, truth in build_scenarios(root, seed):
            ws = Workspace.from_folder(folder)
            res = PromoAgent(policy, ws).run()
            cases.append(score_case(f"{truth.restaurant} #{seed}", truth, res, caveat_needed=ws.data.costs is None))
    return cases, summarize(cases)


def to_markdown(policy_name: str, cases: list[CaseScore], summary: dict) -> str:
    lines = [f"## {policy_name}", "", "| metric | value |", "|---|---|"]
    lines += [f"| {k} | {v} |" for k, v in summary.items()]
    lines += [
        "",
        "| scenario | truth | true uplift | break-even | verdict | recommendation | outcome | grounded | tool calls |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for c in cases:
        lines.append(
            f"| {c.scenario} | {c.truth} | {c.true_uplift:.0%} | {c.breakeven_uplift:.0%} | {c.verdict} | {c.recommendation} | "
            f"{c.outcome} | {'yes' if c.grounded else 'no'} | {c.tool_calls} |"
        )
    return "\n".join(lines) + "\n"


def save(policy_name: str, cases: list[CaseScore], summary: dict, out_dir: str | Path = "evals") -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "-", policy_name.lower()).strip("-")
    (out / f"{slug}.json").write_text(
        json.dumps({"policy": policy_name, "summary": summary, "cases": [asdict(c) for c in cases]}, indent=2)
    )
    (out / f"{slug}.md").write_text(to_markdown(policy_name, cases, summary))
    return out / f"{slug}.md"
