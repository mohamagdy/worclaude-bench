"""Counting tokens the way the model actually counts them.

Every figure this tool reports comes from Anthropic's `count_tokens` endpoint.
That matters more than it sounds: `tiktoken` is OpenAI's tokenizer, and it
undercounts Claude by 15-20% on prose and considerably more on the JSON that
tool results are formatted as. A benchmark built on it is wrong in a direction
that flatters whichever side sends more JSON.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from anthropic import Anthropic

#: The smallest legal request. Its cost is subtracted from every measurement so
#: what is reported is the payload, not the envelope carrying it.
_PROBE = [{"role": "user", "content": "."}]


@dataclass
class Counter:
    """Counts payloads against one model, with the envelope netted out."""

    client: Anthropic
    model: str

    def __post_init__(self) -> None:
        self._envelope = self._raw(_PROBE, None)

    def _raw(self, messages: list[dict[str, Any]], tools: list[dict] | None) -> int:
        kwargs: dict[str, Any] = {"model": self.model, "messages": messages}
        if tools:
            kwargs["tools"] = tools
        return self.client.messages.count_tokens(**kwargs).input_tokens

    def text(self, payload: str) -> int:
        """Tokens a block of text adds to a request."""
        if not payload:
            return 0
        return self._raw([{"role": "user", "content": payload}], None) - self._envelope

    def tools(self, tools: list[dict]) -> int:
        """Tokens a whole tool block adds, including its fixed preamble.

        This is the number that matters for a connector: the block is rendered
        into every request of every conversation, so a client holding twenty
        tools pays for twenty tools on each turn, whether or not it calls any.
        """
        if not tools:
            return 0
        return self._raw(_PROBE, tools) - self._envelope

    def tool_block_overhead(self, tools: list[dict]) -> int:
        """The fixed cost of having a tool block at all, in tokens.

        Solved rather than assumed. Counting tools one at a time includes this
        preamble once per tool, so the difference between the sum of the singles
        and the block as a whole gives it up exactly:

            sum(singles) = n * overhead + sum(marginals)
            block        =     overhead + sum(marginals)

        Worth isolating because it is the reason a character-based estimate of a
        small tool block can be off by several hundred percent -- the preamble is
        invisible in the JSON but very much present in the bill.
        """
        if len(tools) < 2:
            raise ValueError("need at least two tools to separate the fixed cost")
        singles = sum(self.tools([tool]) for tool in tools)
        return round((singles - self.tools(tools)) / (len(tools) - 1))


def to_anthropic_tools(listed: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalise tool descriptors from either side into API tool shape.

    MCP calls the field `inputSchema`; the Anthropic API calls it `input_schema`;
    Worclaude's own API hands back whichever its runtime recorded. All three
    describe the same bytes, and the count must not depend on which spelling
    arrived.
    """
    out = []
    for tool in listed:
        schema = (
            tool.get("input_schema")
            or tool.get("inputSchema")
            or tool.get("parameters")
            or {"type": "object", "properties": {}}
        )
        out.append(
            {
                "name": tool.get("name") or tool.get("qualified_name") or "unnamed",
                "description": tool.get("description") or "",
                "input_schema": schema,
            }
        )
    return out
