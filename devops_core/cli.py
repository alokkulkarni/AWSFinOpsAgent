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


def main(argv: Optional[list] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.cmd == "scan":
        return _run_scan(args)
    if args.cmd == "diagram":
        return _run_diagram(args)
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
