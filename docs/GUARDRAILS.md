# Bedrock Guardrails (optional)

The agent can run every model call through an [Amazon Bedrock Guardrail](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails.html)
to filter PII and block prompt attacks / denied topics. **Off by default.**

## Enable
```bash
# 1) Create a guardrail (PII anonymize + AWS-secret block + prompt-attack filter):
./scripts/create_finops_guardrail.sh          # prints the guardrailId
# 2) Point the agent at it:
export FINOPS_GUARDRAIL_ID=<id>
export FINOPS_GUARDRAIL_VERSION=DRAFT          # or a published version
# 3) (config alternative) set llm.guardrail_id in config/finops.yaml
make preflight
```
`ModelRouter` then passes `guardrail_id` / `guardrail_version` / `guardrail_trace` to every
`BedrockModel`. With distributed containers, set the env on the agent services and re-up.

## ⚠️ Compliance caveat (from the bedrock skill)
Guardrail PII **masking applies to the API response only** — the original, unmasked content
(including PII) is still written to **CloudWatch Logs** in plain text. For HIPAA/GDPR:
- Encrypt CloudWatch Logs with KMS and restrict access with IAM.
- Set log retention limits; consider Amazon Macie for PII detection.

## Config keys
| Key | Env | Default |
|---|---|---|
| `llm.guardrail_id` | `FINOPS_GUARDRAIL_ID` | none (disabled) |
| `llm.guardrail_version` | `FINOPS_GUARDRAIL_VERSION` | `DRAFT` |
| `llm.guardrail_trace` | `FINOPS_GUARDRAIL_TRACE` | `enabled` |
