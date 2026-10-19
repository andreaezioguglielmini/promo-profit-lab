"""The promo analyst agent.

Claude gets the restaurant's exports behind a set of analysis tools
(promolab.tools), decides which to call, and must finish by calling
`submit_report`. Before a report is accepted, a grounding check verifies that
every figure in it appears in some tool result; if not, the call is rejected
with the offending numbers and the model revises. The loop is bounded in turns
and every step is traced, so runs can be scored (promolab.evals).

Two interchangeable policies drive the same loop:
- ClaudePolicy: the LLM (Anthropic Messages API with tool use).
- ScriptedPolicy: a fixed, deterministic plan. It needs no API key, is the
  baseline the LLM is compared against in the evals, and keeps CI hermetic.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

from promolab import grounding
from promolab.tools import ToolError, Workspace, run_tool, tool_specs

DEFAULT_MODEL = "claude-opus-5-5"

SYSTEM_PROMPT = """You are a promotions analyst for independent restaurants that sell on delivery apps.
The owner wants to know whether their discounts make or lose money, and what to do next.

You have tools that load the owner's exports and compute everything: margins, break-even uplift,
the measured uplift with its uncertainty, the profit change in euros, how long a test would take,
and whether ads pay back. Use them; never compute or estimate a figure yourself. Every number in your
report must come from a tool result (rounding is fine).

Work like an analyst: check what data is there and what is missing, look at the business before the promo,
then decide. If the evidence does not settle the question, say so and recommend a test of a concrete length
rather than guessing. State the assumptions that matter (for example, food cost assumed instead of provided).

