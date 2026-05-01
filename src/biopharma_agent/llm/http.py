"""Small JSON HTTP transport used by provider adapters."""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol

from biopharma_agent.llm.errors import LLMHTTPError


class JsonTransport(Protocol):
    def post_json(
        self,
        url: str,
        payload: dict[str, Any],
        headers: dict[str, str] | None = None,
        timeout: float = 60.0,
    ) -> dict[str, Any]:
        """POST a JSON payload and return a decoded JSON object."""


@dataclass(frozen=True)
class UrllibJsonTransport:
    """Dependency-free transport suitable for the first MVP."""

    def post_json(
        self,
        url: str,
        payload: dict[str, Any],
        headers: dict[str, str] | None = None,
        timeout: float = 60.0,
    ) -> dict[str, Any]:
        encoded = json.dumps(payload).encode("utf-8")
        request_headers = {"Content-Type": "application/json", **(headers or {})}
        request = urllib.request.Request(
            url=url,
            data=encoded,
            headers=request_headers,
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise LLMHTTPError(f"HTTP {exc.code} from {url}: {body}") from exc
        except (urllib.error.URLError, socket.timeout) as exc:
            raise LLMHTTPError(f"Failed to reach {url}: {exc}") from exc

        try:
            decoded = json.loads(body)
        except json.JSONDecodeError as exc:
            raise LLMHTTPError(f"Non-JSON response from {url}: {body[:500]}") from exc

        if not isinstance(decoded, dict):
            raise LLMHTTPError(f"Expected JSON object from {url}, got {type(decoded).__name__}")
        return decoded

