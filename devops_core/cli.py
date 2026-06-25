"""DevOps / estate agent CLI. Phase 1: scan."""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Optional

# Services runnable via `devops serve <name>`: the estate MCP tool server, the agent-as-MCP server
# (`ask` → ask_devops, for IDE clients), and the A2A estate agent.
_SERVERS = {
    "devops-tools": "devops_core.mcp_servers.estate_server",
    "ask": "devops_core.mcp_servers.agent_server",     # MCP: ask_devops (IDE entrypoint)
    "devops-agent": "devops_core.services.estate_agent_server",
}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="devops", description="AWS DevOps / estate agent CLI")
    sub = parser.add_subparsers(dest="cmd")

    sc = sub.add_parser("scan", help="discover the AWS estate (Config / Resource Explorer / Tagging)")
    sc.add_argument("--config", default=None)
    sc.add_argument("--regions", default=None, help="comma list, e.g. eu-west-2,us-east-1 (default: all enabled)")
    sc.add_argument("--source", default="auto",
                    choices=["auto", "config", "resource-explorer", "tagging"])
    sc.add_argument("--org", action="store_true", help="fan out to Organization member accounts (assume-role)")
    sc.add_argument("--role-name", default="OrganizationAccountAccessRole",
                    help="read-only role to assume in member accounts")
    sc.add_argument("--json", action="store_true")
    sc.add_argument("--top", type=int, default=20)

    dg = sub.add_parser("diagram", help="draw the estate as .drawio (AWS icons) + SVG/PNG")
    dg.add_argument("--config", default=None)
    dg.add_argument("--regions", default=None)
    dg.add_argument("--group-by", default="region", choices=["region", "account"])
    dg.add_argument("--out", default="diagrams/estate", help="output path prefix")
    dg.add_argument("--format", default="all", choices=["drawio", "svg", "png", "all"])
    dg.add_argument("--org", action="store_true", help="fan out to member accounts")
    dg.add_argument("--role-name", default="OrganizationAccountAccessRole")

    tp = sub.add_parser("topology", help="draw a region's network topology (.drawio + PNG)")
    tp.add_argument("--region", required=True)
    tp.add_argument("--config", default=None)
    tp.add_argument("--out", default="diagrams/topology")
    tp.add_argument("--format", default="all", choices=["drawio", "png", "all"])

    ak = sub.add_parser("ask", help="ask the DevOps/estate agent a question")
    ak.add_argument("question")
    ak.add_argument("--config", default=None)
    ak.add_argument("--regions", default=None)
    ak.add_argument("--remote", default=None, metavar="URL", help="call a remote A2A devops-agent")
    ak.add_argument("--skills", action=argparse.BooleanOptionalAction, default=None,
                    help="enable/disable agent skills for this question (default: config / FINOPS_SKILLS)")

    rv = sub.add_parser("review", help="review a resource for best-practice optimizations")
    rv.add_argument("service", help="lambda | ec2 | rds | s3 | ... (inferred from an ARN)")
    rv.add_argument("resource_id", help="name, id, or ARN")
    rv.add_argument("--region", default=None)
    rv.add_argument("--config", default=None)
    rv.add_argument("--no-code", action="store_true", help="skip Lambda code analysis")
    rv.add_argument("--json", action="store_true")

    dn = sub.add_parser("diagnose", help="debug a faulty resource (alarms/logs/CloudTrail → cause)")
    dn.add_argument("service", help="lambda | ec2 | rds | ... (inferred from an ARN)")
    dn.add_argument("resource_id", help="name, id, or ARN")
    dn.add_argument("--region", default=None)
    dn.add_argument("--config", default=None)
    dn.add_argument("--mode", default=None, choices=["advisory", "artifacts", "guarded_write"],
                    help="action posture for fix output (default: config/FINOPS_MODE)")
    dn.add_argument("--json", action="store_true")

    sv = sub.add_parser("serve", help="run a distributed DevOps service")
    sv.add_argument("service", choices=list(_SERVERS))
    sv.add_argument("--stdio", action="store_true",
                    help="run the MCP server over stdio (for IDE clients: Claude Code/Cursor/VS Code)")
    return parser


def _run_scan(args) -> int:
    from finops_core.config import Config
    from devops_core.discovery.engine import EstateScanner

    cfg = Config.load(args.config)
    regions = [r.strip() for r in args.regions.split(",")] if args.regions else None
    try:
        est = EstateScanner(cfg=cfg).scan(regions=regions, source=args.source,
                                          fan_out=args.org, role_name=args.role_name)
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
        est = EstateScanner(cfg=cfg).scan(regions=regions, fan_out=args.org, role_name=args.role_name)
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


