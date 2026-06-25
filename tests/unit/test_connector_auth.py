"""connector_auth: per-request AWS credential injection for MCP connector mode.

Tests cover:
- Header creds take priority over server-side creds
- Graceful fallback to build_session when headers are absent or incomplete
- cred_key_from_context returns consistent hashed keys for caching
- No real AWS calls are made by any of these helpers
"""
from __future__ import annotations

import hashlib
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers to build fake Context objects
# ---------------------------------------------------------------------------

def _fake_request(headers: dict) -> MagicMock:
    req = MagicMock()
    req.headers = headers
    return req


def _ctx_with_headers(headers: dict) -> MagicMock:
    """FastMCP Context with an HTTP request carrying the given headers."""
    ctx = MagicMock()
    ctx.request_context.request = _fake_request(headers)
    return ctx


def _ctx_no_request() -> MagicMock:
    """FastMCP Context in stdio mode — request_context.request is None."""
    ctx = MagicMock()
    ctx.request_context.request = None
    return ctx


def _ctx_none() -> None:
    """Caller passes ctx=None (e.g., test harness)."""
    return None


# ---------------------------------------------------------------------------
# session_from_context
# ---------------------------------------------------------------------------

class TestSessionFromContext:
    def test_uses_header_creds_when_present(self):
        from finops_core.mcp_servers.connector_auth import session_from_context
        from finops_core.config import Config

        cfg = Config.load()
        ctx = _ctx_with_headers({
            "x-aws-access-key-id": "AKIA_TEST",
            "x-aws-secret-access-key": "secret",
            "x-aws-session-token": "token",
            "x-aws-region": "eu-west-1",
        })

        with patch("boto3.Session") as mock_session_cls:
            session_from_context(ctx, cfg)

        mock_session_cls.assert_called_once_with(
            aws_access_key_id="AKIA_TEST",
            aws_secret_access_key="secret",
            aws_session_token="token",
            region_name="eu-west-1",
        )

    def test_region_defaults_to_cfg_when_header_absent(self):
        from finops_core.mcp_servers.connector_auth import session_from_context
        from finops_core.config import Config

        cfg = Config.load()
        ctx = _ctx_with_headers({
            "x-aws-access-key-id": "AKIA_TEST",
            "x-aws-secret-access-key": "secret",
        })

        with patch("boto3.Session") as mock_session_cls:
            session_from_context(ctx, cfg)

        call_kwargs = mock_session_cls.call_args.kwargs
        assert call_kwargs["region_name"] == cfg.aws.region

    def test_session_token_is_none_when_header_absent(self):
        from finops_core.mcp_servers.connector_auth import session_from_context
        from finops_core.config import Config

        cfg = Config.load()
        ctx = _ctx_with_headers({
            "x-aws-access-key-id": "AKIA_TEST",
            "x-aws-secret-access-key": "secret",
        })

        with patch("boto3.Session") as mock_session_cls:
            session_from_context(ctx, cfg)

        call_kwargs = mock_session_cls.call_args.kwargs
        assert call_kwargs["aws_session_token"] is None

    def test_falls_back_to_build_session_when_no_request(self):
        """stdio mode: no HTTP request → delegate to build_session."""
        from finops_core.mcp_servers.connector_auth import session_from_context
        from finops_core.config import Config

        cfg = Config.load()
        ctx = _ctx_no_request()

        with patch("finops_core.mcp_servers.connector_auth.build_session") as mock_build:
            mock_build.return_value = MagicMock()
            session_from_context(ctx, cfg)

        mock_build.assert_called_once_with(cfg)

    def test_falls_back_to_build_session_when_ctx_is_none(self):
        """Test harness passes ctx=None → delegate to build_session."""
        from finops_core.mcp_servers.connector_auth import session_from_context
        from finops_core.config import Config

        cfg = Config.load()
        with patch("finops_core.mcp_servers.connector_auth.build_session") as mock_build:
            mock_build.return_value = MagicMock()
            session_from_context(None, cfg)

        mock_build.assert_called_once_with(cfg)

    def test_falls_back_when_only_access_key_present(self):
        """Incomplete headers (no secret) → fall back to server-side creds."""
        from finops_core.mcp_servers.connector_auth import session_from_context
        from finops_core.config import Config

        cfg = Config.load()
        ctx = _ctx_with_headers({"x-aws-access-key-id": "AKIA_TEST"})

        with patch("finops_core.mcp_servers.connector_auth.build_session") as mock_build:
            mock_build.return_value = MagicMock()
            session_from_context(ctx, cfg)

        mock_build.assert_called_once_with(cfg)

    def test_does_not_call_build_session_when_header_creds_present(self):
        """Header creds present → build_session must NOT be called."""
        from finops_core.mcp_servers.connector_auth import session_from_context
        from finops_core.config import Config

        cfg = Config.load()
        ctx = _ctx_with_headers({
            "x-aws-access-key-id": "AKIA_TEST",
            "x-aws-secret-access-key": "secret",
        })

        with patch("finops_core.mcp_servers.connector_auth.build_session") as mock_build:
            with patch("boto3.Session"):
                session_from_context(ctx, cfg)

        mock_build.assert_not_called()


