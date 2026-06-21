"""Fetch & lightly analyze a deployed Lambda's code (zip packages only).

Downloads the deployment package (presigned URL from get_function), extracts in a temp dir, and
runs a few high-signal heuristics aligned with the lambda-performance-audit / lambda-security-audit
skills. Bounded (skips large packages) and graceful (any failure → a note, never raises).
"""
from __future__ import annotations

import io
import re
import tempfile
import urllib.request
import zipfile
from pathlib import Path

from devops_core.review.schemas import Finding

_DOC = "https://docs.aws.amazon.com/lambda/latest/operatorguide/"
_MAX_BYTES = 8 * 1024 * 1024  # don't pull huge packages
_SRC_EXT = (".py", ".js", ".mjs", ".ts")
_AKIA = re.compile(r"AKIA[0-9A-Z]{16}")
_SECRET_LITERAL = re.compile(r"""(?i)(password|secret|api[_-]?key|token)\s*=\s*['"][^'"]{6,}['"]""")
_CLIENT_CALL = re.compile(r"boto3\.(client|resource)\(|new\s+AWS\.|new\s+\w+Client\(")
_HANDLER_DEF = re.compile(r"def\s+(lambda_handler|handler)\b|exports\.handler\s*=")


def analyze_lambda_code(lam_client, name: str, runtime: str) -> tuple[list, list]:
    findings: list[Finding] = []
    notes: list[str] = []
    try:
        meta = lam_client.get_function(FunctionName=name)
    except Exception as e:
        return [], [f"code: get_function failed ({type(e).__name__})"]

    code = meta.get("Code", {})
    size = meta.get("Configuration", {}).get("CodeSize", 0)
    url = code.get("Location")
    if not url:
        return [], ["code: no downloadable package (image or inline)"]
    if size and size > _MAX_BYTES:
        return [], [f"code: package {size // 1024} KB exceeds the {_MAX_BYTES // 1024} KB scan cap"]

    try:
        with urllib.request.urlopen(url, timeout=20) as r:  # presigned, read-only
            raw = r.read(_MAX_BYTES + 1)
        if len(raw) > _MAX_BYTES:
            return [], ["code: package larger than scan cap; skipped"]
        zf = zipfile.ZipFile(io.BytesIO(raw))
    except Exception as e:
        return [], [f"code: download/extract failed ({type(e).__name__})"]

    with tempfile.TemporaryDirectory() as td:
        try:
            zf.extractall(td)
        except Exception as e:
            return [], [f"code: extract failed ({type(e).__name__})"]
        secret_hit = client_in_handler = False
        scanned = 0
        for p in Path(td).rglob("*"):
            if p.suffix.lower() not in _SRC_EXT or not p.is_file():
                continue
            try:
                text = p.read_text(errors="ignore")
            except Exception:
                continue
            scanned += 1
            if not secret_hit and (_AKIA.search(text) or _SECRET_LITERAL.search(text)):
                secret_hit = True
            if not client_in_handler:
                m = _HANDLER_DEF.search(text)
                if m and _CLIENT_CALL.search(text[m.start():]):
                    client_in_handler = True

        if not scanned:
            notes.append("code: no readable source files in package")
        if secret_hit:
            findings.append(Finding(
                "lambda.code.hardcoded_secret", "Hardcoded credential/secret in source", "critical",
                current="literal secret/AWS key in code", recommended="Secrets Manager / env + KMS",
                rationale="Hardcoded secrets leak via the package, logs, and source control; rotate "
                          "and move to a secrets store.", category="code",
                doc_url=_DOC + "security-configuration.html"))
        if client_in_handler:
            findings.append(Finding(
                "lambda.code.client_in_handler", "SDK client created inside the handler", "medium",
                current="client/resource constructed per invocation",
                recommended="initialize SDK clients at module scope",
                rationale="Module-scope clients are reused across warm invocations, cutting latency "
                          "and connection churn.", category="code",
                doc_url=_DOC + "static-initialization.html"))
        notes.append(f"code: scanned {scanned} source file(s) "
                     "(deep code/security audit → lambda-performance-audit / lambda-security-audit)")
    return findings, notes
