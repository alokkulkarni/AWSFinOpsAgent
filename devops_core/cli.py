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


def main(argv: Optional[list] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.cmd == "scan":
        return _run_scan(args)
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
