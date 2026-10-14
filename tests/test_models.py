from datetime import datetime, timedelta

import pytest

from td.models import VALID_STATES, Task, parse_duration, slugify


class TestSlugify:
    def test_basic(self):
        assert slugify("Build login form") == "build-login-form"

    def test_special_characters(self):
        assert slugify("Hello, World!") == "hello-world"

    def test_leading_trailing(self):
        assert slugify("  --hello--  ") == "hello"

    def test_consecutive_separators(self):
        assert slugify("a   b---c") == "a-b-c"

    def test_numbers(self):
        assert slugify("Step 1: Do thing") == "step-1-do-thing"

    def test_empty_after_strip(self):
        assert slugify("!!!") == ""

    def test_already_slug(self):
        assert slugify("my-task") == "my-task"


class TestTask:
    def _make_task(self, **overrides) -> Task:
        defaults = {
            "id": "test-task",
            "title": "Test task",
            "state": "active",
            "created": datetime(2026, 1, 1, 12, 0, 0),
            "updated": datetime(2026, 1, 1, 12, 0, 0),
        }
        defaults.update(overrides)
        return Task(**defaults)

    def test_to_dict_minimal(self):
        task = self._make_task()
        d = task.to_dict()
        assert d["id"] == "test-task"
        assert d["title"] == "Test task"
        assert d["state"] == "active"
        assert "parent" not in d
        assert "notes" not in d

    def test_to_dict_with_optionals(self):
        task = self._make_task(parent="parent-id", notes="Some notes")
        d = task.to_dict()
        assert d["parent"] == "parent-id"
        assert d["notes"] == "Some notes"

    def test_round_trip(self):
        task = self._make_task(parent="p", notes="n")
        d = task.to_dict()
        restored = Task.from_dict(d)
        assert restored.id == task.id
        assert restored.title == task.title
        assert restored.state == task.state
        assert restored.parent == task.parent
        assert restored.notes == task.notes
        assert restored.created == task.created
        assert restored.updated == task.updated

    def test_valid_states(self):
        assert VALID_STATES == ("focus", "active", "later", "done")

    def test_to_dict_omits_snoozed_until_when_unset(self):
        assert "snoozed_until" not in self._make_task().to_dict()

    def test_round_trip_snoozed_until(self):
        until = datetime(2026, 1, 4, 12, 0, 0)
        restored = Task.from_dict(self._make_task(snoozed_until=until).to_dict())
        assert restored.snoozed_until == until

    def test_from_dict_without_snoozed_until(self):
        d = self._make_task().to_dict()
        assert Task.from_dict(d).snoozed_until is None


class TestSnooze:
    NOW = datetime(2026, 1, 1, 12, 0, 0)

    def _make_task(self, **overrides) -> Task:
        return Task(
            id="t", title="T", state="active", created=self.NOW, updated=self.NOW, **overrides
        )

    def test_not_snoozed_by_default(self):
        assert not self._make_task().is_snoozed(self.NOW)

    def test_snoozed_while_active(self):
        task = self._make_task(snoozed_until=self.NOW + timedelta(hours=4))
        assert task.is_snoozed(self.NOW)
        assert task.is_snoozed(self.NOW + timedelta(hours=3, minutes=59))

    def test_not_snoozed_after_expiry(self):
        task = self._make_task(snoozed_until=self.NOW + timedelta(hours=4))
        assert not task.is_snoozed(self.NOW + timedelta(hours=4))
        assert not task.is_snoozed(self.NOW + timedelta(days=1))


class TestParseDuration:
    @pytest.mark.parametrize(
        "text, expected",
        [
            ("4h", timedelta(hours=4)),
            ("3d", timedelta(days=3)),
            ("1h", timedelta(hours=1)),
            ("10D", timedelta(days=10)),
        ],
    )
    def test_valid(self, text, expected):
        assert parse_duration(text) == expected

    @pytest.mark.parametrize("text", ["", "4", "h", "0h", "-1d", "2w", "1.5h", "3 d", "4hours"])
    def test_invalid(self, text):
        with pytest.raises(ValueError):
            parse_duration(text)
