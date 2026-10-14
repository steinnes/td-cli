import json
import os
from datetime import datetime, timedelta

import pytest
from click.testing import CliRunner

from td.cli import cli
from td.store import init_project, load_task, save_task


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def project(tmp_path):
    init_project(str(tmp_path))
    return tmp_path


def invoke(runner, args, cwd, input=None):
    """Invoke CLI with working directory set."""
    prev = os.getcwd()
    os.chdir(cwd)
    try:
        return runner.invoke(cli, args, input=input)
    finally:
        os.chdir(prev)


class TestInit:
    def test_init(self, runner, tmp_path):
        result = invoke(runner, ["init"], tmp_path)
        assert result.exit_code == 0
        assert "Initialized" in result.output
        assert (tmp_path / ".td").is_dir()


class TestAdd:
    def test_add_basic(self, runner, project):
        result = invoke(runner, ["add", "Build login form"], project)
        assert result.exit_code == 0
        assert "build-login-form" in result.output

    def test_add_with_state(self, runner, project):
        result = invoke(runner, ["add", "Urgent", "--state", "focus"], project)
        assert result.exit_code == 0
        task = load_task(project, "urgent")
        assert task.state == "focus"

    def test_add_with_parent(self, runner, project):
        invoke(runner, ["add", "Parent task"], project)
        result = invoke(runner, ["add", "Child", "--parent", "parent-task"], project)
        assert result.exit_code == 0
        task = load_task(project, "child")
        assert task.parent == "parent-task"

    def test_add_custom_id(self, runner, project):
        result = invoke(runner, ["add", "My thing", "--id", "custom"], project)
        assert result.exit_code == 0
        assert "custom" in result.output

    def test_add_duplicate_id_collision(self, runner, project):
        invoke(runner, ["add", "Test"], project)
        result = invoke(runner, ["add", "Test"], project)
        assert result.exit_code == 0
        assert "test-2" in result.output


class TestStateCommands:
    def test_focus(self, runner, project):
        invoke(runner, ["add", "Task"], project)
        result = invoke(runner, ["focus", "task"], project)
        assert result.exit_code == 0
        assert "focus" in result.output

    def test_active(self, runner, project):
        invoke(runner, ["add", "Task", "--state", "focus"], project)
        result = invoke(runner, ["active", "task"], project)
        assert result.exit_code == 0
        assert "active" in result.output

    def test_later(self, runner, project):
        invoke(runner, ["add", "Task"], project)
        result = invoke(runner, ["later", "task"], project)
        assert result.exit_code == 0
        assert "later" in result.output

    def test_done(self, runner, project):
        invoke(runner, ["add", "Task"], project)
        result = invoke(runner, ["done", "task"], project)
        assert result.exit_code == 0
        assert "done" in result.output


class TestLs:
    def test_ls_empty(self, runner, project):
        result = invoke(runner, ["ls"], project)
        assert result.exit_code == 0
        assert "No tasks" in result.output

    def test_ls_hides_done(self, runner, project):
        invoke(runner, ["add", "A"], project)
        invoke(runner, ["done", "a"], project)
        result = invoke(runner, ["ls"], project)
        assert "a" not in result.output.lower().split("\n")[-1] or "No tasks" in result.output

    def test_ls_all_shows_done(self, runner, project):
        invoke(runner, ["add", "A"], project)
        invoke(runner, ["done", "a"], project)
        result = invoke(runner, ["ls", "--all"], project)
        assert "a" in result.output

    def test_ls_filter_state(self, runner, project):
        invoke(runner, ["add", "Focus thing", "--state", "focus"], project)
        invoke(runner, ["add", "Active thing"], project)
        result = invoke(runner, ["ls", "--state", "focus"], project)
        assert "focus-thing" in result.output
        assert "active-thing" not in result.output

    def test_ls_json(self, runner, project):
        invoke(runner, ["add", "Task one"], project)
        result = invoke(runner, ["ls", "--json"], project)
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 1
        assert data[0]["id"] == "task-one"


class TestTree:
    def test_tree_flat(self, runner, project):
        invoke(runner, ["add", "Root"], project)
        result = invoke(runner, ["tree"], project)
        assert result.exit_code == 0
        assert "root [active]" in result.output

    def test_tree_hierarchy(self, runner, project):
        invoke(runner, ["add", "Parent"], project)
        invoke(runner, ["add", "Child", "--parent", "parent"], project)
        result = invoke(runner, ["tree"], project)
        assert "parent [active]" in result.output
        assert "  child [active]" in result.output

    def test_tree_subtree(self, runner, project):
        invoke(runner, ["add", "A"], project)
        invoke(runner, ["add", "B", "--parent", "a"], project)
        invoke(runner, ["add", "C"], project)
        result = invoke(runner, ["tree", "a"], project)
        assert "a [active]" in result.output
        assert "b [active]" in result.output
        # "c" as a task ID should not appear — check lines start
        lines = [l.strip() for l in result.output.strip().splitlines()]
        assert not any(l.startswith("c ") for l in lines)


