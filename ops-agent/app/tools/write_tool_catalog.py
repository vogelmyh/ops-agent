"""Format WRITE_TOOLS metadata for decide Step 1 handleability assessment."""

from __future__ import annotations

from typing import Any

from langchain_core.tools import BaseTool

from app.tools.policy import risk_for_tool


def _field_line(name: str, field_info: Any) -> str:
    type_name = getattr(field_info.annotation, "__name__", str(field_info.annotation))
    if field_info.is_required():
        req = "required"
    else:
        req = f"optional, default={field_info.default!r}"
    line = f"    - {name} ({type_name}, {req})"
    if field_info.description:
        line += f": {field_info.description}"
    return line


def format_tool_entry(tool: BaseTool) -> str:
    name = tool.name
    risk = risk_for_tool(name).value
    description = (tool.description or "").strip() or "(no description)"
    lines = [
        f"- {name} (policy risk={risk})",
        f"  Description: {description}",
    ]
    schema = tool.args_schema
    if schema is not None and hasattr(schema, "model_fields"):
        lines.append("  Parameters:")
        for param_name, field_info in schema.model_fields.items():
            lines.append(_field_line(param_name, field_info))
    return "\n".join(lines)


def format_write_tools_catalog(tools: list[BaseTool]) -> str:
    """Build the authoritative write-tool list for decide Step 1 prompts."""
    if not tools:
        return "(no write tools configured)"
    return "\n\n".join(format_tool_entry(tool) for tool in tools)
