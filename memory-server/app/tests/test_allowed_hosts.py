"""MCP_ALLOWED_HOSTS 解析与 FastMCP Host 校验测试（无数据库依赖）。

独立运行（跳过需要 PostgreSQL 的 conftest）：
    pytest app/tests/test_allowed_hosts.py --noconftest
"""

from __future__ import annotations

from contextlib import contextmanager

import pytest
from starlette.testclient import TestClient

from app.config import Settings, resolve_mcp_allowed_hosts

LAN_PATTERNS = (
    ["10.*"] + [f"172.{i}.*" for i in range(16, 32)] + ["192.168.*"]
)


class TestResolve:
    def test_default_lan(self):
        assert resolve_mcp_allowed_hosts("lan") == LAN_PATTERNS

    def test_lan_aliases(self):
        for alias in ("private", "RFC1918", " lan "):
            assert resolve_mcp_allowed_hosts(alias) == LAN_PATTERNS

    def test_single_ip(self):
        assert resolve_mcp_allowed_hosts("10.0.0.4") == ["10.0.0.4"]

    def test_cidr_octet_aligned(self):
        assert resolve_mcp_allowed_hosts("10.0.0.0/24") == ["10.0.0.*"]
        assert resolve_mcp_allowed_hosts("192.168.0.0/16") == ["192.168.*"]
        assert resolve_mcp_allowed_hosts("10.0.0.0/8") == ["10.*"]
        assert resolve_mcp_allowed_hosts("10.0.0.4/32") == ["10.0.0.4"]

    def test_cidr_non_strict(self):
        assert resolve_mcp_allowed_hosts("10.0.0.4/24") == ["10.0.0.*"]

    def test_cidr_partial_octet(self):
        assert resolve_mcp_allowed_hosts("172.16.0.0/12") == [
            f"172.{i}.*" for i in range(16, 32)
        ]
        assert resolve_mcp_allowed_hosts("10.0.0.0/25") == [
            f"10.0.0.{i}" for i in range(128)
        ]

    def test_wildcard_and_domain_passthrough(self):
        assert resolve_mcp_allowed_hosts("10.0.0.*, mcp.example.com") == [
            "10.0.0.*",
            "mcp.example.com",
        ]
        assert resolve_mcp_allowed_hosts("*") == ["*"]

    def test_mixed(self):
        assert resolve_mcp_allowed_hosts("lan,10.0.0.4") == LAN_PATTERNS + [
            "10.0.0.4"
        ]

    def test_empty_raises(self):
        for value in ("", "  ", ", ,"):
            with pytest.raises(ValueError):
                resolve_mcp_allowed_hosts(value)

    def test_invalid_cidr_raises(self):
        with pytest.raises(ValueError):
            resolve_mcp_allowed_hosts("10.0.0.0/33")

    def test_ipv6_cidr_raises(self):
        with pytest.raises(ValueError):
            resolve_mcp_allowed_hosts("2001:db8::/32")


class TestSettings:
    def test_default(self, monkeypatch):
        monkeypatch.delenv("MCP_ALLOWED_HOSTS", raising=False)
        assert Settings().mcp_allowed_hosts == "lan"

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("MCP_ALLOWED_HOSTS", "10.0.0.4,192.168.1.0/24")
        assert Settings().mcp_allowed_hosts == "10.0.0.4,192.168.1.0/24"


INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "host-test", "version": "0.0.0"},
    },
}


@contextmanager
def mcp_client(allowed_hosts: str):
    from app.tools import mcp

    app = mcp.http_app(
        transport="http",
        host_origin_protection=True,
        allowed_hosts=resolve_mcp_allowed_hosts(allowed_hosts),
    )
    # 与生产一致绑定 0.0.0.0（unspecified 地址不会自动加入白名单）
    with TestClient(app, base_url="http://0.0.0.0:9000") as client:
        yield client


def initialize(client: TestClient, host: str):
    return client.post(
        "/mcp",
        headers={
            "Host": host,
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        },
        json=INITIALIZE,
    )


class TestHostGuard:
    def test_default_lan_allows_private_rejects_public(self):
        with mcp_client("lan") as client:
            for host in (
                "10.0.0.4:9000",
                "192.168.1.5:9000",
                "172.20.0.3:9000",
                "localhost:9000",
                "127.0.0.1:9000",
            ):
                assert initialize(client, host).status_code == 200, host
            assert initialize(client, "8.8.8.8:9000").status_code == 421

    def test_single_ip(self):
        with mcp_client("10.0.0.4") as client:
            assert initialize(client, "10.0.0.4:9000").status_code == 200
            assert initialize(client, "10.0.0.5:9000").status_code == 421

    def test_cidr(self):
        with mcp_client("10.0.0.0/24") as client:
            assert initialize(client, "10.0.0.99:9000").status_code == 200
            assert initialize(client, "10.0.1.1:9000").status_code == 421

    def test_domain_wildcard(self):
        with mcp_client("*.example.com") as client:
            assert initialize(client, "mcp.example.com").status_code == 200
            assert initialize(client, "evil.com").status_code == 421

    def test_star_allows_any(self):
        with mcp_client("*") as client:
            assert initialize(client, "anything.example:9000").status_code == 200