class TestShow:
    def test_show(self, runner, project):
        invoke(runner, ["add", "My task"], project)
        result = invoke(runner, ["show", "my-task"], project)
        assert result.exit_code == 0
        assert "my-task" in result.output
        assert "My task" in result.output
        assert "active" in result.output


class TestEdit:
    def test_edit_title(self, runner, project):
        invoke(runner, ["add", "Old title"], project)
        result = invoke(runner, ["edit", "old-title", "--title", "New title"], project)
        assert result.exit_code == 0
        task = load_task(project, "old-title")
        assert task.title == "New title"

    def test_edit_notes(self, runner, project):
        invoke(runner, ["add", "Task"], project)
        invoke(runner, ["edit", "task", "--notes", "hello"], project)
        task = load_task(project, "task")
        assert task.notes == "hello"

    def test_edit_parent(self, runner, project):
        invoke(runner, ["add", "Parent"], project)
        invoke(runner, ["add", "Child"], project)
        invoke(runner, ["edit", "child", "--parent", "parent"], project)
        task = load_task(project, "child")
        assert task.parent == "parent"

    def test_edit_remove_parent(self, runner, project):
        invoke(runner, ["add", "Parent"], project)
        invoke(runner, ["add", "Child", "--parent", "parent"], project)
        invoke(runner, ["edit", "child", "--parent", ""], project)
        task = load_task(project, "child")
        assert task.parent is None


class TestMv:
    def test_mv(self, runner, project):
        invoke(runner, ["add", "Parent"], project)
        invoke(runner, ["add", "Child"], project)
        result = invoke(runner, ["mv", "child", "parent"], project)
        assert result.exit_code == 0
        task = load_task(project, "child")
        assert task.parent == "parent"


class TestRm:
    def test_rm_with_force(self, runner, project):
        invoke(runner, ["add", "Doomed"], project)
        result = invoke(runner, ["rm", "doomed", "--force"], project)
        assert result.exit_code == 0
        assert "Deleted" in result.output

    def test_rm_confirm_yes(self, runner, project):
        invoke(runner, ["add", "Doomed"], project)
        result = invoke(runner, ["rm", "doomed"], project, input="y\n")
        assert result.exit_code == 0

    def test_rm_confirm_no(self, runner, project):
        invoke(runner, ["add", "Safe"], project)
        result = invoke(runner, ["rm", "safe"], project, input="n\n")
        assert result.exit_code != 0


class TestStatus:
    def test_status_empty(self, runner, project):
        result = invoke(runner, ["status"], project)
        assert result.exit_code == 0
        assert "total: 0" in result.output

    def test_status_counts(self, runner, project):
        invoke(runner, ["add", "A", "--state", "focus"], project)
        invoke(runner, ["add", "B"], project)
        invoke(runner, ["add", "C", "--state", "later"], project)
        result = invoke(runner, ["status"], project)
        assert "focus: 1" in result.output
        assert "active: 1" in result.output
        assert "later: 1" in result.output
        assert "total: 3" in result.output


PAST = datetime(2000, 1, 1, 0, 0, 0)
FAR_FUTURE = datetime(2999, 1, 1, 0, 0, 0)


def set_snoozed_until(project, task_id, until):
    task = load_task(project, task_id)
    task.snoozed_until = until
    save_task(project, task)


def listed_ids(result):
    return [line.split()[1] for line in result.output.strip().splitlines()[1:]]