# ---------------------------------------------------------------------------
# cred_key_from_context
# ---------------------------------------------------------------------------

class TestCredKeyFromContext:
    def test_returns_hex_digest_for_header_creds(self):
        from finops_core.mcp_servers.connector_auth import cred_key_from_context
        from finops_core.config import Config

        cfg = Config.load()
        ctx = _ctx_with_headers({
            "x-aws-access-key-id": "AK",
            "x-aws-secret-access-key": "SK",
            "x-aws-session-token": "ST",
            "x-aws-region": "us-east-1",
        })
        key = cred_key_from_context(ctx, cfg)
        expected = hashlib.sha256(b"AK:SK:ST:us-east-1").hexdigest()[:16]
        assert key == expected

    def test_returns_server_side_sentinel_when_no_request(self):
        from finops_core.mcp_servers.connector_auth import cred_key_from_context
        from finops_core.config import Config

        cfg = Config.load()
        ctx = _ctx_no_request()
        assert cred_key_from_context(ctx, cfg) == "server-side"

    def test_returns_server_side_sentinel_when_ctx_is_none(self):
        from finops_core.mcp_servers.connector_auth import cred_key_from_context
        from finops_core.config import Config

        cfg = Config.load()
        assert cred_key_from_context(None, cfg) == "server-side"

    def test_same_creds_produce_same_key(self):
        from finops_core.mcp_servers.connector_auth import cred_key_from_context
        from finops_core.config import Config

        cfg = Config.load()
        headers = {"x-aws-access-key-id": "AK", "x-aws-secret-access-key": "SK"}
        key1 = cred_key_from_context(_ctx_with_headers(headers), cfg)
        key2 = cred_key_from_context(_ctx_with_headers(headers), cfg)
        assert key1 == key2

    def test_different_creds_produce_different_keys(self):
        from finops_core.mcp_servers.connector_auth import cred_key_from_context
        from finops_core.config import Config

        cfg = Config.load()
        key1 = cred_key_from_context(
            _ctx_with_headers({"x-aws-access-key-id": "AK1", "x-aws-secret-access-key": "SK1"}), cfg)
        key2 = cred_key_from_context(
            _ctx_with_headers({"x-aws-access-key-id": "AK2", "x-aws-secret-access-key": "SK2"}), cfg)
        assert key1 != key2


# ---------------------------------------------------------------------------
# MCP server modules must import cleanly (no AWS session at import time)
# ---------------------------------------------------------------------------

def _evict(*names: str) -> None:
    import sys
    for key in list(sys.modules):
        if any(key == n or key.startswith(n + ".") for n in names):
            del sys.modules[key]


@pytest.fixture(autouse=True)
def _patch_build_session(monkeypatch):
    """Make build_session raise so any accidental module-level call fails the test."""
    from botocore.exceptions import ProfileNotFound

    def _bomb(cfg):
        raise ProfileNotFound(profile="test-nonexistent")

    monkeypatch.setattr("finops_core.aws.session.build_session", _bomb)


def test_cost_server_imports_without_aws_session():
    _evict("finops_core.mcp_servers.cost_server")
    from finops_core.mcp_servers import cost_server  # noqa: F401


def test_anomaly_server_imports_without_aws_session():
    _evict("finops_core.mcp_servers.anomaly_server")
    from finops_core.mcp_servers import anomaly_server  # noqa: F401


def test_optimize_server_imports_without_aws_session():
    _evict("finops_core.mcp_servers.optimize_server")
    from finops_core.mcp_servers import optimize_server  # noqa: F401


def test_estate_server_imports_without_aws_session():
    _evict("devops_core.mcp_servers.estate_server")
    from devops_core.mcp_servers import estate_server  # noqa: F401
