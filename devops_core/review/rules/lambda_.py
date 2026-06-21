"""AWS Lambda best-practice rules — config/sizing + CloudWatch metrics.
Refs: Lambda Operator Guide & Well-Architected Serverless Lens."""
from __future__ import annotations

from devops_core.review.schemas import Finding

_DOC = "https://docs.aws.amazon.com/lambda/latest/operatorguide/"

# Runtimes deprecated or approaching end-of-support on Lambda.
_DEPRECATED_RUNTIMES = {
    "python3.6", "python3.7", "python3.8", "nodejs10.x", "nodejs12.x", "nodejs14.x",
    "nodejs16.x", "ruby2.5", "ruby2.7", "java8", "go1.x", "dotnetcore2.1", "dotnetcore3.1",
    "dotnet5.0", "dotnet6",
}
_SECRET_HINTS = ("PASSWORD", "SECRET", "TOKEN", "APIKEY", "API_KEY", "PRIVATE_KEY", "ACCESS_KEY")


def lambda_findings(config: dict, metrics: dict | None = None) -> list:
    metrics = metrics or {}
    out: list[Finding] = []
    runtime = config.get("Runtime") or ""
    mem = config.get("MemorySize")
    timeout = config.get("Timeout")
    archs = config.get("Architectures") or ["x86_64"]
    tracing = (config.get("TracingConfig") or {}).get("Mode")
    env = (config.get("Environment") or {}).get("Variables") or {}

    if runtime in _DEPRECATED_RUNTIMES:
        out.append(Finding(
            "lambda.runtime.deprecated", "Deprecated/old runtime", "high",
            current=runtime, recommended="a supported runtime (e.g. python3.12, nodejs20.x)",
            rationale="Deprecated runtimes stop receiving security patches and eventually block "
                      "create/update; migrate before end-of-support.",
            category="security", doc_url=_DOC + "runtimes-deprecated.html"))

    if mem == 128:
        out.append(Finding(
            "lambda.memory.default", "Memory left at the 128 MB default", "medium",
            current="128 MB", recommended="right-size with Lambda Power Tuning",
            rationale="CPU/network scale with memory; the default is often both slower and (per "
                      "GB-second billing) not cost-optimal. Tune to the cost/perf sweet spot.",
            category="performance", doc_url=_DOC + "computing-power.html"))

    if archs == ["x86_64"]:
        out.append(Finding(
            "lambda.arch.graviton", "Not using arm64 (Graviton2)", "low",
            current="x86_64", recommended="arm64 where dependencies allow",
            rationale="Graviton2 offers up to ~19% better price-performance vs x86_64 on Lambda.",
            category="cost", doc_url=_DOC + "computing-power.html"))

    if tracing and tracing != "Active":
        out.append(Finding(
            "lambda.tracing.disabled", "X-Ray active tracing off", "low",
            current=tracing, recommended="TracingConfig.Mode = Active",
            rationale="Active tracing gives latency/error breakdowns across the call graph for "
                      "faster debugging.", category="performance", doc_url=_DOC + "monitoring.html"))

    for k in env:
        if any(h in k.upper() for h in _SECRET_HINTS):
            out.append(Finding(
                "lambda.env.plaintext_secret", "Secret-looking plaintext env var", "high",
                current=f"env var {k}", recommended="store in Secrets Manager / SSM Parameter Store",
                rationale="Plaintext secrets in env vars are visible to anyone with "
                          "GetFunctionConfiguration and are logged in IaC/state.",
                category="security", doc_url=_DOC + "security-configuration.html"))
            break

    errors = (metrics.get("Errors") or {}).get("sum")
    if errors and errors > 0:
        out.append(Finding(
            "lambda.errors.present", "Invocation errors in the window", "high",
            current=f"{int(errors)} errors", recommended="0 — investigate logs/DLQ",
            rationale="Errors indicate failing invocations; check CloudWatch Logs and configure an "
                      "on-failure destination/DLQ.", category="reliability",
            doc_url=_DOC + "monitoring.html"))

    throttles = (metrics.get("Throttles") or {}).get("sum")
    if throttles and throttles > 0:
        out.append(Finding(
            "lambda.throttles.present", "Throttled invocations", "high",
            current=f"{int(throttles)} throttles", recommended="raise reserved concurrency / quota",
            rationale="Throttling means demand exceeded available concurrency; tune reserved/"
                      "provisioned concurrency or request a quota increase.", category="reliability",
            doc_url=_DOC + "scaling-concurrency.html"))

    dur_max = (metrics.get("Duration") or {}).get("max")
    if timeout and dur_max and dur_max >= 0.9 * timeout * 1000:
        out.append(Finding(
            "lambda.duration.near_timeout", "Max duration near the configured timeout", "medium",
            current=f"max {int(dur_max)} ms vs timeout {timeout}s",
            recommended="raise timeout or optimize the hot path",
            rationale="Running close to the timeout risks intermittent timeouts under load.",
            category="reliability", doc_url=_DOC + "monitoring.html"))

    return out
