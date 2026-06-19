"""Phase-0 smoke check: resolve AWS identity (STS) and verify Bedrock model availability.

Exit codes: 0 = identity OK (model warnings allowed), 2 = identity could not be resolved.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from finops_core.aws.identity import get_caller_identity, redact_account, redact_arn
from finops_core.aws.session import build_session
from finops_core.config import Config
from finops_core.models.router import ModelRouter


def run_preflight(config_path: Optional[Path] = None) -> int:
    cfg = Config.load(config_path)
    redact = cfg.guardrails.redact_account_ids

    print("== AWS FinOps Agent — preflight ==")
    print(f"mode        : {cfg.mode}")
    profile_note = f" (profile={cfg.aws.profile})" if cfg.aws.auth == "profile" else ""
    print(f"aws.auth    : {cfg.aws.auth}{profile_note}")
    print(f"region      : {cfg.aws.region}   ce_region: {cfg.aws.ce_region}   org_mode: {cfg.aws.org_mode}")
    print(f"llm         : {cfg.llm.provider} @ {cfg.llm.region}")

    # 1) credentials / identity (the Phase-0 exit criterion) -------------
    try:
        session = build_session(cfg)
        ident = get_caller_identity(session)
        print(f"[ok]  account : {redact_account(ident['account'], redact)}")
        print(f"[ok]  arn     : {redact_arn(ident['arn'], redact)}")
    except Exception as e:
        print(f"[FAIL] could not resolve AWS identity: {e}")
        print("       -> check credentials (profile/env/assume_role) and region in .env / config.")
        return 2

    # 2) Bedrock model availability (warn-only) --------------------------
    ok = True
    try:
        report = ModelRouter(cfg, session).preflight()
        print(f"[{'ok' if report.reachable else 'warn'}]  bedrock reachable: {report.reachable}")
        for role, info in report.resolved.items():
            avail = {True: "available", False: "NOT FOUND", None: "unchecked"}[info["available"]]
            print(f"        - {role:13s} {info['id']}  [{avail}]")
        for note in report.notes:
            print(f"        ! {note}")
        if report.reachable and any(v["available"] is False for v in report.resolved.values()):
            ok = False
    except Exception as e:
        print(f"[warn] model preflight skipped: {e}")

    print("== preflight " + ("PASSED ==" if ok else "completed WITH WARNINGS =="))
    return 0  # identity resolved -> smoke test passes (model issues are warnings)
