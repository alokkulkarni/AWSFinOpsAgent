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

    # ask (agent) — local in-process, or a remote A2A endpoint (distributed)
    ask = sub.add_parser("ask", help="ask the Cost-Analysis agent (local) or a remote A2A agent")
    ask.add_argument("question")
    ask.add_argument("--config", default=None)
    ask.add_argument("--remote", default=None,
                     metavar="URL", help="call a remote A2A agent (e.g. http://localhost:9000)")

    # serve — run a distributed service (used as the container command)
    srv = sub.add_parser("serve", help="run a distributed service (MCP tool / A2A agent server)")
    srv.add_argument("service", choices=["cost-tools", "cost-agent", "orchestrator",
                                         "optimize-tools", "optimize-agent"])

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
        ce = CostExplorer(build_session(cfg), cfg)
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
            _emit(ce.cost_by_account(period=args.period, metric=args.metric, top_n=args.top),
                  args.json, fmt.print_breakdown)
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
        agent = build_cost_agent(build_session(cfg), cfg, callback_handler=None)
    except ImportError:
        print("[error] the agent requires Strands. Install with: pip install -e '.[agent]'")
        return 2
    except Exception as e:
        print(f"[error] could not build agent: {e}")
        return 2

    print(_result_text(agent(args.question)))
    return 0


# --------------------------------------------------------------------------- #
# entrypoint
# --------------------------------------------------------------------------- #
def main(argv: Optional[list] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    cmd = args.cmd or "preflight"

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
    if cmd == "optimize":
        return _run_optimize(args)
    if cmd == "serve":
        servers = {
            "cost-tools": "finops_core.mcp_servers.cost_server",
            "cost-agent": "finops_core.services.cost_agent_server",
            "orchestrator": "finops_core.services.orchestrator_server",
            "optimize-tools": "finops_core.mcp_servers.optimize_server",
            "optimize-agent": "finops_core.services.optimize_agent_server",
        }
        import importlib
        importlib.import_module(servers[args.service]).main()
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
