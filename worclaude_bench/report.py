"""Rendering the result so the shape of it is visible at a glance."""

from __future__ import annotations

import json
from typing import Any


def _rule(width: int) -> str:
    return "-" * width


def _row(cells: list[str], widths: list[int]) -> str:
    out = []
    for i, (cell, width) in enumerate(zip(cells, widths, strict=False)):
        out.append(cell.ljust(width) if i == 0 else cell.rjust(width))
    return "  ".join(out)


def table(headers: list[str], rows: list[list[str]]) -> str:
    widths = [
        max(len(headers[i]), *(len(r[i]) for r in rows)) if rows else len(headers[i])
        for i in range(len(headers))
    ]
    lines = [_row(headers, widths), _rule(sum(widths) + 2 * (len(widths) - 1))]
    lines += [_row(r, widths) for r in rows]
    return "\n".join(lines)


def render(result: dict[str, Any]) -> str:
    out: list[str] = []
    out.append(f"\nworclaude-bench  ·  counted with {result['model']}")
    out.append(f"question: {result['question']!r}\n")

    connectors = result.get("connectors") or []
    if connectors:
        out.append("Connector tool definitions — carried on every request")
        rows = [
            [c["name"], c["kind"], str(c["tool_count"]), f"{c['tool_tokens']:,}"]
            if c["ok"]
            else [c["name"], c["kind"], "—", f"unreachable: {c['error'][:40]}"]
            for c in connectors
        ]
        out.append(table(["server", "transport", "tools", "tokens"], rows))
        reachable = [c for c in connectors if c["ok"]]
        if reachable:
            total = sum(c["tool_tokens"] for c in reachable)
            count = sum(c["tool_count"] for c in reachable)
            plural = "server" if len(reachable) == 1 else "servers"
            out.append(
                f"\n  {count} tools across {len(reachable)} {plural} = {total:,} tokens\n"
            )

    sources = result.get("sources") or []
    if sources:
        out.append("Worclaude sources — the same question, through the index")
        rows = []
        for s in sources:
            usage = s.get("usage") or {}
            tokens = f"{s['tool_tokens']:,}" if s["tool_tokens"] else "—"
            rows.append([
                s["label"],
                str(s["tool_count"]),
                tokens,
                f"{s.get('result_chars', 0):,}",
                f"{usage.get('input_tokens', 0):,}" if usage else "—",
                f"{s.get('latency_ms', 0):,} ms" if s.get("latency_ms") else "—",
            ])
        out.append(table(
            ["source", "tools", "tool tokens", "result chars", "billed input", "latency"],
            rows,
        ))
        for s in sources:
            if s.get("error"):
                out.append(f"  {s['label']}: the turn failed — {s['error']}")
        for s in sources:
            if s.get("tool_tokens_note"):
                out.append(f"  {s['label']}: {s['tool_tokens_note']}")
        if not any(s.get("executed") for s in sources):
            out.append(
                "\n  Counted without running anything. Pass --execute for billed "
                "usage and true tool-result sizes."
            )

    verdict = result.get("comparison") or {}
    if verdict:
        out.append("\nTool definitions in context")
        out.append(f"  connectors : {verdict['connector_tool_tokens']:,} tokens")
        out.append(f"  worclaude  : {verdict['worclaude_tool_tokens']:,} tokens")
        if verdict.get("ratio"):
            out.append(f"  difference : {verdict['ratio']}x")
        out.append(
            "\n  This is the fixed cost, paid on every request whether or not a\n"
            "  tool is called. Prompt caching bills a re-sent block at a tenth,\n"
            "  so the dollar gap is smaller than the token gap."
        )
    return "\n".join(out) + "\n"


def write_json(path: str, result: dict[str, Any]) -> None:
    with open(path, "w") as handle:
        json.dump(result, handle, indent=2)