def _run_topology(args) -> int:
    from pathlib import Path

    from finops_core.aws.session import build_session
    from finops_core.config import Config
    from devops_core.diagram.render import render
    from devops_core.diagram.topology_drawio import build_topology_drawio
    from devops_core.discovery.topology import TopologyScanner

    cfg = Config.load(args.config)
    try:
        topo = TopologyScanner(build_session(cfg), cfg).scan(args.region)
    except Exception as e:
        print(f"[error] topology scan failed: {e}")
        return 2

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    dpath = out.with_suffix(".drawio")
    dpath.write_text(build_topology_drawio(topo))
    written = [str(dpath)]
    if args.format in ("png", "all"):
        png = render(str(dpath), "png")
        if png:
            written.append(png)

    print(f"Topology {args.region}: {len(topo.vpcs)} VPCs, {topo.subnet_count} subnets, "
          f"{topo.instance_count} instances, {len(topo.peerings)} peering")
    for w in written:
        print(f"  wrote {w}")
    for n in topo.notes:
        print(f"  ! {n}")
    return 0


def _run_review(args) -> int:
    from finops_core.config import Config
    from devops_core.review.engine import review_service

    cfg = Config.load(args.config)
    try:
        review = review_service(args.service, args.resource_id, region=args.region, cfg=cfg,
                                include_code=not args.no_code)
    except Exception as e:
        print(f"[error] review failed: {e}")
        return 2

    d = review.to_dict()
    if args.json:
        print(json.dumps(d, indent=2))
        return 0

    print(f"\nReview: {d['service']} · {d['resource_id']}"
          + (f" · {d['region']}" if d['region'] else ""))
    if d["summary"]:
        print("  config: " + ", ".join(f"{k}={v}" for k, v in d["summary"].items() if v is not None))
    print(f"\n{d['finding_count']} finding(s): "
          + ", ".join(f"{n} {sev}" for sev, n in d["by_severity"].items()) or "none")
    for f in d["findings"]:
        print(f"\n  [{f['severity'].upper()}] {f['title']}  ({f['rule_id']})")
        print(f"    now: {f['current']}  →  {f['recommended']}")
        print(f"    why: {f['rationale']}")
        print(f"    doc: {f['doc_url']}")
    for n in d["notes"]:
        print(f"  ! {n}")
    return 0


def _run_diagnose(args) -> int:
    from finops_core.config import Config
    from devops_core.diagnose.engine import diagnose_service

    cfg = Config.load(args.config)
    try:
        diag = diagnose_service(args.service, args.resource_id, region=args.region,
                                mode=args.mode, cfg=cfg)
    except Exception as e:
        print(f"[error] diagnose failed: {e}")
        return 2

    d = diag.to_dict()
    if args.json:
        print(json.dumps(d, indent=2))
        return 0

    print(f"\nDiagnose: {d['service']} · {d['resource_id']}"
          + (f" · {d['region']}" if d['region'] else "") + f"   [posture: {d['mode']}]")
    s = d["signals"]
    print(f"  signals: {len(s.get('alarms', []))} alarm(s), "
          f"{len(s.get('log_errors', []))} error log line(s), "
          f"{len(s.get('recent_changes', []))} recent change(s)")
    if d["healthy"]:
        print("  ✓ no active fault detected")
    for h in d["hypotheses"]:
        print(f"\n  [{h['confidence'].upper()}] {h['cause']}")
        for ev in h["evidence"][:3]:
            print(f"    · {ev}")
        print(f"    fix: {h['fix']}")
        if h.get("fix_command"):
            print(f"    cmd: {h['fix_command']}")
        if h.get("apply"):
            print(f"    ⚠ {h['apply']}")
    for n in d["notes"]:
        print(f"  ! {n}")
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
    from devops_core.tools.diagnose_tool import build_diagnose_tools
    from devops_core.tools.diagram_tool import build_diagram_tools
    from devops_core.tools.estate import build_estate_tools
    from devops_core.tools.review_tool import build_review_tools

    cfg = Config.load(args.config)
    regions = [r.strip() for r in args.regions.split(",")] if args.regions else None
    try:
        session = build_session(cfg)
        idx = EstateIndex(session, cfg, regions=regions)
        tools = (build_estate_tools(index=idx) + build_diagram_tools(session, cfg, index=idx)
                 + build_review_tools(session, cfg) + build_diagnose_tools(session, cfg))
        agent = build_estate_agent(cfg=cfg, session=session, callback_handler=None, tools=tools,
                                   skills=getattr(args, "skills", None))
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
    if args.cmd == "topology":
        return _run_topology(args)
    if args.cmd == "ask":
        return _run_ask(args)
    if args.cmd == "review":
        return _run_review(args)
    if args.cmd == "diagnose":
        return _run_diagnose(args)
    if args.cmd == "serve":
        if getattr(args, "stdio", False):
            os.environ["FINOPS_MCP_TRANSPORT"] = "stdio"  # picked up by run_mcp
        import importlib
        importlib.import_module(_SERVERS[args.service]).main()
        return 0
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
