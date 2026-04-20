from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mcp_orchestrator.config import Settings
from mcp_orchestrator.infrastructure.mcp_servers import LocalMcpServerCatalog
from mcp_orchestrator.main import create_app


def test_catalog_discovers_local_postgresql_server() -> None:
    catalog = LocalMcpServerCatalog(Path("mcps"))

    status = catalog.status()

    assert status["server_count"] >= 2
    names = {server["name"] for server in status["servers"]}
    assert "postgresql" in names
    assert "power_bi" in names


def test_catalog_marks_power_bi_as_npm_server() -> None:
    catalog = LocalMcpServerCatalog(Path("mcps"))

    servers = catalog.status()["servers"]
    power_bi = next(server for server in servers if server["name"] == "power_bi")

    assert power_bi["kind"] == "npm"
    assert power_bi["package_name"] == "@microsoft/powerbi-modeling-mcp"
    assert "powerbi-modeling-mcp" in power_bi["command"]


def test_catalog_accepts_powerbi_alias() -> None:
    catalog = LocalMcpServerCatalog(Path("mcps"))

    server = catalog.get("powerbi")

    assert server is not None
    assert server.name == "power_bi"


@pytest.mark.parametrize(
    ("folder_name", "alias"),
    [
        ("sql-server-mcp", "sql-server"),
        ("sqlserver-mcp", "sqlserver"),
        ("mssql-mcp", "mssql"),
    ],
)
def test_catalog_accepts_sql_server_aliases(tmp_path: Path, folder_name: str, alias: str) -> None:
    server_dir = tmp_path / folder_name
    server_dir.mkdir()
    (server_dir / "server.py").write_text("print('sql server mcp')", encoding="utf-8")
    catalog = LocalMcpServerCatalog(tmp_path)

    server = catalog.get(alias)

    assert server is not None
    assert server.name == "sql_server"


def test_api_exposes_mcp_servers_status() -> None:
    client = TestClient(create_app(Settings()))

    response = client.get("/mcp-servers/status")

    assert response.status_code == 200
    assert response.json()["server_count"] >= 2
