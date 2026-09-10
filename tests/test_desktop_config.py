"""Reading the desktop client's own configuration.

The file is written by another program and by hand, so the parser has to survive
shapes we did not choose.
"""

import json

from worclaude_bench.desktop import ServerSpec, read_config


def _write(tmp_path, payload):
    path = tmp_path / "claude_desktop_config.json"
    path.write_text(json.dumps(payload))
    return path


def test_reads_stdio_servers(tmp_path):
    path = _write(tmp_path, {"mcpServers": {"fs": {"command": "npx", "args": ["-y", "x"]}}})
    servers = read_config(path)
    assert [(s.name, s.kind, s.command) for s in servers] == [("fs", "stdio", "npx")]


def test_reads_remote_servers(tmp_path):
    path = _write(tmp_path, {"mcpServers": {"remote": {"url": "https://example.test/sse"}}})
    assert read_config(path)[0].kind == "remote"


def test_a_config_with_no_servers_is_not_an_error(tmp_path):
    """A fresh install has the file and no servers in it."""
    assert read_config(_write(tmp_path, {})) == []


def test_a_malformed_entry_is_skipped_not_fatal(tmp_path):
    """One bad entry must not cost the measurement of the others."""
    path = _write(
        tmp_path,
        {"mcpServers": {"good": {"command": "x"}, "bad": "not-an-object"}},
    )
    assert [s.name for s in read_config(path)] == ["good"]


def test_stdio_target_inherits_the_environment(monkeypatch):
    """Nearly every stdio server needs PATH, and most need a credential the
    config references rather than contains."""
    monkeypatch.setenv("SOME_TOKEN", "abc")
    spec = ServerSpec(name="s", command="x", env={"EXTRA": "1"})
    target = spec.target()
    assert target.env["SOME_TOKEN"] == "abc"
    assert target.env["EXTRA"] == "1"
