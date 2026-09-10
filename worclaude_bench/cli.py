"""worclaude-bench — one question, counted on both paths."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from typing import Any

from anthropic import Anthropic

from worclaude_bench import desktop, report
from worclaude_bench.tokens import Counter, to_anthropic_tools
from worclaude_bench.workbench import Worclaude

DEFAULT_MODEL = "claude-opus-5"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="worclaude-bench",
        description=(
            "Measure what one question costs through a Worclaude indexed source "
            "versus through the MCP connectors your desktop client loads."
        ),
        epilog=(
            "Claude Desktop exposes no API. This reads the same config Desktop "
            "reads and connects to the same servers, so the connector figures are "
            "measured at the source rather than guessed."
        ),
    )
    parser.add_argument("--question", required=True, help="The question to ask both paths.")
    parser.add_argument("--base-url", default=os.environ.get("WORCLAUDE_BASE_URL"),
                        help="Worclaude deployment, e.g. https://worclaude.example.com")
    parser.add_argument("--token", default=os.environ.get("WORCLAUDE_TOKEN"),
                        help="A Worclaude API token (wcl_...). Mint one in Settings, or "
                             "with: worclaude-cli token <email> --scope read --scope measure")
    parser.add_argument("--source", action="append", default=[], metavar="LABEL",
                        help="Source label or id to benchmark. Repeatable. Default: all.")
    parser.add_argument("--mcp-url", action="append", default=[], metavar="URL",
                        help="A remote MCP server to measure. Repeatable. Use this for "
                             "connectors added from Claude's directory, which are not in "
                             "the local config file.")
    parser.add_argument("--desktop-config", default=None,
                        help="Override the path to claude_desktop_config.json.")
    parser.add_argument("--no-desktop-config", action="store_true",
                        help="Skip auto-discovery; measure only --mcp-url servers.")
    parser.add_argument("--model", default=DEFAULT_MODEL,
                        help=f"Model to count tokens against (default: {DEFAULT_MODEL}).")
    parser.add_argument("--anthropic-api-key", default=os.environ.get("ANTHROPIC_API_KEY"))
    parser.add_argument("--json", dest="json_path", default=None,
                        help="Also write the full result to this path.")
    parser.add_argument("--execute", action="store_true",
                        help="Run the turn for real, for billed usage and true tool-result "
                             "sizes. Needs the `chat` scope, and spends money.")
    return parser


def collect_servers(args: argparse.Namespace) -> list[desktop.ServerSpec]:
    servers: list[desktop.ServerSpec] = []
    if not args.no_desktop_config:
        path = desktop.config_path(args.desktop_config)
        if path:
            servers.extend(desktop.read_config(path))
            print(f"Reading desktop config: {path}", file=sys.stderr)
        elif not args.mcp_url:
            print("No claude_desktop_config.json found — pass --mcp-url to measure a "
                  "connector, or --no-desktop-config to skip this side.", file=sys.stderr)
    for url in args.mcp_url:
        servers.append(desktop.ServerSpec(name=url, url=url))
    return servers


async def measure_connectors(servers: list[desktop.ServerSpec],
                             counter: Counter) -> list[dict[str, Any]]:
    readings = await asyncio.gather(*(desktop.read_server(s) for s in servers))
    out = []
    for reading in readings:
        entry: dict[str, Any] = {
            "name": reading.name,
            "kind": reading.kind,
            "ok": reading.ok,
            "error": reading.error,
            "tool_count": len(reading.tools),
            "tool_tokens": 0,
        }
        if reading.ok and reading.tools:
            entry["tool_tokens"] = counter.tools(to_anthropic_tools(reading.tools))
        out.append(entry)
    return out


def measure_sources(args: argparse.Namespace, counter: Counter) -> list[dict[str, Any]]:
    if not (args.base_url and args.token):
        print("Skipping the Worclaude side — needs --base-url and --token.",
              file=sys.stderr)
        return []

    out = []
    with Worclaude(args.base_url, args.token) as client:
        wanted = {w.lower() for w in args.source}
        try:
            listed = client.connections()
        except RuntimeError as exc:
            print(f"Worclaude: {exc}", file=sys.stderr)
            return []
        connections = [
            c for c in listed
            if not wanted or c.label.lower() in wanted or c.id in wanted
        ]
        if not connections:
            print("No matching sources on that account.", file=sys.stderr)
            return []

        for connection in connections:
            verb = "Asking" if args.execute else "Measuring"
            print(f"{verb} {connection.label}…", file=sys.stderr)
            try:
                measured = client.measure(
                    args.question, [connection.id], execute=args.execute
                )
            except Exception as exc:  # noqa: BLE001 - one bad source is not the run
                print(f"  failed: {exc}", file=sys.stderr)
                continue

            # Prefer the deployment's own count; fall back to counting the
            # schemas it returned. Either way the number is measured, never
            # estimated — the fallback exists because a deployment without
            # Anthropic credentials cannot count, and says so rather than guess.
            if measured.get("error"):
                # The deployment ran the turn and it failed. Reporting its zeros
                # as a result would make a broken source look like a free one.
                print(f"  the turn failed: {measured['error']}", file=sys.stderr)

            tokens = measured.get("tool_definition_tokens")
            if tokens is None and measured.get("schemas"):
                tokens = counter.tools(to_anthropic_tools(measured["schemas"]))
            note = measured.get("tool_definition_note") or ""

            out.append({
                "label": connection.label,
                "runtime_mode": connection.runtime_mode,
                "tool_count": sum(s["tool_count"] for s in measured.get("sources", [])),
                "tool_tokens": tokens or 0,
                "tool_tokens_note": note if tokens is None else "",
                "result_tokens": 0,
                "result_chars": measured.get("result_chars", 0),
                "tool_calls": len(measured.get("tool_calls", [])),
                "usage": measured.get("usage") or {},
                "latency_ms": measured.get("latency_ms") or 0,
                "executed": measured.get("executed", False),
                "error": measured.get("error") or "",
            })
    return out


def main() -> int:
    args = build_parser().parse_args()
    if not args.anthropic_api_key:
        print("An Anthropic API key is required to count tokens: set ANTHROPIC_API_KEY "
              "or pass --anthropic-api-key.", file=sys.stderr)
        return 2

    counter = Counter(Anthropic(api_key=args.anthropic_api_key), args.model)

    servers = collect_servers(args)
    connectors = asyncio.run(measure_connectors(servers, counter)) if servers else []
    sources = measure_sources(args, counter)

    connector_tokens = sum(c["tool_tokens"] for c in connectors if c["ok"])
    worclaude_tokens = sum(s["tool_tokens"] for s in sources)
    comparison: dict[str, Any] = {}
    if connector_tokens and worclaude_tokens:
        comparison = {
            "connector_tool_tokens": connector_tokens,
            "worclaude_tool_tokens": worclaude_tokens,
            "ratio": round(connector_tokens / worclaude_tokens, 1),
        }
    elif connector_tokens or worclaude_tokens:
        comparison = {
            "connector_tool_tokens": connector_tokens,
            "worclaude_tool_tokens": worclaude_tokens,
        }

    result = {
        "model": args.model,
        "question": args.question,
        "connectors": connectors,
        "sources": sources,
        "comparison": comparison,
    }
    print(report.render(result))
    if args.json_path:
        report.write_json(args.json_path, result)
        print(f"Wrote {args.json_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
