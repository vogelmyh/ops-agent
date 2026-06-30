from app.tools import WRITE_TOOLS
from app.tools.write_tool_catalog import format_write_tools_catalog


def test_catalog_lists_all_write_tools():
    catalog = format_write_tools_catalog(WRITE_TOOLS)
    for tool in WRITE_TOOLS:
        assert tool.name in catalog
        assert tool.description in catalog


def test_catalog_includes_risk_and_parameters():
    catalog = format_write_tools_catalog(WRITE_TOOLS)
    assert "patch_config" in catalog
    assert "policy risk=low" in catalog
    assert "config_key" in catalog
    assert "rollback_deployment" in catalog
    assert "policy risk=high" in catalog
    assert "cleanup_storage" in catalog


def test_catalog_empty_tools():
    assert format_write_tools_catalog([]) == "(no write tools configured)"


def test_standard_tool_set_size():
    assert len(WRITE_TOOLS) == 10
