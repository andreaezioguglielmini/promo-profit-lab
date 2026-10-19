import json
from types import SimpleNamespace

import pytest

from promolab import agent, simulate, tools


@pytest.fixture(scope="module")
def ws(tmp_path_factory):
    folder = tmp_path_factory.mktemp("rest")
    simulate.write_exports(simulate.simulate(simulate.RestaurantConfig(seed=11)), folder)
    return tools.Workspace.from_folder(folder)


def test_scripted_agent_submits_a_grounded_report(ws):
    res = agent.PromoAgent(agent.ScriptedPolicy(), ws).run()
    assert res.stopped == "submitted"
    assert res.grounding.ok
    assert res.report["verdict"] in {"profitable", "unprofitable", "inconclusive"}
    assert "evaluate_promo" in res.tools_used()


class Hallucinator:
    """Fake model: submits an invented figure first, then fixes it after the rejection."""

    name = "fake"

    def __init__(self):
        self.calls = 0

    def next_turn(self, system, messages, tools_):
        self.calls += 1
        if self.calls == 1:
            return agent._tool_turn("a", "evaluate_promo", {})
        if self.calls == 2:
            report = {
                "verdict": "profitable",
                "estimated_uplift": 0.5,
                "recommendation": "keep_promo",
                "experiment_nights": None,
                "report_markdown": "Hai guadagnato €987,65.",
            }
            return agent._tool_turn("b", "submit_report", report)
        ev = json.loads(messages[2]["content"][0]["content"])
        text = f"Effetto: €{ev['profit_change_per_promo_night']} per sera."
        report = {
            "verdict": ev["verdict"],
            "estimated_uplift": ev["estimated_uplift"],
            "recommendation": "run_experiment",
            "experiment_nights": None,
            "report_markdown": text,
        }
        return agent._tool_turn("c", "submit_report", report)


def test_ungrounded_report_is_rejected_then_fixed(ws):
    res = agent.PromoAgent(Hallucinator(), ws).run()
    assert res.rejected_reports == 1
    assert res.grounding.ok
    assert "987" not in res.report["report_markdown"]


def test_tool_errors_go_back_to_the_model(ws):
    class BadArgs:
        name = "bad"

        def __init__(self):
            self.n = 0

        def next_turn(self, system, messages, tools_):
            self.n += 1
            if self.n == 1:
                return agent._tool_turn("a", "unit_economics", {"discount": 20})
            last = messages[-1]["content"][0]
            assert last["is_error"] and "fraction" in last["content"]
            return agent.Turn("done", [], [{"type": "text", "text": "done"}], "end_turn")

    res = agent.PromoAgent(BadArgs(), ws).run()
    assert res.stopped == "no_report"
    assert res.steps[0].is_error


def test_claude_policy_translates_sdk_responses(ws):
    """ClaudePolicy against a stub client shaped like the Anthropic SDK."""
    script = iter(
        [
            [SimpleNamespace(type="tool_use", id="t1", name="inspect_data", input={})],
            [
                SimpleNamespace(type="text", text="Fatto."),
                SimpleNamespace(
                    type="tool_use",
                    id="t2",
                    name="submit_report",
                    input={
                        "verdict": "inconclusive",
                        "estimated_uplift": None,
                        "recommendation": "run_experiment",
                        "experiment_nights": None,
                        "report_markdown": "Servono più dati.",
                    },
                ),
            ],
        ]
    )
    sent = []

    def create(**kwargs):
        sent.append(kwargs)
        content = next(script)
        stop = "tool_use" if any(b.type == "tool_use" for b in content) else "end_turn"
        return SimpleNamespace(content=content, stop_reason=stop, usage=SimpleNamespace(input_tokens=100, output_tokens=20))

    client = SimpleNamespace(messages=SimpleNamespace(create=create))
    res = agent.PromoAgent(agent.ClaudePolicy(client=client), ws).run()
    assert res.stopped == "submitted"
    assert res.usage == {"input_tokens": 200, "output_tokens": 40}
    assert sent[0]["model"] == agent.DEFAULT_MODEL
    assert {t["name"] for t in sent[0]["tools"]} >= {"evaluate_promo", "submit_report"}
