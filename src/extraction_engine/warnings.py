from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(slots=True)
class ExtractionWarning:
    code: str
    message: str
    field: str | None = None
    table: str | None = None
    severity: str = "warning"

    def to_dict(self) -> dict[str, str | None]:
        return asdict(self)
