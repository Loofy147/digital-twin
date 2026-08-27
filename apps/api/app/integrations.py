from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol


@dataclass(frozen=True)
class NormalizedObservation:
    kind: str
    occurred_at: str
    normalized: dict[str, Any]
    retention_days: int = 90


class Connector(Protocol):
    provider: str
    scopes: tuple[str, ...]

    def authorize_url(self, state: str, redirect_uri: str) -> str: ...
    def normalize(self, payload: dict[str, Any]) -> list[NormalizedObservation]: ...


class DisabledConnector:
    """Safe default for providers whose credentials are not configured."""

    def __init__(self, provider: str, scopes: tuple[str, ...] = ()):
        self.provider = provider
        self.scopes = scopes

    def authorize_url(self, state: str, redirect_uri: str) -> str:
        raise RuntimeError(f"Connector '{self.provider}' is disabled until provider credentials are configured")

    def normalize(self, payload: dict[str, Any]) -> list[NormalizedObservation]:
        if not isinstance(payload, dict):
            raise ValueError("Provider payload must be an object")
        return [NormalizedObservation(kind=f"{self.provider}.event", occurred_at=datetime.now(timezone.utc).isoformat(), normalized={"metadata": payload})]


CONNECTORS: dict[str, Connector] = {
    "calendar": DisabledConnector("calendar", ("read_events",)),
    "tasks": DisabledConnector("tasks", ("read_tasks",)),
    "notes": DisabledConnector("notes", ("read_notes",)),
    "email_metadata": DisabledConnector("email_metadata", ("read_metadata",)),
}


def get_connector(provider: str) -> Connector:
    try:
        return CONNECTORS[provider]
    except KeyError as exc:
        raise ValueError(f"Unsupported integration provider: {provider}") from exc
