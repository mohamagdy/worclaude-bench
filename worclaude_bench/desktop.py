"""The connector side: what your desktop client loads into every request.

There is no API on Claude Desktop to query, and this tool does not pretend
otherwise. What it does instead is read the same configuration Desktop reads,
connect to the same MCP servers Desktop connects to, and ask them the same
question Desktop would -- so the payloads counted here are the payloads Desktop
would carry, measured at the source rather than inferred.

One limitation worth stating plainly, because it decides whether the numbers
mean anything: `claude_desktop_config.json` holds the servers *you* configured.
Connectors added from Claude's own directory are provisioned server-side and do
not appear in that file. Point `--mcp-url` at those directly.
"""

from __future__ import annotations

import json
import os
import platform
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mcp import Client, StdioServerParameters


@dataclass
class ServerSpec:
    """One MCP server, however it was reached."""

    name: str
    command: str | None = None
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    url: str | None = None

    @property
    def kind(self) -> str:
        return "remote" if self.url else "stdio"

    def target(self) -> Any:
        if self.url:
            return self.url
        return StdioServerParameters(
            command=self.command or "",
            args=self.args,
            # Inherit the parent environment: a stdio server almost always needs
            # PATH, and most need a credential the config references rather than
            # contains.
            env={**os.environ, **self.env},
        )


@dataclass
class ServerReading:
    name: str
    kind: str
    ok: bool
    tools: list[dict[str, Any]] = field(default_factory=list)
    error: str = ""


def config_path(explicit: str | None = None) -> Path | None:
    """Where Claude Desktop keeps its MCP configuration on this machine."""
    if explicit:
        return Path(explicit).expanduser()
    system = platform.system()
    if system == "Darwin":
        candidate = (
            Path.home() / "Library/Application Support/Claude"
            / "claude_desktop_config.json"
        )
    elif system == "Windows":
        base = os.environ.get("APPDATA")
        candidate = (
            Path(base) / "Claude/claude_desktop_config.json" if base else None
        )
    else:
        candidate = Path.home() / ".config/Claude/claude_desktop_config.json"
    return candidate if candidate and candidate.exists() else None


def read_config(path: Path) -> list[ServerSpec]:
    """Every MCP server the desktop client is configured to load."""
    raw = json.loads(path.read_text())
    servers = []
    for name, entry in (raw.get("mcpServers") or {}).items():
        if not isinstance(entry, dict):
            continue
        servers.append(
            ServerSpec(
                name=name,
                command=entry.get("command"),
                args=list(entry.get("args") or []),
                env=dict(entry.get("env") or {}),
                url=entry.get("url") or entry.get("serverUrl"),
            )
        )
    return servers


async def read_server(spec: ServerSpec, timeout: float = 30.0) -> ServerReading:
    """Connect, list what it advertises, disconnect.

    A server that will not start is reported rather than raised: one broken
    entry in a config should not cost you the measurement of the other six.
    """
    try:
        async with Client(spec.target(), read_timeout_seconds=timeout,
                          raise_exceptions=False) as client:
            listing = await client.list_tools()
            tools = [
                {
                    "name": tool.name,
                    "description": tool.description or "",
                    "inputSchema": _schema_of(tool),
                }
                for tool in listing.tools
                if tool.name
            ]
        return ServerReading(spec.name, spec.kind, True, tools)
    except Exception as exc:  # noqa: BLE001 - a dead server is a result, not a crash
        return ServerReading(spec.name, spec.kind, False, [], f"{type(exc).__name__}: {exc}")


async def call_tool(spec: ServerSpec, tool: str, arguments: dict[str, Any],
                    timeout: float = 60.0) -> str:
    """Run one tool and return exactly the text the model would receive."""
    async with Client(spec.target(), read_timeout_seconds=timeout,
                      raise_exceptions=False) as client:
        result = await client.call_tool(tool, arguments, read_timeout_seconds=timeout)
    return _text_of(result)


def _schema_of(tool: Any) -> dict[str, Any]:
    schema = getattr(tool, "inputSchema", None) or getattr(tool, "input_schema", None)
    if hasattr(schema, "model_dump"):
        return schema.model_dump(exclude_none=True)
    return schema or {"type": "object", "properties": {}}


def _text_of(result: Any) -> str:
    """Flatten a tool result to the text a model would be handed."""
    blocks = getattr(result, "content", None) or []
    parts = []
    for block in blocks:
        text = getattr(block, "text", None)
        if text:
            parts.append(text)
        elif hasattr(block, "model_dump_json"):
            parts.append(block.model_dump_json())
    return "\n".join(parts)