class TestSnooze:
    def test_snooze_hours_sets_expiry(self, runner, project):
        invoke(runner, ["add", "Task"], project)
        before = datetime.now()
        result = invoke(runner, ["snooze", "task", "4h"], project)
        after = datetime.now()
        assert result.exit_code == 0
        until = load_task(project, "task").snoozed_until
        assert before + timedelta(hours=4) <= until <= after + timedelta(hours=4)

    def test_snooze_days_sets_expiry(self, runner, project):
        invoke(runner, ["add", "Task"], project)
        before = datetime.now()
        invoke(runner, ["snooze", "task", "3d"], project)
        after = datetime.now()
        until = load_task(project, "task").snoozed_until
        assert before + timedelta(days=3) <= until <= after + timedelta(days=3)

    def test_snooze_keeps_state(self, runner, project):
        invoke(runner, ["add", "Task", "--state", "focus"], project)
        invoke(runner, ["snooze", "task", "1d"], project)
        assert load_task(project, "task").state == "focus"

    def test_snooze_invalid_duration(self, runner, project):
        invoke(runner, ["add", "Task"], project)
        result = invoke(runner, ["snooze", "task", "2w"], project)
        assert result.exit_code != 0
        assert load_task(project, "task").snoozed_until is None

    def test_snooze_missing_task(self, runner, project):
        result = invoke(runner, ["snooze", "nope", "1d"], project)
        assert result.exit_code != 0

    def test_snoozed_hidden_from_ls(self, runner, project):
        invoke(runner, ["add", "Sleepy"], project)
        invoke(runner, ["add", "Awake"], project)
        invoke(runner, ["snooze", "sleepy", "4h"], project)
        result = invoke(runner, ["ls"], project)
        assert listed_ids(result) == ["awake"]

    def test_snoozed_hidden_from_ls_state_filter(self, runner, project):
        invoke(runner, ["add", "Sleepy", "--state", "focus"], project)
        invoke(runner, ["snooze", "sleepy", "4h"], project)
        result = invoke(runner, ["ls", "--state", "focus"], project)
        assert "sleepy" not in result.output

    def test_snoozed_hidden_from_ls_json(self, runner, project):
        invoke(runner, ["add", "Sleepy"], project)
        invoke(runner, ["snooze", "sleepy", "4h"], project)
        result = invoke(runner, ["ls", "--json"], project)
        assert json.loads(result.output) == []

    def test_snoozed_hidden_from_tree(self, runner, project):
        invoke(runner, ["add", "Sleepy"], project)
        invoke(runner, ["add", "Awake"], project)
        invoke(runner, ["snooze", "sleepy", "4h"], project)
        result = invoke(runner, ["tree"], project)
        assert "awake [active]" in result.output
        assert "sleepy" not in result.output

    def test_ls_all_includes_snoozed(self, runner, project):
        invoke(runner, ["add", "Sleepy"], project)
        invoke(runner, ["snooze", "sleepy", "4h"], project)
        result = invoke(runner, ["ls", "--all"], project)
        assert "sleepy" in listed_ids(result)

    def test_visible_after_expiry(self, runner, project):
        invoke(runner, ["add", "Sleepy"], project)
        set_snoozed_until(project, "sleepy", PAST)
        assert listed_ids(invoke(runner, ["ls"], project)) == ["sleepy"]
        assert "sleepy [active]" in invoke(runner, ["tree"], project).output
        data = json.loads(invoke(runner, ["ls", "--json"], project).output)
        assert [t["id"] for t in data] == ["sleepy"]

    def test_ls_snoozed_lists_only_active_snoozes(self, runner, project):
        invoke(runner, ["add", "Sleepy"], project)
        invoke(runner, ["add", "Expired"], project)
        invoke(runner, ["add", "Awake"], project)
        set_snoozed_until(project, "sleepy", FAR_FUTURE)
        set_snoozed_until(project, "expired", PAST)
        result = invoke(runner, ["ls", "--snoozed"], project)
        assert result.exit_code == 0
        assert listed_ids(result) == ["sleepy"]
        assert "2999-01-01" in result.output

    def test_ls_snoozed_empty(self, runner, project):
        invoke(runner, ["add", "Awake"], project)
        result = invoke(runner, ["ls", "--snoozed"], project)
        assert "No tasks" in result.output

    def test_ls_snoozed_json(self, runner, project):
        invoke(runner, ["add", "Sleepy"], project)
        set_snoozed_until(project, "sleepy", FAR_FUTURE)
        result = invoke(runner, ["ls", "--snoozed", "--json"], project)
        data = json.loads(result.output)
        assert data == [
            {
                "id": "sleepy",
                "title": "Sleepy",
                "state": "active",
                "snoozed_until": "2999-01-01T00:00:00",
            }
        ]

    def test_ls_snoozed_with_state_filter(self, runner, project):
        invoke(runner, ["add", "Focused", "--state", "focus"], project)
        invoke(runner, ["add", "Parked", "--state", "later"], project)
        set_snoozed_until(project, "focused", FAR_FUTURE)
        set_snoozed_until(project, "parked", FAR_FUTURE)
        result = invoke(runner, ["ls", "--snoozed", "--state", "later"], project)
        assert listed_ids(result) == ["parked"]

    def test_unsnooze(self, runner, project):
        invoke(runner, ["add", "Sleepy"], project)
        invoke(runner, ["snooze", "sleepy", "3d"], project)
        result = invoke(runner, ["unsnooze", "sleepy"], project)
        assert result.exit_code == 0
        assert load_task(project, "sleepy").snoozed_until is None
        assert listed_ids(invoke(runner, ["ls"], project)) == ["sleepy"]
        assert "sleepy" not in invoke(runner, ["ls", "--snoozed"], project).output

    def test_unsnooze_not_snoozed(self, runner, project):
        invoke(runner, ["add", "Awake"], project)
        result = invoke(runner, ["unsnooze", "awake"], project)
        assert result.exit_code == 0
        assert "not snoozed" in result.output

    def test_unsnooze_missing_task(self, runner, project):
        result = invoke(runner, ["unsnooze", "nope"], project)
        assert result.exit_code != 0

    def test_show_displays_active_snooze(self, runner, project):
        invoke(runner, ["add", "Sleepy"], project)
        set_snoozed_until(project, "sleepy", FAR_FUTURE)
        result = invoke(runner, ["show", "sleepy"], project)
        assert "snoozed: until 2999-01-01 00:00:00" in result.output

    def test_show_hides_expired_snooze(self, runner, project):
        invoke(runner, ["add", "Sleepy"], project)
        set_snoozed_until(project, "sleepy", PAST)
        result = invoke(runner, ["show", "sleepy"], project)
        assert "snoozed" not in result.output
