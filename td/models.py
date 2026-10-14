from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta

VALID_STATES = ("focus", "active", "later", "done")

DURATION_UNITS = {"h": "hours", "d": "days"}


def parse_duration(text: str) -> timedelta:
    """Parse a duration like '4h' or '3d'."""
    match = re.fullmatch(r"([1-9][0-9]*)([hd])", text.strip().lower())
    if not match:
        raise ValueError(f"Invalid duration '{text}'. Use hours or days, e.g. 4h or 3d.")
    amount, unit = match.groups()
    return timedelta(**{DURATION_UNITS[unit]: int(amount)})


def slugify(title: str) -> str:
    """Convert a title to a filesystem-safe slug."""
    s = title.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = s.strip("-")
    s = re.sub(r"-{2,}", "-", s)
    return s


@dataclass
class Task:
    id: str
    title: str
    state: str
    created: datetime
    updated: datetime
    parent: str | None = None
    notes: str | None = None
    snoozed_until: datetime | None = None

    def is_snoozed(self, now: datetime) -> bool:
        return self.snoozed_until is not None and now < self.snoozed_until

    def to_dict(self) -> dict:
        d: dict = {
            "id": self.id,
            "title": self.title,
            "state": self.state,
        }
        if self.parent is not None:
            d["parent"] = self.parent
        if self.notes is not None:
            d["notes"] = self.notes
        if self.snoozed_until is not None:
            d["snoozed_until"] = self.snoozed_until
        d["created"] = self.created
        d["updated"] = self.updated
        return d

    @classmethod
    def from_dict(cls, data: dict) -> Task:
        return cls(
            id=data["id"],
            title=data["title"],
            state=data["state"],
            parent=data.get("parent"),
            notes=data.get("notes"),
            snoozed_until=data.get("snoozed_until"),
            created=data["created"],
            updated=data["updated"],
        )
