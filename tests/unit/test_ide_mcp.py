"""IDE integration over MCP: the stdio transport switch, the `serve ask` agent-MCP servers
(ask_finops / ask_devops), and the checked-in IDE config files (Claude Code / Cursor / VS Code).
"""
import asyncio
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


# --- stdio transport switch ------------------------------------------------
class _FakeMCP:
    def __init__(self):
        self.ran = None

        class _S:
            host, port, streamable_http_path = "127.0.0.1", 8081, "/mcp"

        self.settings = _S()

    def run(self, transport):
        self.ran = transport


def test_run_mcp_defaults_to_streamable_http(monkeypatch, capsys):
    monkeypatch.delenv("FINOPS_MCP_TRANSPORT", raising=False)
    from finops_core.mcp_servers._runtime import run_mcp

    m = _FakeMCP()
    run_mcp(m, "cost-tools")
    assert m.ran == "streamable-http"


def test_run_mcp_stdio_from_env_and_keeps_stdout_clean(monkeypatch, capsys):
    """stdio uses stdout for the MCP protocol — the banner MUST go to stderr, not stdout."""
    monkeypatch.setenv("FINOPS_MCP_TRANSPORT", "stdio")
    from finops_core.mcp_servers._runtime import run_mcp

    m = _FakeMCP()
    run_mcp(m, "cost-tools")
    out = capsys.readouterr()
    assert m.ran == "stdio"
    assert out.out == ""          # nothing on stdout (would corrupt the stdio protocol)
    assert "stdio" in out.err     # banner on stderr is fine


# --- CLI: `serve ask` + `--stdio` ------------------------------------------
def test_finops_serve_has_ask_and_stdio():
    from finops_core.cli import _SERVERS, _build_parser

    assert _SERVERS["ask"] == "finops_core.mcp_servers.agent_server"
    p = _build_parser()
    args = p.parse_args(["serve", "ask", "--stdio"])
    assert args.service == "ask" and args.stdio is True
    assert p.parse_args(["serve", "cost-tools"]).stdio is False


def test_devops_serve_has_ask_and_stdio():
    from devops_core.cli import _SERVERS, _build_parser

    assert _SERVERS["ask"] == "devops_core.mcp_servers.agent_server"
    p = _build_parser()
    args = p.parse_args(["serve", "ask", "--stdio"])
    assert args.service == "ask" and args.stdio is True


# --- agent-MCP servers register the ask_* tools (import-safe, no AWS) -------
def _tool_names(mcp):
    return {t.name for t in asyncio.run(mcp.list_tools())}


def test_finops_agent_server_exposes_ask_finops():
    from finops_core.mcp_servers import agent_server

    assert "ask_finops" in _tool_names(agent_server.mcp)


def test_devops_agent_server_exposes_ask_devops():
    from devops_core.mcp_servers import agent_server

    assert "ask_devops" in _tool_names(agent_server.mcp)


# --- checked-in IDE config files -------------------------------------------
@pytest.mark.parametrize("rel,top_key", [
    (".mcp.json", "mcpServers"),          # Claude Code
    (".cursor/mcp.json", "mcpServers"),   # Cursor
    (".vscode/mcp.json", "servers"),      # VS Code (Copilot agent mode)
])
def test_ide_config_valid_json_with_servers(rel, top_key):
    data = json.loads((REPO / rel).read_text())
    servers = data[top_key]
    assert servers, f"{rel} has no servers"
    # every server entry must launch via stdio (a `command`) — IDEs spawn local servers
    for name, spec in servers.items():
        assert "command" in spec, f"{rel}:{name} missing command"


def test_ide_configs_register_both_agents_and_tools():
    data = json.loads((REPO / ".mcp.json").read_text())["mcpServers"]
    keys = set(data)
    # the agent surface (ask_finops/ask_devops) AND at least one raw tool server
    assert any("finops" in k and "ask" in k for k in keys) or "finops-ask" in keys
    assert any("devops" in k for k in keys)
    # a stdio launch references `serve ... --stdio`
    blob = json.dumps(data)
    assert "--stdio" in blob


def test_ide_configs_use_dedicated_profiles():
    data = json.loads((REPO / ".mcp.json").read_text())["mcpServers"]
    assert data["finops-ask"]["env"]["AWS_PROFILE"] == "finops"
    assert data["devops-ask"]["env"]["AWS_PROFILE"] == "devops"


# --- HTTP / Docker overlay (docker-compose.mcp.yml) ------------------------
def test_http_overlay_publishes_ports_and_ask_servers():
    yaml = pytest.importorskip("yaml")
    overlay = yaml.safe_load((REPO / "docker-compose.mcp.yml").read_text())
    svcs = overlay["services"]

    # the tool servers are published to the host (so localhost:<port>/mcp is reachable)
    for name, port in [("cost-tools", "8081"), ("optimize-tools", "8082"),
                       ("anomaly-tools", "8083"), ("devops-tools", "8085")]:
        assert any(str(port) in str(p) for p in svcs[name]["ports"]), name

    # the agent (ask) MCP servers run over HTTP, with the right command + profile
    assert svcs["finops-ask"]["command"] == ["serve", "ask"]
    assert svcs["finops-ask"]["environment"]["AWS_PROFILE"] == "finops"
    assert any("8090" in str(p) for p in svcs["finops-ask"]["ports"])
    assert svcs["devops-ask"]["command"] == ["serve", "ask"]
    assert svcs["devops-ask"]["entrypoint"] == ["devops"]
    assert svcs["devops-ask"]["environment"]["AWS_PROFILE"] == "devops"
    assert any("8095" in str(p) for p in svcs["devops-ask"]["ports"])

    # finops tool servers use the finops profile; devops the devops profile
    assert svcs["cost-tools"]["environment"]["AWS_PROFILE"] == "finops"
    assert svcs["devops-tools"]["environment"]["AWS_PROFILE"] == "devops"
