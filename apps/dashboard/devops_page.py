"""DevOps / estate dashboard page — scan summary, AWS-icon diagram, inventory, and estate chat.

Numbers/inventory come from the deterministic estate tools; the agent only narrates.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from finops_core.config import Config


@st.cache_data(show_spinner="Scanning the AWS estate…", ttl=900)
def _scan(regions_tuple):
    from finops_core.aws.session import build_session
    from devops_core.discovery.engine import EstateScanner
    cfg = Config.load()
    regions = list(regions_tuple) if regions_tuple else None
    return EstateScanner(build_session(cfg), cfg).scan(regions=regions)


@st.cache_resource(show_spinner=False)
def _agent(regions_tuple):
    from devops_core.agents.estate import build_estate_agent
    from devops_core.discovery.index import EstateIndex
    from devops_core.tools.diagram_tool import build_diagram_tools
    from devops_core.tools.estate import build_estate_tools
    idx = EstateIndex(estate=_scan(regions_tuple))           # reuse the cached estate (no re-scan)
    tools = build_estate_tools(index=idx) + build_diagram_tools(index=idx)
    return build_estate_agent(cfg=Config.load(), callback_handler=None, tools=tools)


def _render_chat_diagram(d: dict, key: str):
    """Render a draw_diagram artifact in the chat: SVG inline + .drawio/.png/.svg downloads."""
    import os
    if not d or not d.get("ok"):
        if d and d.get("error"):
            st.caption(f"⚠ diagram: {d['error']}")
        return
    if d.get("svg_content"):
        st.html(f'<div style="overflow:auto;max-height:560px;background:#ffffff;'
                f'border:1px solid #e6e6e6;border-radius:6px">{d["svg_content"]}</div>')
    cols = st.columns(3)
    for col, fmt, label in ((cols[0], "drawio", "⬇ .drawio"),
                            (cols[1], "png", "⬇ .png"), (cols[2], "svg", "⬇ .svg")):
        p = d.get(fmt)
        if p and os.path.exists(p):
            with open(p, "rb") as fh:
                col.download_button(label, fh.read(), file_name=os.path.basename(p),
                                    key=f"dl_{fmt}_{key}")


def render():
    from devops_core.diagram.drawio import build_drawio
    from devops_core.diagram.svg import build_svg

    st.title("AWS Estate — DevOps")
    with st.sidebar:
        regions_raw = st.text_input("Regions (comma; blank = all enabled)", value="eu-west-2,us-east-1")
        group_by = st.selectbox("Diagram grouping", ["region", "account"])
    regions_tuple = tuple(r.strip() for r in regions_raw.split(",") if r.strip())

    try:
        est = _scan(regions_tuple)
    except Exception as e:
        st.error(f"Estate scan failed: {e}\n\nCheck Resource Explorer / tag:GetResources access.")
        return
    d = est.to_dict()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Resources", d["count"])
    c2.metric("Accounts", len(d["accounts"]))
    c3.metric("Regions", len(d["regions"]))
    top = next(iter(d["by_service"].items()), ("—", 0))
    c4.metric("Top service", f"{top[0]} ({top[1]})")
    if d["notes"]:
        with st.expander("Discovery notes / coverage"):
            for n in d["notes"]:
                st.caption(f"• {n}")

    st.subheader("Estate diagram (AWS icons)")
    svg = build_svg(est, group_by=group_by)
    st.html(f'<div style="overflow:auto;max-height:660px;background:#ffffff">{svg}</div>')
    st.download_button("⬇ Download editable .drawio", build_drawio(est, group_by=group_by),
                       file_name="estate.drawio", mime="application/xml")

    st.subheader("Inventory")
    f1, f2 = st.columns(2)
    svc = f1.selectbox("Service", ["(all)"] + list(d["by_service"].keys()))
    reg = f2.selectbox("Region", ["(all)"] + d["regions"])
    rows = [r for r in d["resources"]
            if (svc == "(all)" or r["service"] == svc) and (reg == "(all)" or r["region"] == reg)]
    st.dataframe(pd.DataFrame([{
        "service": r["service"], "type": r["resource_type"], "id": r["id"],
        "region": r["region"], "name": r.get("name"),
    } for r in rows[:500]]), width="stretch", hide_index=True)
    st.caption(f"{len(rows)} resources" + (" (showing first 500)" if len(rows) > 500 else ""))

    st.subheader("Ask about the estate")
    st.caption("Inventory above is exact (tool layer); the agent explains, explores, and draws.")
    if "devops_chat" not in st.session_state:
        st.session_state.devops_chat = []
    for i, m in enumerate(st.session_state.devops_chat):
        st.chat_message(m["role"]).write(m["content"])
        if m.get("diagram"):
            _render_chat_diagram(m["diagram"], key=str(i))
    if q := st.chat_input("e.g. how many EC2 instances? · draw my network in eu-west-2 · diagram the estate"):
        st.session_state.devops_chat.append({"role": "user", "content": q})
        st.chat_message("user").write(q)
        from devops_core.diagram import registry as _diag
        _diag.clear()
        try:
            with st.spinner("Thinking…"):
                text = str(_agent(regions_tuple)(q)).strip()
        except Exception as e:
            text = f"(agent unavailable: {e})"
        diagram = _diag.last_diagram()
        msg = {"role": "assistant", "content": text}
        if diagram:
            msg["diagram"] = diagram
        st.session_state.devops_chat.append(msg)
        st.chat_message("assistant").write(text)
        if diagram:
            _render_chat_diagram(diagram, key="new")
