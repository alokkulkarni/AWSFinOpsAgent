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
def _agent(regions_tuple, skills_on=False):
    # skills_on is part of the cache key so toggling it in the sidebar rebuilds the agent.
    from devops_core.agents.estate import build_estate_agent
    from devops_core.discovery.index import EstateIndex
    from devops_core.tools.diagnose_tool import build_diagnose_tools
    from devops_core.tools.diagram_tool import build_diagram_tools
    from devops_core.tools.estate import build_estate_tools
    from devops_core.tools.review_tool import build_review_tools
    idx = EstateIndex(estate=_scan(regions_tuple))           # reuse the cached estate (no re-scan)
    cfg = Config.load()
    # diagnose: no captured cfg so it Config.load()s fresh each call → picks up the live action
    # posture (FINOPS_MODE), which the page exports from the sidebar selector before each turn.
    tools = (build_estate_tools(index=idx) + build_diagram_tools(index=idx)
             + build_review_tools(cfg=cfg) + build_diagnose_tools())
    return build_estate_agent(cfg=cfg, callback_handler=None, tools=tools, skills=skills_on)


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


_SEV_ICON = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🔵", "info": "⚪"}
_CONF_ICON = {"high": "🟢", "medium": "🟡", "low": "⚪"}


def _render_review_result(res: dict):
    by = res.get("by_severity") or {}
    head = "  ".join(f"{_SEV_ICON.get(s, '')} {n} {s}" for s, n in by.items()) or "none"
    st.markdown(f"**{res['finding_count']} finding(s)** — {head}")
    for f in res["findings"]:
        with st.container(border=True):
            st.markdown(f"{_SEV_ICON.get(f['severity'], '')} **{f['title']}**  · `{f['category']}`")
            st.markdown(f"`{f['current']}`  →  **{f['recommended']}**")
            st.caption(f["rationale"])
            if f.get("doc_url"):
                st.markdown(f"[AWS docs]({f['doc_url']})")
    for n in res.get("notes", []):
        st.caption(f"• {n}")


def _render_diagnose_result(res: dict):
    s = res.get("signals", {})
    st.markdown(f"signals: **{len(s.get('alarms', []))}** alarm(s) · "
                f"**{len(s.get('log_errors', []))}** error log line(s) · "
                f"**{len(s.get('recent_changes', []))}** recent change(s) — posture **{res['mode']}**")
    if res.get("healthy"):
        st.success("✓ No active fault detected in the inspected window.")
    for h in res["hypotheses"]:
        with st.container(border=True):
            st.markdown(f"{_CONF_ICON.get(h['confidence'], '')} **{h['cause']}**  · "
                        f"{h['confidence']} confidence")
            for ev in h["evidence"][:4]:
                st.caption(f"• {ev}")
            st.markdown(f"**Fix:** {h['fix']}")
            if h.get("fix_command"):
                st.code(h["fix_command"], language="bash")
            if h.get("apply"):
                st.warning(h["apply"])
            if h.get("doc_url"):
                st.markdown(f"[AWS docs]({h['doc_url']})")
    for n in res.get("notes", []):
        st.caption(f"• {n}")


def render():
    from devops_core.diagram.drawio import build_drawio
    from devops_core.diagram.svg import build_svg

    st.title("AWS Estate — DevOps")
    with st.sidebar:
        regions_raw = st.text_input("Regions (comma; blank = all enabled)", value="eu-west-2,us-east-1")
        group_by = st.selectbox("Diagram grouping", ["region", "account"])
        st.session_state["skills"] = st.checkbox(
            "Agent skills (beta)", value=st.session_state.get("skills", Config.load().skills_enabled),
            key="skills_select_devops",
            help="Progressive-disclosure playbooks (e.g. incident-triage runbook) for the estate agent.",
        )
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

    st.subheader("🔍 Review & 🩺 debug a resource")
    st.caption("Deterministic fast-path (no LLM): best-practice review (config/sizing/metrics, "
               "Lambda also code) or fault diagnosis (alarms/logs/CloudTrail). Fix posture follows "
               "the sidebar Action mode.")
    from apps.dashboard.resource_select import resource_choices
    reviewable = [s for s in ("lambda", "ec2", "rds", "s3") if s in d["by_service"]] \
        or ["lambda", "ec2", "rds", "s3"]
    pc1, pc2 = st.columns([1, 3])
    rv_svc = pc1.selectbox("Service", reviewable, key="rv_service")
    choices = resource_choices(d["resources"], rv_svc)
    chosen = None
    if choices:
        labels = [c["label"] for c in choices]
        pick = pc2.selectbox(f"Resource ({len(choices)})", labels, key="rv_resource")
        chosen = choices[labels.index(pick)]
    else:
        manual = pc2.text_input(f"No {rv_svc} resources scanned — enter a name or ARN",
                                key="rv_manual")
        if manual.strip():
            chosen = {"service": rv_svc, "id": manual.strip(), "region": None}

    posture = st.session_state.get("mode", "advisory")
    b1, b2, b3, _ = st.columns([1, 1, 1, 2])
    do_review = b1.button("🔍 Review", disabled=chosen is None)
    do_diag = b2.button("🩺 Diagnose", disabled=chosen is None)
    do_describe = b3.button("🔎 Describe", disabled=chosen is None)
    if chosen and (do_review or do_diag or do_describe):
        region = chosen.get("region")
        try:
            if do_review:
                from devops_core.review.engine import review_service
                with st.spinner(f"Reviewing {chosen['id']}…"):
                    _render_review_result(
                        review_service(chosen["service"], chosen["id"], region=region).to_dict(limit=15))
            elif do_diag:
                from devops_core.diagnose.engine import diagnose_service
                with st.spinner(f"Diagnosing {chosen['id']}…"):
                    _render_diagnose_result(
                        diagnose_service(chosen["service"], chosen["id"], region=region,
                                         mode=posture).to_dict())
            else:
                from devops_core.discovery.index import EstateIndex
                with st.spinner(f"Describing {chosen['id']}…"):
                    out = EstateIndex(estate=est).describe(chosen["id"])
                st.markdown(f"**{out.get('service', '?')} · {out.get('resource_type', '?')}**  · "
                            f"`{out.get('id', '')}`")
                st.json(out.get("detail") or {"detail": None, "note": out.get("note", "n/a")})
        except Exception as e:
            st.error(f"Failed: {e}")

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
        import os
        from devops_core.diagram import registry as _diag
        os.environ["FINOPS_MODE"] = st.session_state.get("mode", "advisory")  # live fault-fix posture
        _diag.clear()
        try:
            with st.spinner("Thinking…"):
                text = str(_agent(regions_tuple, st.session_state.get("skills", False))(q)).strip()
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
