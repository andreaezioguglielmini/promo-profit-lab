"""Promo Profit Lab demo: run the agent, play with break-even, plan a test, see the evals."""

import json
import os
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

from promolab import experiments, margins
from promolab.agent import ClaudePolicy, PromoAgent, ScriptedPolicy
from promolab.tools import Workspace

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "data" / "synthetic" / "demo"

st.set_page_config(page_title="Promo Profit Lab", layout="wide")
st.title("Promo Profit Lab")
st.caption("An AI agent that tells a delivery restaurant whether its discounts make money. All data shown is synthetic.")


def api_key_available() -> bool:
    """Use an API key from the environment or from Streamlit secrets (Streamlit Community Cloud)."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        return True
    try:
        key = st.secrets["ANTHROPIC_API_KEY"]
    except Exception:
        return False
    os.environ["ANTHROPIC_API_KEY"] = key
    return True


has_key = api_key_available()

agent_tab, calc_tab, plan_tab, eval_tab = st.tabs(["Agent", "Break-even calculator", "Test planner", "Evals"])

with agent_tab:
    left, right = st.columns([1, 2])
    with left:
        source = st.radio("Data", ["Synthetic demo restaurant", "Upload Deliveroo exports (CSV)"])
        uploads = None
        if source.startswith("Upload"):
            uploads = st.file_uploader("Orders, product sales, ads, costs, promo calendar", type="csv", accept_multiple_files=True)
        options = ["Claude (tool use)", "Scripted baseline"] if has_key else ["Scripted baseline"]
        policy_name = st.selectbox("Policy", options)
        if not has_key:
            st.info("Set ANTHROPIC_API_KEY to let Claude drive the analysis. Without it the deterministic baseline runs the same tools.")
        language = st.selectbox("Report language", ["Italian", "English"])
        question = st.text_area("Question", "Is my current promo making me money? What should I do next?")
        go = st.button("Run agent", type="primary")

    with right:
        if go:
            folder = DEMO
            if uploads:
                tmp = Path(tempfile.mkdtemp())
                for f in uploads:
                    (tmp / f.name).write_bytes(f.getvalue())
                folder = tmp
            ws = Workspace.from_folder(folder)
            policy = ClaudePolicy() if policy_name.startswith("Claude") else ScriptedPolicy()
            with st.spinner("The agent is working..."):
                res = PromoAgent(policy, ws, language=language).run(question)
            if res.report:
                badge = "every figure traced to a tool" if res.grounding and res.grounding.ok else "some figures not traced"
                st.markdown(f"**Verdict:** `{res.report['verdict']}` · **Recommendation:** `{res.report['recommendation']}` · {badge}")
                st.markdown(res.report["report_markdown"])
            else:
                st.error(f"No report ({res.stopped}).")
            st.caption(
                f"{res.policy} · {res.turns} turns · {len(res.steps)} tool calls · {res.rejected_reports} report(s) rejected by the grounding check"
                + (f" · {res.usage.get('input_tokens', 0)} in / {res.usage.get('output_tokens', 0)} out tokens" if res.usage else "")
            )
            st.subheader("Trace")
            for i, step in enumerate(res.steps, 1):
                with st.expander(f"{i}. {step.tool}({json.dumps(step.input)}) · {step.ms:.0f} ms" + (" · error" if step.is_error else "")):
                    st.json(step.output if isinstance(step.output, dict) else {"error": step.output})

with calc_tab:
    st.write("How many extra orders a discount needs before it stops losing money (framework section 5).")
    c1, c2 = st.columns(2)
    with c1:
        price = st.number_input("Dish price (€)", 1.0, 100.0, 10.0, 0.5)
        commission = st.slider("Platform commission", 0.0, 0.40, 0.30, 0.01)
        food = st.number_input("Food cost (€)", 0.0, 50.0, 2.5, 0.1)
        pack = st.number_input("Packaging (€)", 0.0, 5.0, 0.5, 0.1)
        discount = st.slider("Discount", 0.05, 0.50, 0.20, 0.05)
        iota = st.slider("Share of extra orders that are genuinely new", 0.3, 1.0, 1.0, 0.05)
    m0 = margins.unit_margin(price, commission, food, pack)
    m1 = margins.promo_margin(price, discount, commission, food, pack)
    u = margins.breakeven_uplift(m0, m1, iota)
    with c2:
        st.metric("Margin per dish, full price", f"€{m0:.2f}")
        st.metric("Margin per dish, with discount", f"€{m1:.2f}", f"{(m1 / m0 - 1):.0%}" if m0 > 0 else None)
        st.metric("Extra orders needed to break even", "never" if u == float("inf") else f"+{u:.0%}")
        curve = pd.DataFrame({"discount": [d / 100 for d in range(5, 51, 5)]})
        curve["break-even uplift"] = [
            min(margins.breakeven_uplift(m0, margins.promo_margin(price, d, commission, food, pack), iota), 5.0) for d in curve["discount"]
        ]
        st.line_chart(curve.set_index("discount"))

with plan_tab:
    st.write("How long a promo on/off test must run to see an effect (switchback design, 10% significance, 80% power).")
    base = st.slider("Orders per night today", 1.0, 40.0, 3.5, 0.5)
    target = st.slider("Uplift to detect", 0.1, 1.5, 0.5, 0.05)
    n = experiments.nights_per_arm(base, target)
    st.metric("Open nights needed", 2 * n, help="half with the promo, half without")
    grid = pd.DataFrame({"orders per night": [1, 2, 3, 5, 8, 12, 20, 40]})
    grid["nights needed"] = [2 * experiments.nights_per_arm(b, target) for b in grid["orders per night"]]
    st.bar_chart(grid.set_index("orders per night"))

with eval_tab:
    st.write("The agent is scored on synthetic restaurants whose true promo effect is known.")
    files = sorted((ROOT / "evals").glob("*.json"))
    if not files:
        st.info("Run `make eval` (baseline) or `make eval-live` (Claude) to produce results.")
    summaries = {}
    for f in files:
        data = json.loads(f.read_text())
        summaries[data["policy"]] = data["summary"]
    if summaries:
        st.dataframe(pd.DataFrame(summaries))
        pick = st.selectbox("Cases", list(summaries))
        cases = json.loads(next(f for f in files if json.loads(f.read_text())["policy"] == pick).read_text())["cases"]
        st.dataframe(pd.DataFrame(cases))
