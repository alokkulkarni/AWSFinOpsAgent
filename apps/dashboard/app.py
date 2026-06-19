"""FinOps dashboard (Streamlit).

Data views (KPIs, cost-per-service, drill-down, trend) are deterministic — rendered from
the CostExplorer tool layer, never the LLM. The chat panel uses the agent for narrative only.

Run: streamlit run apps/dashboard/app.py   (or: make dashboard)
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from apps.dashboard.data import DRILL_ORDER, CostDashboardData, DrillLevel, breadcrumb_to_query
from finops_core.config import Config

st.set_page_config(page_title="AWS FinOps Agent", page_icon="💰", layout="wide")

PERIODS = ["mtd", "last_month", "ytd", "30d", "90d", "3m", "6m", "12m"]
METRICS = ["UnblendedCost", "AmortizedCost", "NetAmortizedCost", "NetUnblendedCost"]


@st.cache_resource(show_spinner=False)
def get_data() -> CostDashboardData:
    return CostDashboardData(Config.load())


@st.cache_data(show_spinner="Querying Cost Explorer…", ttl=600)
def breakdown(stack_tuples, period, metric, top_n):
    stack = [DrillLevel(d, v) for d, v in stack_tuples]
    b = get_data().breakdown(stack, period=period, metric=metric, top_n=top_n)
    return None if b is None else b.to_dict()


@st.cache_data(show_spinner=False, ttl=600)
def kpis(metric):
    return get_data().kpis(metric=metric)


@st.cache_data(show_spinner=False, ttl=600)
def trend(months, metric):
    return get_data().trend(months=months, metric=metric).to_dict()


def money(x, cur="USD"):
    return "—" if x is None else (f"${x:,.2f}" if cur == "USD" else f"{cur} {x:,.2f}")


# ---- state -----------------------------------------------------------------
if "drill" not in st.session_state:
    st.session_state.drill = []  # list[(dimension, value)]

# ---- sidebar ---------------------------------------------------------------
with st.sidebar:
    st.header("💰 FinOps Agent")
    period = st.selectbox("Period", PERIODS, index=0)
    metric = st.selectbox("Metric", METRICS, index=0)
    top_n = st.slider("Top N", 5, 30, 12)
    cfg = Config.load()
    st.caption(f"mode: `{cfg.mode}` · region: `{cfg.aws.ce_region}` · model: `{cfg.llm.provider}`")
    st.caption("Numbers are pulled directly from Cost Explorer (deterministic).")

# ---- KPI row ---------------------------------------------------------------
st.title("AWS Cost Overview")
try:
    k = kpis(metric)
except Exception as e:
    st.error(f"Could not load cost data: {e}\n\nIs Cost Explorer enabled and are credentials set?")
    st.stop()

cur = k["currency"]
delta_txt = None if k["delta_pct_vs_last_month"] is None else f"{k['delta_pct_vs_last_month']}% vs last mo"
c1, c2, c3, c4 = st.columns(4)
c1.metric("Month-to-date", money(k["mtd_total"], cur), delta=delta_txt)
c2.metric("Forecast (EOM)", money(k["forecast_eom"], cur))
c3.metric("Last month", money(k["last_month_total"], cur))
c4.metric("Top service (MTD)", k["top_service"] or "—",
          delta=money(k["top_service_amount"], cur) if k["top_service_amount"] is not None else None)
if k["estimated"]:
    st.caption("⚠️ Current period includes estimated (not-yet-final) figures.")

# ---- cost-per-service + drill-down ----------------------------------------
st.subheader("Cost breakdown — double-click to drill in")

stack = st.session_state.drill
group_by, filters = breadcrumb_to_query([DrillLevel(d, v) for d, v in stack])

# breadcrumb
crumbs = ["All"] + [f"{d}={v}" for d, v in stack]
bc_cols = st.columns(len(crumbs) + 1)
for i, label in enumerate(crumbs):
    if bc_cols[i].button(label, key=f"crumb{i}"):
        st.session_state.drill = stack[:i]
        st.rerun()
if stack and bc_cols[len(crumbs)].button("⬅ Back", key="back_btn"):
    st.session_state.drill = stack[:-1]
    st.rerun()

if group_by is None:
    st.info("Fully drilled in. Use the breadcrumb to go back up.")
else:
    data = breakdown(tuple(stack), period, metric, top_n)
    groups = data["groups"]
    if not groups:
        st.info("No cost data for this period / scope.")
    else:
        df = pd.DataFrame(
            [{group_by: g["key"], "amount": g["amount"], "%": g["pct"]} for g in groups]
        )
        left, right = st.columns([3, 2])
        with left:
            st.dataframe(
                df.style.format({"amount": lambda v: money(v, cur), "%": "{:.1f}%"}),
                width="stretch", hide_index=True,
            )
            st.caption(f"Total: **{money(data['total'], cur)}**"
                       + (f"  ·  (others): {money(data['others'], cur)}"
                          if data["others"] is not None else ""))
        with right:
            st.bar_chart(df.set_index(group_by)["amount"], horizontal=True)

        # drill control
        descendable = [g["key"] for g in groups if g["key"] != "(unattributed)"]
        nxt, _ = breadcrumb_to_query([DrillLevel(d, v) for d, v in stack] + [DrillLevel(group_by, "")])
        if descendable and nxt is not None:
            csel, cbtn = st.columns([3, 1])
            choice = csel.selectbox(f"Pick a {group_by} to drill into → {nxt}",
                                    descendable, key="drill_select")
            if cbtn.button("Drill in ↓", key="drill_btn"):
                st.session_state.drill = stack + [(group_by, choice)]
                st.rerun()

# ---- trend -----------------------------------------------------------------
st.subheader("Monthly trend")
try:
    t = trend(6, metric)
    tdf = pd.DataFrame([{"month": p["start"][:7], "amount": p["amount"]} for p in t["by_period"]])
    st.line_chart(tdf.set_index("month")["amount"])
except Exception as e:
    st.caption(f"(trend unavailable: {e})")

# ---- optimization (advisory; deterministic) --------------------------------
st.subheader("Optimization — potential savings (advisory)")


@st.cache_data(show_spinner="Scanning for savings…", ttl=900)
def optimization():
    from finops_core.aws.session import build_session
    from finops_core.optimize.engine import Optimizer
    c = Config.load()
    return Optimizer(build_session(c), c).all_recommendations().to_dict()


try:
    rep = optimization()
    ocur = rep.get("currency", "USD")
    st.metric("Potential monthly savings", money(rep["total_monthly_savings"], ocur))
    if rep["recommendations"]:
        odf = pd.DataFrame([{
            "savings/mo": r["monthly_savings"], "source": r["source"], "risk": r["risk"],
            "finding": r["title"], "resource": r.get("resource_id") or "",
        } for r in rep["recommendations"]])
        st.dataframe(odf.style.format({"savings/mo": lambda v: money(v, ocur)}),
                     width="stretch", hide_index=True)
    else:
        st.info("No actionable recommendations from enrolled sources right now.")
    if rep["notes"]:
        with st.expander("Coverage notes (unavailable / not-enrolled sources)"):
            for n in rep["notes"]:
                st.write(f"• {n}")
except Exception as e:
    st.caption(f"(optimization unavailable: {e})")

# ---- anomalies & budgets (deterministic) -----------------------------------
st.subheader("Anomalies & budgets")


@st.cache_data(show_spinner="Checking anomalies & budgets…", ttl=600)
def anomalies_budgets():
    from finops_core.anomaly.engine import AnomalyEngine
    from finops_core.aws.session import build_session
    c = Config.load()
    eng = AnomalyEngine(build_session(c), c)
    return eng.anomalies(period="30d").to_dict(), eng.budgets().to_dict()


try:
    anom, buds = anomalies_budgets()
    ac, bc = st.columns(2)
    with ac:
        st.caption(f"Anomalies (30d): {anom['count']} · impact "
                   f"{money(anom['total_impact'], anom['currency'])}")
        if anom["anomalies"]:
            st.dataframe(pd.DataFrame([{
                "impact": a["total_impact"], "date": a["start"][:10],
                "service": a["dimension"],
            } for a in anom["anomalies"]]).style.format(
                {"impact": lambda v: money(v, anom["currency"])}),
                width="stretch", hide_index=True)
        for n in anom["notes"]:
            st.caption(f"• {n}")
    with bc:
        st.caption(f"Budgets: {buds['count']}")
        for b in buds["budgets"]:
            flag = " 🔴 OVER" if b["breached"] else (" 🟠 forecast breach" if b["forecast_breach"] else " 🟢")
            st.write(f"**{b['name']}**{flag} — {money(b['actual'], b['currency'])} / "
                     f"{money(b['limit'], b['currency'])} ({b['pct_used']}% used)")
            if b["pct_used"] is not None:
                st.progress(min(1.0, (b["pct_used"] or 0) / 100))
        for n in buds["notes"]:
            st.caption(f"• {n}")
except Exception as e:
    st.caption(f"(anomalies/budgets unavailable: {e})")

# ---- chat (narrative only; numbers above are authoritative) ---------------
st.subheader("Ask the FinOps agent")
st.caption("Questions are routed deterministically (cost / optimize / anomaly) to the right "
           "specialist; the tables above remain the source of truth for figures.")


@st.cache_resource(show_spinner=False)
def get_router():
    from finops_core.router import IntentRouter
    return IntentRouter(Config.load())


if "chat" not in st.session_state:
    st.session_state.chat = []
for m in st.session_state.chat:
    st.chat_message(m["role"]).write(m["content"])

if q := st.chat_input("e.g. why did EC2 jump last week? / find savings / am I over budget?"):
    st.session_state.chat.append({"role": "user", "content": q})
    st.chat_message("user").write(q)
    try:
        with st.spinner("Thinking…"):
            intent, answer = get_router().answer(q)
        text = f"*(routed to the **{intent}** specialist)*\n\n{answer}"
    except Exception as e:
        text = f"(agent unavailable: {e})"
    st.session_state.chat.append({"role": "assistant", "content": text})
    st.chat_message("assistant").write(text)
