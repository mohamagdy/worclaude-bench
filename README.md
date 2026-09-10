# worclaude-bench

[![CI](https://github.com/mohamagdy/worclaude-bench/actions/workflows/ci.yml/badge.svg)](https://github.com/mohamagdy/worclaude-bench/actions/workflows/ci.yml)

Measure what one question costs, two ways: through a Worclaude indexed source,
and through the MCP connectors your desktop client loads.

Every number it reports is counted with Anthropic's `count_tokens` endpoint
against a real model. Nothing is estimated, and nothing uses `tiktoken` — that
is OpenAI's tokenizer, and it undercounts Claude by 15–20% on prose and more on
the JSON that tool results are formatted as.

## What it actually measures

**Claude Desktop has no API.** This tool does not pretend to query it. It reads
the same `claude_desktop_config.json` Desktop reads, connects to the same MCP
servers, and asks them the same question — so the connector figures are measured
at the source rather than inferred.

Two quantities come out:

| Quantity | How it is obtained |
|---|---|
| **Tool definitions** | `tools/list` from each MCP server, and the Worclaude API's own description of each source, both counted as a real tool block |
| **Tool results** | The bytes a real turn returned, read back from the persisted message rather than the truncated live stream |

The first is the one people underestimate. A tool block is rendered into *every*
request of *every* conversation, whether or not a tool is called — so a client
holding thirty tools pays for thirty tools on every turn.

## Install

```bash
pip install worclaude-bench      # or: uv tool install worclaude-bench
```

## Use

```bash
export ANTHROPIC_API_KEY=sk-ant-...
export WORCLAUDE_TOKEN=wcl_...

worclaude-bench \
  --question "What is our deployment process?" \
  --base-url https://worclaude.example.com
```

Get a key from **Settings → API access** in Worclaude, or on the server:

```bash
worclaude-cli token you@example.com --scope read --scope measure
```

Give it `read` and `measure`. Add `chat` only if you want the tool to run real
turns — that scope is what lets it spend money, which is exactly why it is
separate.

That reads your desktop config, measures every MCP server in it, then asks the
same question of every source on your Worclaude account and prints both sides.

### Measuring a connector that is not in your config file

Connectors added from Claude's own directory are provisioned server-side and do
**not** appear in `claude_desktop_config.json`. Point the tool at them directly:

```bash
worclaude-bench --question "..." --mcp-url https://mcp.example.com/v1/sse
```

### Useful flags

| Flag | Effect |
|---|---|
| `--source LABEL` | Benchmark one source instead of all. Repeatable. |
| `--mcp-url URL` | Measure a remote MCP server. Repeatable. |
| `--no-desktop-config` | Skip auto-discovery entirely. |
| `--desktop-config PATH` | Read a config from somewhere else. |
| `--model ID` | Count against a different model (default `claude-opus-5`). |
| `--json out.json` | Write the full result alongside the table. |
| `--keep-chats` | Leave the benchmark chats in place for inspection. |

Environment variables work too: `WORCLAUDE_BASE_URL`, `WORCLAUDE_TOKEN`,
`ANTHROPIC_API_KEY`.

Either side can run alone. Omit the token to measure only your connectors;
pass `--no-desktop-config` with no `--mcp-url` to measure only Worclaude.

## Reading the output

```
Tool definitions in context
  connectors : 13,453 tokens
  worclaude  :    562 tokens
  difference : 23.9x
```

Two honest caveats travel with that number, and the tool prints them:

- **Tokens are not dollars.** A re-sent tool block is served from the prompt
  cache at roughly a tenth of the input price, so the dollar gap is smaller than
  the token gap. Compare cost by pricing both sides through the same cache
  arithmetic, not by multiplying this ratio by a rate.
- **Your corpus decides the rest.** How much an index saves on *results* depends
  entirely on how much bigger your documents are than the answers inside them.
  Measured across four source types, that ranged from 1.8× to 8.7×. One number
  would not have been the truth.

## Cost

Counting is cheap — `count_tokens` is not billed as inference. The Worclaude
side runs a real turn per source, so it costs one turn of whatever model that
account is configured to use. Benchmark chats are deleted afterwards unless you
pass `--keep-chats`.

## Working on it

```bash
git clone git@github.com:mohamagdy/worclaude-bench.git
cd worclaude-bench
uv run --extra dev pytest      # tests
uv run --with ruff ruff check .  # lint
uv run worclaude-bench --help
```

The two halves are deliberately separable: `desktop.py` knows only about MCP
servers, `workbench.py` knows only about the Worclaude API, and `tokens.py`
counts. Nothing in `desktop.py` imports anything from `workbench.py`, so either
side can be measured — or replaced — without the other.

## Requirements

Python 3.11+, an Anthropic API key, and — for the Worclaude side — a Worclaude API
token carrying at least the `read` and `measure` scopes.

## Related

[Worclaude](https://github.com/mohamagdy/worclaude) — the source workbench this
measures. You do not need it to use the connector half of this tool.

## Licence

MIT.