Finish by calling submit_report once. Write the report in {language}, for an owner who is not a data person:
short, concrete, in euros, with the decision first."""


@dataclass
class ToolCall:
    id: str
    name: str
    input: dict


@dataclass
class Turn:
    text: str
    tool_calls: list[ToolCall]
    content: list  # assistant content blocks to append to the transcript
    stop_reason: str
    usage: dict = field(default_factory=dict)


class Policy(Protocol):
    name: str

    def next_turn(self, system: str, messages: list[dict], tools: list[dict]) -> Turn: ...


@dataclass
class Step:
    tool: str
    input: dict
    output: Any
    is_error: bool
    ms: float


@dataclass
class AgentResult:
    report: dict | None
    steps: list[Step]
    grounding: grounding.GroundingResult | None
    rejected_reports: int
    turns: int
    usage: dict
    seconds: float
    policy: str
    stopped: str

    def tools_used(self) -> list[str]:
        return [s.tool for s in self.steps]


class AgentError(RuntimeError):
    pass


class PromoAgent:
    def __init__(self, policy: Policy, workspace: Workspace, language: str = "Italian", max_turns: int = 14, max_rejections: int = 2):
        self.policy = policy
        self.ws = workspace
        self.language = language
        self.max_turns = max_turns
        self.max_rejections = max_rejections

    def run(self, question: str = "Is my current promo making me money? What should I do next?") -> AgentResult:
        system = SYSTEM_PROMPT.format(language=self.language)
        tools = tool_specs()
        messages: list[dict] = [{"role": "user", "content": question}]
        steps: list[Step] = []
        usage: dict[str, int] = {}
        rejected = 0
        report = None
        check = None
        stopped = "max_turns"
        t0 = time.perf_counter()

        for turn_no in range(1, self.max_turns + 1):  # noqa: B007 (read after the loop)
            turn = self.policy.next_turn(system, messages, tools)
            for k, v in turn.usage.items():
                usage[k] = usage.get(k, 0) + v
            messages.append({"role": "assistant", "content": turn.content})
            if turn.stop_reason == "refusal":
                stopped = "refusal"
                break
            if not turn.tool_calls:
                stopped = "no_report"  # the model ended without submitting
                break

            results = []
            for call in turn.tool_calls:
                if call.name == "submit_report":
                    check = grounding.check(call.input.get("report_markdown", ""), [s.output for s in steps if not s.is_error])
                    if check.ok or rejected >= self.max_rejections:
                        report = call.input
                        results.append(_result(call.id, {"accepted": True, "ungrounded_numbers": check.ungrounded}))
                    else:
                        rejected += 1
                        msg = (
                            "Report rejected: these figures do not appear in any tool result: "
                            + ", ".join(check.ungrounded)
                            + ". Call a tool that computes them, or remove them, then submit again."
                        )
                        results.append(_result(call.id, msg, error=True))
                    continue
                start = time.perf_counter()
                try:
                    out, err = run_tool(self.ws, call.name, call.input), False
                except (ToolError, TypeError, ValueError) as e:
                    out, err = f"Error: {e}", True
                steps.append(Step(call.name, call.input, out, err, (time.perf_counter() - start) * 1000))
                results.append(_result(call.id, out, error=err))
            messages.append({"role": "user", "content": results})
            if report is not None:
                stopped = "submitted"
                break

        return AgentResult(
            report=report,
            steps=steps,
            grounding=check,
            rejected_reports=rejected,
            turns=turn_no,
            usage=usage,
            seconds=time.perf_counter() - t0,
            policy=self.policy.name,
            stopped=stopped,
        )


def _result(tool_use_id: str, content: Any, error: bool = False) -> dict:
    body = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False, default=str)
    block = {"type": "tool_result", "tool_use_id": tool_use_id, "content": body}
    if error:
        block["is_error"] = True
    return block


# ------------------------------------------------------------------ policies


class ClaudePolicy:
    """Claude decides which tools to call (Anthropic Messages API, tool use)."""

    def __init__(self, model: str = DEFAULT_MODEL, effort: str = "medium", client=None):
        import anthropic

        self.client = client or anthropic.Anthropic()
        self.model = model
        self.effort = effort
        self.name = f"claude:{model}"

    def next_turn(self, system: str, messages: list[dict], tools: list[dict]) -> Turn:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=16000,
            system=system,
            tools=tools,
            messages=messages,
            output_config={"effort": self.effort},
        )
        calls = [ToolCall(b.id, b.name, dict(b.input)) for b in response.content if b.type == "tool_use"]
        text = "".join(b.text for b in response.content if b.type == "text")
        u = response.usage
        return Turn(
            text=text,
            tool_calls=calls,
            content=response.content,
            stop_reason=response.stop_reason,
            usage={"input_tokens": u.input_tokens, "output_tokens": u.output_tokens},
        )


class ScriptedPolicy:
    """Deterministic baseline: always runs the same analysis plan and fills a report template."""

    name = "scripted-baseline"
    PLAN = ["inspect_data", "sales_overview", "evaluate_promo", "plan_experiment", "evaluate_ads"]

    def __init__(self, language: str = "Italian"):
        self.language = language

    def next_turn(self, system: str, messages: list[dict], tools: list[dict]) -> Turn:
        done = _tool_results(messages)
        for i, name in enumerate(self.PLAN):
            if name not in done:
                return _tool_turn(f"call_{i}", name, {})
        report = scripted_report(done)
        return _tool_turn("call_submit", "submit_report", report)


def _tool_turn(call_id: str, name: str, args: dict) -> Turn:
    block = {"type": "tool_use", "id": call_id, "name": name, "input": args}
    return Turn(text="", tool_calls=[ToolCall(call_id, name, args)], content=[block], stop_reason="tool_use")


def _tool_results(messages: list[dict]) -> dict[str, Any]:
    """Map tool name -> parsed result from the transcript (errors map to None)."""
    names = {}
    out: dict[str, Any] = {}
    for m in messages:
        if not isinstance(m["content"], list):
            continue
        for b in m["content"]:
            b = b if isinstance(b, dict) else b.model_dump()
            if b.get("type") == "tool_use":
                names[b["id"]] = b["name"]
            elif b.get("type") == "tool_result":
                out[names[b["tool_use_id"]]] = None if b.get("is_error") else json.loads(b["content"])
    return out


def _pct(x: float | None) -> str:
    return "n.d." if x is None else f"{x * 100:.0f}%"


def _it(x: float, decimals: int = 1) -> str:
    """Italian number format: 1.234,5"""
    return f"{x:,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _eur(x: float) -> str:
    return "€" + _it(x, 2)


def scripted_report(r: dict[str, Any]) -> dict:
    ev, plan, ads, ov = r.get("evaluate_promo"), r.get("plan_experiment"), r.get("evaluate_ads"), r.get("sales_overview")
    lines = []
    if ev is None:
        verdict, rec, nights, uplift = "inconclusive", "run_experiment", plan and plan["total_open_nights"], None
        lines.append("**Decisione:** con questi dati non si può misurare l'effetto della promo.")
    else:
        verdict, uplift = ev["verdict"], ev["estimated_uplift"]
        rec = {"profitable": "keep_promo", "unprofitable": "stop_promo", "inconclusive": "run_experiment"}[verdict]
        nights = plan["total_open_nights"] if (plan and verdict == "inconclusive") else None
        head = {
            "profitable": "la promo fa guadagnare: tienila.",
            "unprofitable": "la promo fa perdere soldi: sospendila o riduci lo sconto.",
            "inconclusive": "non si può ancora dire se la promo fa guadagnare.",
        }[verdict]
        lines.append(f"**Decisione:** {head}")
        lines.append("")
        lines.append(
            f"- Con lo sconto del {_pct(ev['discount'])} il margine per ordine scende da {_eur(ev['margin_per_order_full_price'])} "
            f"a {_eur(ev['margin_per_order_with_discount'])}: servono almeno il {_pct(ev['breakeven_uplift'])} di ordini in più per andare in pari."
        )
        lo, hi = ev["uplift_interval_90"]
        lines.append(f"- Nelle sere in promo gli ordini sono aumentati del {_pct(uplift)} (intervallo plausibile {_pct(lo)}–{_pct(hi)}).")
        lines.append(
            f"- Effetto sul margine: {_eur(ev['profit_change_per_promo_night'])} per sera in promo, "
            f"{_eur(ev['profit_change_over_observed_promo_nights'])} sulle {ev['promo_nights_observed']} sere osservate."
        )
        if ev.get("costs_assumed"):
            lines.append("- Attenzione: il food cost non è stato fornito ed è stimato; con i costi veri il risultato può cambiare.")
    if plan and verdict == "inconclusive":
        lines.append(
            f"- Prossimo passo: un test con promo accesa e spenta a sere alterne per {plan['total_open_nights']} sere "
            f"(circa {_it(plan['weeks_needed'])} settimane)."
        )
    if ads:
        lines.append(
            f"- Annunci: ROAS {_it(ads['roas'])} contro un ROAS di pareggio di {_it(ads['breakeven_roas_if_partly_incremental'])} "
            f"(se metà degli ordini da annuncio sarebbe arrivata comunque)."
        )
    if ov:
        lines.append(
            f"- Contesto: {_it(ov['orders_per_night'])} ordini a sera, scontrino medio pagato {_eur(ov['average_order_value_paid'])}."
        )
    return {
        "verdict": verdict,
        "estimated_uplift": uplift,
        "recommendation": rec,
        "experiment_nights": nights,
        "report_markdown": "\n".join(lines),
    }


def default_policy() -> Policy:
    """Claude when an API key is configured, the scripted baseline otherwise."""
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        return ClaudePolicy()
    return ScriptedPolicy()
