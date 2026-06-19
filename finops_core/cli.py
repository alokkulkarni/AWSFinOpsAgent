"""FinOps Agent CLI. Phase-0 commands: preflight, whoami, config."""
from __future__ import annotations

import argparse
import json
import sys
from typing import Optional


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(prog="finops", description="AWS FinOps Agent CLI")
    sub = parser.add_subparsers(dest="cmd")

    for name, help_text in (
        ("preflight", "verify AWS identity (STS) + Bedrock model availability"),
        ("whoami", "print caller identity as JSON"),
        ("config", "print effective (redacted) configuration"),
    ):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("--config", default=None, help="path to finops.yaml")

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

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
