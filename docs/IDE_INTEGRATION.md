# IDE integration (Claude Code · Cursor · VS Code) via MCP

The FinOps and DevSecOps agents plug into any MCP-capable editor — **Claude Code**, **Cursor**,
and **VS Code** (Copilot agent mode / Continue) — over the **Model Context Protocol (MCP)**. No
Streamlit needed: the editor's own model calls our servers as tools.

## Two surfaces (both shipped)

| Surface | Server | Tool(s) | Use when |
|---|---|---|---|
| **Agents** (high-level) | `finops serve ask` · `devops serve ask` | `ask_finops(question)` · `ask_devops(question)` | You want *the agent* — routed specialist + steering + skills + memory. One call → an analysis. |
| **Tools** (granular) | `finops serve cost-tools` · `devops serve devops-tools` (+ `optimize-tools`, `anomaly-tools`) | `get_cost_by_service`, `drill_down`, `get_estate_summary`, … | You want the editor's model to orchestrate individual deterministic tools. |

Both return **exact** figures (same deterministic tool layer as the dashboard/API — numbers never
come from an LLM). Start with the **agent** servers; add the tool servers when you want the IDE
model to drive the drill-down itself.

## Transport: stdio

For local IDE use the servers run over **stdio** (the editor spawns the process; no ports, nothing
always-on) via the `--stdio` flag. The MCP protocol owns stdout, so startup banners go to stderr.
(The same servers still run over Streamable HTTP without `--stdio` for the Docker stack.)

## Prerequisites

```bash
pip install -e ".[agent]"     # puts `finops` and `devops` on PATH; the IDE configs call them
```
The committed configs invoke `finops` / `devops`, so the **project virtualenv must be active** in
the environment that launches your editor (or replace `command` with an absolute path to the venv's
`finops`/`devops`). Servers default to `FINOPS_MODE=advisory` (read-only); the `ReadOnlyGuard`
blocks writes unless you opt into `guarded_write`.

## Credentials (already wired)

The configs are **pre-wired to dedicated, least-privilege profiles** — no per-account editing
needed. Run the two setup scripts once (with credentials that can manage IAM); each creates a
read-only IAM user + local `~/.aws` profile:

```bash
./scripts/setup_finops_iam.sh    # → profile `finops`  (billing/Cost Explorer read-only + Bedrock)
./scripts/setup_devops_iam.sh    # → profile `devops`  (estate discovery read-only + Bedrock)
```
After that the FinOps servers use `AWS_PROFILE=finops` and the DevSecOps servers use
`AWS_PROFILE=devops` (set in each server's `env`), so opening the repo in any editor "just works".
Adjust `AWS_REGION` if needed. (Already have your own read-only profiles? Just change the
`AWS_PROFILE` values.) For **org-wide cross-account** estate scans, use `scripts/setup_devops_role.sh`
(the `DevOpsReadOnly` assume-role) and point the devops server at it with
`FINOPS_AWS_AUTH=assume_role` + `FINOPS_ROLE_ARN=...`.

## Claude Code

Checked in at **`.mcp.json`** (project-scoped) — open the repo in Claude Code and approve the
servers. Or add ad-hoc:
```bash
claude mcp add finops-ask -- finops serve ask --stdio
claude mcp add devops-ask -- devops serve ask --stdio
```
Then just ask: *"use finops-ask: where is my money going this month?"* You can also add a
`.claude/commands/finops.md` slash command or a subagent that wraps these tools.

HTTP instead (if the Docker stack is already up): `claude mcp add --transport http finops http://localhost:8081/mcp`.

## Cursor

Checked in at **`.cursor/mcp.json`** (same `mcpServers` schema as Claude Code). Cursor →
Settings → MCP shows the servers; toggle on and use them from the agent/composer.

## VS Code (Copilot agent mode)

Checked in at **`.vscode/mcp.json`** (uses the `servers` key + `"type": "stdio"`). Open the file
and click **Start**, or run *MCP: List Servers*. Use the tools from Copilot Chat in **Agent** mode.
(Continue users: add the same `command`/`args`/`env` under `mcpServers` in `~/.continue/config.yaml`.)

## What's registered (both options, out of the box)

All six servers are in every config — **Option B (agents)** + **Option A (tools)**:

| Server | Option | Command | Profile |
|---|---|---|---|
| `finops-ask` | B (agent) | `finops serve ask --stdio` | `finops` |
| `devops-ask` | B (agent) | `devops serve ask --stdio` | `devops` |
| `finops-cost-tools` | A (tools) | `finops serve cost-tools --stdio` | `finops` |
| `finops-optimize-tools` | A (tools) | `finops serve optimize-tools --stdio` | `finops` |
| `finops-anomaly-tools` | A (tools) | `finops serve anomaly-tools --stdio` | `finops` |
| `devops-tools` | A (tools) | `devops serve devops-tools --stdio` | `devops` |

Disable any you don't want by removing its entry. Want fewer processes? Keep just the two
`*-ask` agent servers (Option B) — they cover everything via routing.

## Telemetry in IDE mode

The configs set `FINOPS_TELEMETRY=0` so stdio stays clean and there are no surprise exports. To
trace IDE-driven calls, point at a collector instead of the console:
`"FINOPS_TELEMETRY": "1", "OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:4317"` (never the
console exporter over stdio). See `docs/OBSERVABILITY.md`.

## Troubleshooting

- **`finops: command not found`** — the editor's PATH lacks the venv. Use an absolute path to
  `…/.venv/bin/finops`, or launch the editor from an activated venv.
- **Server starts then exits** — usually AWS credentials/region. Check `finops whoami` /
  `finops preflight` in a terminal with the same `env`.
- **No tools appear** — confirm the editor picked up the file (Claude Code: `/mcp`; VS Code:
  *MCP: List Servers*; Cursor: Settings → MCP) and that you approved the server.
