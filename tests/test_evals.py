from promolab import evals
from promolab.agent import ScriptedPolicy


def test_suite_runs_and_scores(tmp_path):
    cases, summary = evals.run_suite(ScriptedPolicy(), root=tmp_path, seeds=(0,))
    assert summary["cases"] == 12
    assert summary["grounded_reports"] == 1.0
    assert summary["caveat_recall"] == 1.0
    no_promo = next(c for c in cases if c.truth == "unknown")
    assert no_promo.outcome == "correct"  # no promo nights: the right answer is to run a test
    md = evals.to_markdown("baseline", cases, summary)
    assert "decision_accuracy" in md
