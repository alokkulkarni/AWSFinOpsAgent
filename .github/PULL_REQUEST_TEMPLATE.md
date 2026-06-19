## Summary
<!-- What does this PR do and why? Link the phase/issue. -->

## Phase / scope
<!-- e.g. Phase 1 — Cost core -->

## Checklist
- [ ] Branch is not `main`; PR targets `main`
- [ ] **No secrets committed** (`.env`, `~/.aws`, keys, tokens, real account IDs, billing data)
- [ ] Read-only by default; any write action is allowlisted, dry-run previewed, human-confirmed
- [ ] Numbers verified against Cost Explorer / CUR (no LLM-estimated figures)
- [ ] `make fmt` and `make test` pass
- [ ] `make preflight` passes (if AWS/Bedrock touched)
- [ ] No hardcoded Bedrock model IDs (use `config/models.yaml`)
- [ ] `SPEC.md` updated if scope/design changed

## How tested
<!-- Commands run, evidence, screenshots. -->
