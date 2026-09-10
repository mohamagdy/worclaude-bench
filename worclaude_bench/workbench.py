"""The Worclaude side: what an indexed source actually sends.

Nothing here is modelled. The tool block comes from the API's own description of
the connection, and the tool results come from a real turn -- run against a real
chat, over real credentials, returning the bytes the model really read.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx

API_PREFIX = "/api/v1"


@dataclass
class Connection:
    id: str
    label: str
    runtime_mode: str
    tools: list[dict[str, Any]] = field(default_factory=list)


class Worclaude:
    """A logged-in client against a Worclaude deployment."""

    def __init__(self, base_url: str, token: str, timeout: float = 300.0):
        self.base = base_url.rstrip("/")
        # An API token, not a password. It is scoped, it is revocable one at a
        # time, and nothing here ever holds the account's actual credential.
        self._http = httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers={"Authorization": f"Bearer {token}"},
        )

    def __enter__(self) -> Worclaude:
        return self

    def __exit__(self, *_: Any) -> None:
        self._http.close()

    def _url(self, path: str) -> str:
        return f"{self.base}{API_PREFIX}{path}"

    def _check(self, response: httpx.Response, what: str) -> None:
        """Turn a status code into something a person can act on."""
        if response.status_code == 401:
            raise RuntimeError(
                "that token is not valid, or has been revoked. Mint one with: "
                "worclaude-cli token <email> --scope read --scope measure"
            )
        if response.status_code == 403:
            raise RuntimeError(f"the token lacks a scope {what} needs: {response.text}")
        if response.status_code == 402:
            raise RuntimeError("this account is over its budget for the month.")
        if response.status_code == 404:
            raise RuntimeError(
                f"{what} is not available on this deployment — it may be running a "
                "version older than the one that added the measurement API."
            )
        response.raise_for_status()

    def measure(self, question: str, connection_ids: list[str], *,
                execute: bool = False, include_schemas: bool = True) -> dict[str, Any]:
        """Ask what a question costs, and get back numbers rather than an answer.

        `execute=False` is free and instant. `execute=True` runs the turn for
        real, which needs the `chat` scope as well and spends money.
        """
        response = self._http.post(
            self._url("/measure"),
            json={
                "question": question,
                "connection_ids": connection_ids,
                "execute": execute,
                "include_schemas": include_schemas,
            },
        )
        self._check(response, "measuring")
        return response.json()

    def connections(self) -> list[Connection]:
        response = self._http.get(self._url("/sources"))
        self._check(response, "listing sources")
        return [
            Connection(
                id=row["id"],
                label=row.get("label") or "",
                runtime_mode=row.get("runtime_mode") or "",
                tools=row.get("tools") or [],
            )
            for row in response.json()
        ]

    def default_model_id(self) -> str | None:
        response = self._http.get(self._url("/models"))
        self._check(response, "listing models")
        models = response.json()
        return models[0]["id"] if models else None
