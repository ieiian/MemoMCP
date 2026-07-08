"""
MCP Tools 测试

测试 MCP 工具注册和调用（Passive 模式）。
"""

from __future__ import annotations

import pytest

from app.tools import mcp


@pytest.mark.asyncio
async def test_tool_registration():
    """10 个 MCP 工具全部注册。"""
    expected = [
        "save_memory",
        "search_memory",
        "update_memory",
        "delete_memory",
        "get_memory",
        "list_memory",
        "clear_workspace",
        "analyze_memory",
        "summarize_memory",
        "merge_memory",
    ]
    for name in expected:
        tool = await mcp.get_tool(name)
        assert tool is not None, f"Tool {name} not registered"


@pytest.mark.asyncio
async def test_save_and_search_memory():
    """保存并搜索 Memory。"""
    result = await mcp.call_tool(
        "save_memory",
        {
            "workspace_id": "tools-test",
            "memory_type": "preference",
            "content": "Use pytest for all Python testing",
            "title": "Testing Framework",
            "tags": ["python", "testing"],
            "importance": 0.8,
        },
    )
    sc = result.structured_content
    assert "id" in sc
    mem_id = sc["id"]

    # 搜索
    search_result = await mcp.call_tool(
        "search_memory",
        {"workspace_id": "tools-test", "query": "pytest", "top_k": 5},
    )
    search_sc = search_result.structured_content
    assert search_sc["total"] >= 1

    # 清理
    await mcp.call_tool(
        "clear_workspace",
        {"workspace_id": "tools-test", "confirm": True},
    )


@pytest.mark.asyncio
async def test_ai_tools_fallback():
    """AI 工具在 Passive 模式下返回错误提示。"""
    # analyze_memory
    result = await mcp.call_tool(
        "analyze_memory",
        {"memory_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert "error" in result.structured_content

    # summarize_memory
    result = await mcp.call_tool(
        "summarize_memory",
        {"workspace_id": "nonexistent"},
    )
    assert "error" in result.structured_content

    # merge_memory
    result = await mcp.call_tool(
        "merge_memory",
        {"memory_ids": ["00000000-0000-0000-0000-000000000000", "00000000-0000-0000-0000-000000000001"]},
    )
    assert "error" in result.structured_content


@pytest.mark.asyncio
async def test_invalid_memory_type():
    """无效 memory_type 抛出异常。"""
    from fastmcp.exceptions import ToolError

    with pytest.raises(ToolError):
        await mcp.call_tool(
            "save_memory",
            {
                "workspace_id": "error-test",
                "memory_type": "invalid_type",
                "content": "This should fail",
            },
        )
