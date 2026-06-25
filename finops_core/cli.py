"""FinOps Agent CLI.

Phase-0 : preflight, whoami, config
Phase-1 : cost {summary,by-service,by-account,drilldown,trend,forecast,dimensions}, ask
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Optional


# --------------------------------------------------------------------------- #
# parser
# --------------------------------------------------------------------------- #
def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="finops", description="AWS FinOps Agent CLI")
    sub = parser.add_subparsers(dest="cmd")

    for name, help_text in (
        ("preflight", "verify AWS identity (STS) + Bedrock model availability"),
        ("whoami", "print caller identity as JSON"),
        ("config", "print effective (redacted) configuration"),
    ):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("--config", default=None, help="path to finops.yaml")

    # cost group
    cost = sub.add_parser("cost", help="cost analysis (Cost Explorer)")
    csub = cost.add_subparsers(dest="view")

    def common(p, with_granularity=False):
        p.add_argument("--config", default=None)
        p.add_argument("--period", default="mtd", help="mtd | last_month | ytd | 30d | 6m ...")
        p.add_argument("--metric", default="UnblendedCost")
        p.add_argument("--json", action="store_true")
        if with_granularity:
            p.add_argument("--granularity", default="MONTHLY", choices=["MONTHLY", "DAILY"])

    common(csub.add_parser("summary", help="total cost, split by sub-period"), with_granularity=True)
    bs = csub.add_parser("by-service", help="ranked cost per service")
    common(bs, with_granularity=True)
    bs.add_argument("--top", type=int, default=10)
    ba = csub.add_parser("by-account", help="cost per linked account (org)")
    common(ba)
    ba.add_argument("--top", type=int, default=20)
    dd = csub.add_parser("drilldown", help="double-click: group by X after filters")
    common(dd, with_granularity=True)
    dd.add_argument("--by", required=True, help="SERVICE|USAGE_TYPE|REGION|...|TAG:<k>")
    dd.add_argument("--filter", action="append", default=[], metavar="DIM=VALUE",
                    help="repeatable scope filter, e.g. --filter 'SERVICE=Amazon EC2'")
    dd.add_argument("--top", type=int, default=15)
    tr = csub.add_parser("trend", help="monthly totals over N months")
    tr.add_argument("--config", default=None)
    tr.add_argument("--months", type=int, default=6)
    tr.add_argument("--metric", default="UnblendedCost")
    tr.add_argument("--json", action="store_true")
    fc = csub.add_parser("forecast", help="forecast future cost")
    fc.add_argument("--config", default=None)
    fc.add_argument("--horizon", default="eom", help="eom | 30d | 3m")
    fc.add_argument("--metric", default="UnblendedCost")
    fc.add_argument("--granularity", default="MONTHLY", choices=["MONTHLY", "DAILY"])
    fc.add_argument("--json", action="store_true")
    dv = csub.add_parser("dimensions", help="list valid values for a dimension")
    dv.add_argument("--config", default=None)
    dv.add_argument("--dimension", required=True)
    dv.add_argument("--period", default="mtd")
    dv.add_argument("--json", action="store_true")

    # optimize group
    opt = sub.add_parser("optimize", help="cost-savings recommendations")
    osub = opt.add_subparsers(dest="view")
    for name in ("summary", "rightsizing", "compute-optimizer", "savings-plans",
                 "reservations", "hub", "trusted-advisor"):
        p = osub.add_parser(name)
        p.add_argument("--config", default=None)
        p.add_argument("--json", action="store_true")

    # org group
    org = sub.add_parser("org", help="organizations / multi-account")
    osub2 = org.add_subparsers(dest="view")
    oa = osub2.add_parser("accounts", help="list linked accounts (id -> name)")
    oa.add_argument("--config", default=None)
    oa.add_argument("--json", action="store_true")

    # anomaly group
    anom = sub.add_parser("anomaly", help="cost anomalies + budgets")
    asub = anom.add_subparsers(dest="view")
    pa = asub.add_parser("anomalies")
    pa.add_argument("--config", default=None)
    pa.add_argument("--period", default="30d")
    pa.add_argument("--json", action="store_true")
    for name in ("budgets", "forecast-vs-budget"):
        p = asub.add_parser(name)
        p.add_argument("--config", default=None)
        p.add_argument("--json", action="store_true")

    # ask (agent) — local in-process, or a remote A2A endpoint (distributed)
    ask = sub.add_parser("ask", help="ask the Cost-Analysis agent (local) or a remote A2A agent")
    ask.add_argument("question")
    ask.add_argument("--config", default=None)
    ask.add_argument("--remote", default=None,
                     metavar="URL", help="call a remote A2A agent (e.g. http://localhost:9000)")
    ask.add_argument("--skills", action=argparse.BooleanOptionalAction, default=None,
                     help="enable/disable agent skills for this question (default: config / FINOPS_SKILLS)")
    ask.add_argument("--memory", action=argparse.BooleanOptionalAction, default=None,
                     help="enable/disable persistent agent memory (default: config / FINOPS_MEMORY)")
    ask.add_argument("--summarize", action=argparse.BooleanOptionalAction, default=None,
                     help="enable/disable conversation summarization (default: config / "
                          "FINOPS_CONVERSATION_SUMMARIZE)")

    # accuracy — reconcile tool-layer numbers against a raw Cost Explorer query
    ac = sub.add_parser("accuracy", help="verify tool numbers match raw Cost Explorer (+ API meter)")
    ac.add_argument("--config", default=None)
    ac.add_argument("--period", default="3m")
    ac.add_argument("--json", action="store_true")

    # digest — scheduled FinOps report (the Workflow DAG)
    dg = sub.add_parser("digest", help="build the FinOps digest report (spend, anomalies, savings)")
    dg.add_argument("--config", default=None)
    dg.add_argument("--format", default="md", choices=["md", "html", "json"])
    dg.add_argument("--narrative", action="store_true", help="add a short LLM summary")
    dg.add_argument("--deliver", default=None, help="comma list: file,slack,sns,ses")
    dg.add_argument("--out", default=None, help="output file path (with --deliver file)")

    # route — deterministic intent routing to a specialist (no orchestrator-LLM guesswork)
    rt = sub.add_parser("route", help="classify a question and route it to the right specialist")
    rt.add_argument("question")
    rt.add_argument("--config", default=None)

    # fix — generate a remediation artifact (artifacts / guarded_write mode)
    fx = sub.add_parser("fix", help="generate a fix script/IaC for a finding (no execution)")
    fx.add_argument("--config", default=None)
    fx.add_argument("--finding-json", default=None, help="a finding as JSON")
    fx.add_argument("--action", default=None)
    fx.add_argument("--resource-id", default=None)
    fx.add_argument("--region", default=None)
    fx.add_argument("--title", default="remediation")
    fx.add_argument("--format", default="cli", choices=["cli", "terraform"])

    # action — guarded-write actions (guarded_write mode only)
    act = sub.add_parser("action", help="guarded-write actions: list / preview / apply")
    a2 = act.add_subparsers(dest="op")
    a2.add_parser("list").add_argument("--config", default=None)
    pv = a2.add_parser("preview")
    pv.add_argument("action_id")
    pv.add_argument("--config", default=None)
    pv.add_argument("--param", action="append", default=[], metavar="K=V")
    ap = a2.add_parser("apply")
    ap.add_argument("action_id")
    ap.add_argument("--token", required=True)
    ap.add_argument("--config", default=None)
    ap.add_argument("--param", action="append", default=[], metavar="K=V")

    # serve — run a distributed service (used as the container command)
    srv = sub.add_parser("serve", help="run a distributed service (MCP tool / A2A agent server)")
    srv.add_argument("service", choices=["cost-tools", "cost-agent", "orchestrator",
                                         "optimize-tools", "optimize-agent",
                                         "anomaly-tools", "anomaly-agent"])

    return parser


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _parse_filters(pairs: list) -> dict:
    out: dict = {}
    for raw in pairs:
        if "=" not in raw:
            raise ValueError(f"bad --filter {raw!r}; expected DIM=VALUE")
        key, value = raw.split("=", 1)
        out[key.strip()] = value.strip()
    return out


def _emit(obj, as_json: bool, printer) -> None:
    if as_json:
        print(json.dumps(obj.to_dict(), indent=2))
    else:
        printer(obj)


def _handle_aws_error(e: Exception) -> int:
    msg = str(e)
    if "not enabled" in msg or "DataUnavailable" in msg or "AccessDenied" in msg:
        print(f"[error] Cost Explorer call failed: {msg}")
        print("        Ensure Cost Explorer is enabled and the principal has ce:Get* permissions.")
    else:
        print(f"[error] {type(e).__name__}: {msg}")
    return 2


# --------------------------------------------------------------------------- #
# command runners
# --------------------------------------------------------------------------- #
def _run_cost(args) -> int:
    from finops_core import format as fmt
    from finops_core.aws.session import build_session
    from finops_core.config import Config
    from finops_core.cost.explorer import CostExplorer

    if not args.view:
        print("usage: finops cost {summary,by-service,by-account,drilldown,trend,forecast,dimensions}")
        return 1

    cfg = Config.load(getattr(args, "config", None))
    try:
        session = build_session(cfg)
        ce = CostExplorer(session, cfg)
    except Exception as e:  # session/credential resolution
        print(f"[error] could not create AWS session: {e}")
        return 2

    try:
        if args.view == "summary":
            _emit(ce.summary(period=args.period, granularity=args.granularity, metric=args.metric),
                  args.json, fmt.print_summary)
        elif args.view == "by-service":
            _emit(ce.cost_by_service(period=args.period, granularity=args.granularity,
                                     metric=args.metric, top_n=args.top), args.json, fmt.print_breakdown)
        elif args.view == "by-account":
            b = ce.cost_by_account(period=args.period, metric=args.metric, top_n=args.top)
            try:  # enrich account ids with names (Organizations), best-effort
                from finops_core.aws.org import OrgResolver
                names = OrgResolver(session, cfg).name_map()
                for g in b.groups:
                    if names.get(g.key) and names[g.key] != g.key:
                        g.key = f"{g.key} ({names[g.key]})"
            except Exception:
                pass
            _emit(b, args.json, fmt.print_breakdown)
        elif args.view == "drilldown":
            _emit(ce.drill_down(args.by, _parse_filters(args.filter), period=args.period,
                                granularity=args.granularity, metric=args.metric, top_n=args.top),
                  args.json, fmt.print_breakdown)
        elif args.view == "trend":
            _emit(ce.trend(months=args.months, metric=args.metric), args.json, fmt.print_summary)
        elif args.view == "forecast":
            _emit(ce.forecast(horizon=args.horizon, metric=args.metric, granularity=args.granularity),
                  args.json, fmt.print_forecast)
        elif args.view == "dimensions":
            r = ce.dimension_values(args.dimension, period=args.period)
            print(json.dumps(r.to_dict(), indent=2) if args.json else "\n".join(r.values) or "(none)")
        else:
            print(f"unknown cost view: {args.view}")
            return 1
    except Exception as e:
        return _handle_aws_error(e)
    return 0


def _run_optimize(args) -> int:
    from dataclasses import asdict

    from finops_core import format as fmt
    from finops_core.aws.session import build_session
    from finops_core.config import Config
    from finops_core.optimize.engine import Optimizer

    if not args.view:
        print("usage: finops optimize {summary,rightsizing,compute-optimizer,"
              "savings-plans,reservations,hub,trusted-advisor}")
        return 1
    cfg = Config.load(getattr(args, "config", None))
    try:
        opt = Optimizer(build_session(cfg), cfg)
    except Exception as e:
        print(f"[error] could not create AWS session: {e}")
        return 2

    if args.view == "summary":
        report = opt.all_recommendations()
        print(json.dumps(report.to_dict(), indent=2)) if args.json else fmt.print_optimization(report)
        return 0

    method = {
        "rightsizing": opt.rightsizing, "compute-optimizer": opt.compute_optimizer,
        "savings-plans": opt.savings_plans, "reservations": opt.reservations,
        "hub": opt.cost_optimization_hub, "trusted-advisor": opt.trusted_advisor_cost,
    }[args.view]
    recs, notes = method()
    if args.json:
        print(json.dumps({"recommendations": [asdict(r) for r in recs], "notes": notes}, indent=2))
    else:
        fmt.print_recommendations(recs, notes)
    return 0


def _run_anomaly(args) -> int:
    from finops_core import format as fmt
    from finops_core.anomaly.engine import AnomalyEngine
    from finops_core.aws.session import build_session
    from finops_core.config import Config
    from finops_core.cost.explorer import CostExplorer

    if not args.view:
        print("usage: finops anomaly {anomalies,budgets,forecast-vs-budget}")
        return 1
    cfg = Config.load(getattr(args, "config", None))
    try:
        session = build_session(cfg)
        eng = AnomalyEngine(session, cfg)
    except Exception as e:
        print(f"[error] could not create AWS session: {e}")
        return 2

    if args.view == "anomalies":
        rep = eng.anomalies(period=args.period)
        print(json.dumps(rep.to_dict(), indent=2)) if args.json else fmt.print_anomalies(rep)
    elif args.view == "budgets":
        rep = eng.budgets()
        print(json.dumps(rep.to_dict(), indent=2)) if args.json else fmt.print_budgets(rep)
    else:  # forecast-vs-budget
        fc = CostExplorer(session, cfg).forecast(horizon="eom")
        rep = eng.budgets()
        if args.json:
            print(json.dumps({"forecast_eom": fc.total, "budgets": rep.to_dict()}, indent=2))
        else:
            print(f"\nForecast EOM: {fmt.money(fc.total, fc.currency)}")
            fmt.print_budgets(rep)
    return 0


def _parse_kv(pairs: list) -> dict:
    out = {}
    for raw in pairs:
        if "=" in raw:
            k, v = raw.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def _run_fix(args) -> int:
    from finops_core.config import Config
    from finops_core.remediation.artifacts import generate_artifact

    cfg = Config.load(args.config)
    from finops_core.modes import can_generate_artifacts
    if not can_generate_artifacts(cfg.mode):
        print("[error] artifact generation needs artifacts or guarded_write mode "
              f"(current: {cfg.mode})")
        return 2
    if args.finding_json:
        finding = json.loads(args.finding_json)
    else:
        finding = {"action": args.action, "resource_id": args.resource_id,
                   "region": args.region, "title": args.title}
    art = generate_artifact(finding, args.format)
    print(f"# {art.filename} ({art.format}) — {art.description}\n{art.content}")
    return 0


def _run_action(args) -> int:
    from finops_core.config import Config
    from finops_core.remediation.actions import ModeError, RemediationEngine

    cfg = Config.load(getattr(args, "config", None))
    eng = RemediationEngine(cfg)
    op = getattr(args, "op", None)
    if not op:
        print("usage: finops action {list,preview,apply}")
        return 1
    if op == "list":
        for a in eng.list_actions():
            print(f"  {a.action_id:30s} [{a.risk:6s}] {a.title}")
        note = "" if cfg.mode == "guarded_write" else "  (set FINOPS_MODE=guarded_write to preview/apply)"
        print(f"\nmode: {cfg.mode}{note}")
        return 0
    try:
        if op == "preview":
            spec = eng.preview(args.action_id, _parse_kv(args.param))
            print(f"action: {spec.action_id}  [risk={spec.risk}]\nwould: {spec.preview}\n")
            print("To apply (single-use token):")
            print(f"  finops action apply {spec.action_id} --token {spec.confirmation_token}")
            return 0
        if op == "apply":
            res = eng.apply(args.action_id, args.token, _parse_kv(args.param) or None)
            print(f"[{res.status}] {res.detail}"
                  + (f"  (audit {res.audit_id})" if res.audit_id else ""))
            return 0 if res.status == "applied" else 2
    except ModeError as e:
        print(f"[error] {e}")
        return 2
    except Exception as e:
        print(f"[error] {type(e).__name__}: {e}")
        return 2
    return 1


def _result_text(result) -> str:
    """Extract plain text from a Strands AgentResult / A2A result."""
    msg = getattr(result, "message", None)
    if isinstance(msg, dict):
        parts = [p.get("text", "") for p in msg.get("content", []) if isinstance(p, dict)]
        if any(parts):
            return "".join(parts).strip()
    return str(result).strip()


def _run_ask(args) -> int:
    # Remote: call a distributed A2A agent (orchestrator or a specialist)
    if args.remote:
        try:
            from strands.agent.a2a_agent import A2AAgent
        except ImportError:
            print("[error] remote calls need the A2A extra: pip install 'strands-agents[a2a]'")
            return 2
        try:
            result = A2AAgent(endpoint=args.remote)(args.question)
        except Exception as e:
            print(f"[error] remote A2A call to {args.remote} failed: {e}")
            return 2
        print(_result_text(result))
        return 0

    # Local: build the Cost-Analysis agent in-process
    from finops_core.aws.session import build_session
    from finops_core.config import Config

    cfg = Config.load(args.config)
    try:
        from finops_core.agents.cost import build_cost_agent
        # callback_handler=None: suppress token streaming so we print the answer once
        agent = build_cost_agent(build_session(cfg), cfg, callback_handler=None,
                                 skills=getattr(args, "skills", None),
                                 memory=getattr(args, "memory", None),
                                 conversation=getattr(args, "summarize", None))
    except ImportError:
        print("[error] the agent requires Strands. Install with: pip install -e '.[agent]'")
        return 2
    except Exception as e:
        print(f"[error] could not build agent: {e}")
        return 2

    result = agent(args.question)
    print(_result_text(result))
    try:
        from finops_core.models.router import ModelRouter
        from finops_core.pricing import usage_summary
        usage = getattr(getattr(result, "metrics", None), "accumulated_usage", None)
        if usage:
            u = usage_summary(ModelRouter(cfg).model_id("cost"), dict(usage))
            from finops_core.telemetry import record_llm_usage
            record_llm_usage(u)  # OTEL: token + estimated-$ metrics
            print(f"\n[tokens in {u['input_tokens']} out {u['output_tokens']} "
                  f"cacheRead {u['cache_read_tokens']} · est ${u['estimated_usd']}]")
    except Exception:
        pass
    return 0


# --------------------------------------------------------------------------- #
# entrypoint
# --------------------------------------------------------------------------- #
def _init_telemetry(args, cmd: str) -> None:
    """Best-effort OTEL bootstrap; never let observability setup break a CLI command."""
    try:
        from finops_core.config import Config
        from finops_core.telemetry import setup_telemetry
        cfg = Config.load(getattr(args, "config", None))
        if cmd == "serve":
            service, console = f"finops-{getattr(args, 'service', 'service')}", True
        else:
            service, console = "finops-cli", False
        setup_telemetry(cfg, service, default_console=console)
    except Exception:
        pass


def main(argv: Optional[list] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    cmd = args.cmd or "preflight"

    # OpenTelemetry: long-running servers emit to console when no collector endpoint is set; a
    # one-shot CLI command stays quiet (no exporter) unless an endpoint is configured.
    _init_telemetry(args, cmd)

    if cmd == "preflight":
        from finops_core.preflight import run_preflight
        return run_preflight(args.config)
    if cmd == "whoami":
        from finops_core.aws.identity import get_caller_identity
        from finops_core.aws.session import build_session
        from finops_core.config import Config
        print(json.dumps(get_caller_identity(build_session(Config.load(args.config))), indent=2))
        return 0
    if cmd == "config":
        from finops_core.config import Config
        print(json.dumps(Config.load(args.config).redacted(), indent=2))
        return 0
    if cmd == "cost":
        return _run_cost(args)
    if cmd == "ask":
        return _run_ask(args)
    if cmd == "accuracy":
        from finops_core.accuracy import reconcile
        from finops_core.aws.session import build_session
        from finops_core.config import Config
        from finops_core.observe import ApiMeter
        cfg = Config.load(args.config)
        session = build_session(cfg)
        meter = ApiMeter().instrument(session)
        r = reconcile(session, cfg, period=args.period)
        if args.json:
            print(json.dumps({**r, "meter": meter.summary()}, indent=2))
        else:
            m = meter.summary()
            print(f"accuracy {'PASS' if r['ok'] else 'FAIL'}: by-service ${r['by_service_total']} "
                  f"vs raw CE ${r['raw_ce_total']}  (Δ ${r['delta']}, tol ${r['tolerance']})")
            print(f"AWS API calls: {m['api_calls']} (CE requests {m['ce_requests']} "
                  f"≈ ${m['estimated_ce_cost_usd']})")
        return 0 if r["ok"] else 2
    if cmd == "digest":
        from finops_core.aws.session import build_session
        from finops_core.config import Config
        from finops_core.workflow.digest import build_digest
        cfg = Config.load(args.config)
        session = build_session(cfg)
        report = build_digest(cfg, session, fmt=args.format, with_narrative=args.narrative)
        if args.deliver:
            from finops_core.workflow.delivery import deliver
            targets = [t.strip() for t in args.deliver.split(",") if t.strip()]
            results = deliver(report, args.format, targets, cfg, session, out=args.out)
            print(f"delivered: {results}")
        else:
            print(report)
        return 0
    if cmd == "route":
        from finops_core.aws.session import build_session
        from finops_core.config import Config
        from finops_core.router import IntentRouter
        cfg = Config.load(args.config)
        try:
            router = IntentRouter(cfg, build_session(cfg))
            intent, answer = router.answer(args.question)
        except ImportError:
            print("[error] routing needs Strands: pip install -e '.[agent]'")
            return 2
        print(f"[routed to: {intent}]\n{answer}")
        if router.last_usage:
            u = router.last_usage
            tools = f" · tools {u['tools']['tool_calls']}" if u.get("tools") else ""
            print(f"\n[tokens in {u['input_tokens']} out {u['output_tokens']} "
                  f"cacheRead {u['cache_read_tokens']} · est ${u['estimated_usd']}{tools}]")
        return 0
    if cmd == "fix":
        return _run_fix(args)
    if cmd == "action":
        return _run_action(args)
    if cmd == "optimize":
        return _run_optimize(args)
    if cmd == "org":
        from finops_core.aws.org import OrgResolver
        from finops_core.aws.session import build_session
        from finops_core.config import Config
        cfg = Config.load(getattr(args, "config", None))
        data = OrgResolver(build_session(cfg), cfg).list_accounts()
        if getattr(args, "json", False):
            print(json.dumps(data, indent=2))
        else:
            print(f"accounts ({'organization' if data['is_org'] else 'single-account'}):")
            for a in data["accounts"]:
                print(f"  {a['id']}  {a['name']}  [{a.get('status', '')}]")
            if data["note"]:
                print(f"  note: {data['note']}")
        return 0
    if cmd == "anomaly":
        return _run_anomaly(args)
    if cmd == "serve":
        servers = {
            "cost-tools": "finops_core.mcp_servers.cost_server",
            "cost-agent": "finops_core.services.cost_agent_server",
            "orchestrator": "finops_core.services.orchestrator_server",
            "optimize-tools": "finops_core.mcp_servers.optimize_server",
            "optimize-agent": "finops_core.services.optimize_agent_server",
            "anomaly-tools": "finops_core.mcp_servers.anomaly_server",
            "anomaly-agent": "finops_core.services.anomaly_agent_server",
        }
        import importlib
        importlib.import_module(servers[args.service]).main()
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
