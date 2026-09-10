"""Normalising tool descriptors, which is where the three sides disagree.

MCP spells it `inputSchema`, the Anthropic API spells it `input_schema`, and a
tool listing rendered for a human spells it `parameters`. All three describe the
same bytes, and a token count that changed depending on which spelling arrived
would be a measurement of our own plumbing.
"""

from worclaude_bench.tokens import to_anthropic_tools


def test_mcp_spelling_is_accepted():
    out = to_anthropic_tools(
        [{"name": "search", "description": "d", "inputSchema": {"type": "object"}}]
    )
    assert out == [
        {"name": "search", "description": "d", "input_schema": {"type": "object"}}
    ]


def test_api_spelling_is_accepted():
    out = to_anthropic_tools(
        [{"name": "search", "description": "d", "input_schema": {"type": "object"}}]
    )
    assert out[0]["input_schema"] == {"type": "object"}


def test_parameters_spelling_is_accepted():
    out = to_anthropic_tools(
        [{"name": "s", "description": "d", "parameters": {"type": "object"}}]
    )
    assert out[0]["input_schema"] == {"type": "object"}


def test_all_three_spellings_produce_identical_output():
    """The point of the normaliser: the count must not depend on the spelling."""
    schema = {"type": "object", "properties": {"q": {"type": "string"}}}
    shapes = [
        {"name": "s", "description": "d", "inputSchema": schema},
        {"name": "s", "description": "d", "input_schema": schema},
        {"name": "s", "description": "d", "parameters": schema},
    ]
    rendered = [to_anthropic_tools([shape]) for shape in shapes]
    assert rendered[0] == rendered[1] == rendered[2]


def test_a_tool_with_no_schema_still_counts():
    """Some servers advertise a tool with no arguments at all. Dropping it would
    understate what that server puts in context."""
    out = to_anthropic_tools([{"name": "ping", "description": ""}])
    assert out[0]["input_schema"] == {"type": "object", "properties": {}}


def test_worclaude_qualified_name_is_used_when_present():
    out = to_anthropic_tools([{"qualified_name": "drive_search", "description": "d"}])
    assert out[0]["name"] == "drive_search"


def test_a_nameless_tool_does_not_crash_the_run():
    out = to_anthropic_tools([{"description": "d"}])
    assert out[0]["name"] == "unnamed"
