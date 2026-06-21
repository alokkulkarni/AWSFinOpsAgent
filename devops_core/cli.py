"""DevOps / estate agent CLI. Phase 1: scan."""
from __future__ import annotations

import argparse
import json
import sys
from typing import Optional


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="devops", description="AWS DevOps / estate agent CLI")
    sub = parser.add_subparsers(dest="cmd")

    sc = sub.add_parser("scan", help="discover the AWS estate (Config / Resource Explorer / Tagging)")
    sc.add_argument("--config", default=None)
    sc.add_argument("--regions", default=None, help="comma list, e.g. eu-west-2,us-east-1 (default: all enabled)")
    sc.add_argument("--source", default="auto",
                    choices=["auto", "config", "resource-explorer", "tagging"])
    sc.add_argument("--json", action="store_true")
    sc.add_argument("--top", type=int, default=20)

    dg = sub.add_parser("diagram", help="draw the estate as .drawio (AWS icons) + SVG/PNG")
    dg.add_argument("--config", default=None)
    dg.add_argument("--regions", default=None)
    dg.add_argument("--group-by", default="region", choices=["region", "account"])
    dg.add_argument("--out", default="diagrams/estate", help="output path prefix")
    dg.add_argument("--format", default="all", choices=["drawio", "svg", "png", "all"])

    ak = sub.add_parser("ask", help="ask the DevOps/estate agent a question")
    ak.add_argument("question")
    ak.add_argument("--config", default=None)
    ak.add_argument("--regions", default=None)
    ak.add_argument("--remote", default=None, metavar="URL", help="call a remote A2A devops-agent")

    sv = sub.add_parser("serve", help="run a distributed DevOps service")
    sv.add_argument("service", choices=["devops-tools", "devops-agent"])
    return parser


def _run_scan(args) -> int:
    from finops_core.config import Config
    from devops_core.discovery.engine import EstateScanner

    cfg = Config.load(args.config)
    regions = [r.strip() for r in args.regions.split(",")] if args.regions else None
    try:
        est = EstateScanner(cfg=cfg).scan(regions=regions, source=args.source)
    except Exception as e:
        print(f"[error] estate scan failed: {e}")
        return 2

    if args.json:
        print(json.dumps(est.to_dict(), indent=2))
        return 0

    print(f"\nEstate: {len(est.resources)} resources · {len(est.accounts)} account(s) · "
          f"{len(est.regions)} region(s)   [source: {est.source}]")
    print("\nby service:")
    for svc, n in list(est.counts("service").items())[:args.top]:
        print(f"  {svc:<28} {n}")
    print("\nby region:")
    for reg, n in list(est.counts("region").items())[:args.top]:
        print(f"  {reg:<28} {n}")
    if len(est.accounts) > 1:
        print("\nby account:")
        for acct, n in est.counts("account").items():
            print(f"  {acct:<28} {n}")
    for note in est.notes:
        print(f"  ! {note}")
    return 0


def _run_diagram(args) -> int:
    from pathlib import Path

    from finops_core.config import Config
    from devops_core.diagram.drawio import build_drawio
    from devops_core.diagram.render import render
    from devops_core.diagram.svg import build_svg
    from devops_core.discovery.engine import EstateScanner

    cfg = Config.load(args.config)
    regions = [r.strip() for r in args.regions.split(",")] if args.regions else None
    try:
        est = EstateScanner(cfg=cfg).scan(regions=regions)
    except Exception as e:
        print(f"[error] estate scan failed: {e}")
        return 2

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    written = []
    if args.format in ("drawio", "png", "all"):
        dpath = out.with_suffix(".drawio")
        dpath.write_text(build_drawio(est, group_by=args.group_by))
        written.append(str(dpath))
        if args.format in ("png", "all"):
            png = render(str(dpath), "png")
            if png:
                written.append(png)
            elif args.format == "png":
                print("[warn] draw.io CLI not found — wrote .drawio only (install draw.io or use --format svg)")
    if args.format in ("svg", "all"):
        spath = out.with_suffix(".svg")
        spath.write_text(build_svg(est, group_by=args.group_by))
        written.append(str(spath))

    print(f"Estate: {len(est.resources)} resources, {len(est.regions)} region(s) [{est.source}]")
    for w in written:
        print(f"  wrote {w}")
    return 0


def _result_text(result) -> str:
    msg = getattr(result, "message", None)
    if isinstance(msg, dict):
        parts = [p.get("text", "") for p in msg.get("content", []) if isinstance(p, dict)]
        if any(parts):
            return "".join(parts).strip()
    return str(result).strip()


def _run_ask(args) -> int:
    if args.remote:
        try:
            from strands.agent.a2a_agent import A2AAgent
        except ImportError:
            print("[error] remote needs the A2A extra: pip install 'strands-agents[a2a]'")
            return 2
        print(_result_text(A2AAgent(endpoint=args.remote)(args.question)))
        return 0
    from finops_core.aws.session import build_session
    from finops_core.config import Config
    from devops_core.agents.estate import build_estate_agent
    from devops_core.discovery.index import EstateIndex
    from devops_core.tools.estate import build_estate_tools

    cfg = Config.load(args.config)
    regions = [r.strip() for r in args.regions.split(",")] if args.regions else None
    try:
        idx = EstateIndex(build_session(cfg), cfg, regions=regions)
        agent = build_estate_agent(cfg=cfg, callback_handler=None, tools=build_estate_tools(index=idx))
    except ImportError:
        print("[error] the agent needs Strands: pip install -e '.[agent]'")
        return 2
    print(_result_text(agent(args.question)))
    return 0


def main(argv: Optional[list] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.cmd == "scan":
        return _run_scan(args)
    if args.cmd == "diagram":
        return _run_diagram(args)
    if args.cmd == "ask":
        return _run_ask(args)
    if args.cmd == "serve":
        import importlib
        mod = {"devops-tools": "devops_core.mcp_servers.estate_server",
               "devops-agent": "devops_core.services.estate_agent_server"}[args.service]
        importlib.import_module(mod).main()
        return 0
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
