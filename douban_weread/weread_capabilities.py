from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from douban_weread.providers.weread import WeReadClient


@dataclass(slots=True, frozen=True)
class WeReadCapability:
    api_name: str
    description: str | None = None


class WeReadCapabilityDiscovery:
    """Read-only discovery of APIs exposed by the official WeRead Agent Gateway."""

    def __init__(self, client: WeReadClient) -> None:
        self.client = client

    def list_capabilities(self) -> tuple[WeReadCapability, ...]:
        payload = self.client._call("/_list")  # Official gateway meta endpoint documented by WeRead.
        names: dict[str, str | None] = {}
        self._collect(payload, names)
        return tuple(
            WeReadCapability(api_name=name, description=names[name])
            for name in sorted(names)
        )

    @classmethod
    def _collect(cls, value: object, names: dict[str, str | None]) -> None:
        if isinstance(value, Mapping):
            api_name = value.get("api_name") or value.get("apiName") or value.get("name")
            if isinstance(api_name, str) and api_name.startswith("/"):
                description = value.get("description") or value.get("desc")
                names.setdefault(
                    api_name,
                    str(description).strip() if isinstance(description, str) and description.strip() else None,
                )
            for child in value.values():
                cls._collect(child, names)
            return
        if isinstance(value, (list, tuple)):
            for child in value:
                cls._collect(child, names)
            return
        if isinstance(value, str) and value.startswith("/") and " " not in value:
            names.setdefault(value, None)
