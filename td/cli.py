from __future__ import annotations

import json
from datetime import datetime
from importlib.resources import files

import click

from td.models import VALID_STATES, Task, parse_duration, slugify
from td.store import (
    delete_task,
    find_td_root,
    init_project,
    load_all_tasks,
    load_task,
    resolve_unique_id,
    save_task,
)


@click.group()
def cli():
    """td — a local task state manager."""


@cli.command()
def init():
    """Initialize .td/ in the current directory."""
    root = init_project()
    click.echo(f"Initialized .td/ in {root}")


@cli.command()
@click.argument("title")
@click.option("--parent", default=None, help="Parent task ID.")
@click.option(
    "--state",
    default=None,
    type=click.Choice(VALID_STATES, case_sensitive=False),
    help="Initial state (default: active).",
)
@click.option("--id", "custom_id", default=None, help="Custom task ID.")
def add(title: str, parent: str | None, state: str | None, custom_id: str | None):
    """Create a new task."""
    root = find_td_root()

    if custom_id:
        task_id = custom_id
        if (root / ".td" / "tasks" / f"{task_id}.yaml").exists():
            raise click.ClickException(f"Task ID '{task_id}' already exists.")
    else:
        base = slugify(title)
        if not base:
            raise click.ClickException("Title must produce a valid slug.")
        task_id = resolve_unique_id(root, base)

    if state is None:
        state = "active"

    now = datetime.now()
    task = Task(
        id=task_id,
        title=title,
        state=state,
        parent=parent,
        created=now,
        updated=now,
    )
    save_task(root, task)
    click.echo(task_id)


def _set_state(task_id: str, new_state: str) -> None:
    root = find_td_root()
    task = load_task(root, task_id)
    task.state = new_state
    task.updated = datetime.now()
    save_task(root, task)
    click.echo(f"{task_id} → {new_state}")


@cli.command()
@click.argument("id")
def focus(id: str):
    """Move a task to focus."""
    _set_state(id, "focus")


@cli.command()
@click.argument("id")
def active(id: str):
    """Move a task to active."""
    _set_state(id, "active")


@cli.command()
@click.argument("id")
def later(id: str):
    """Park a task for later."""
    _set_state(id, "later")


@cli.command()
@click.argument("id")
def done(id: str):
    """Mark a task as done."""
    _set_state(id, "done")


def _parse_duration_option(ctx, param, value: str):
    try:
        return parse_duration(value)
    except ValueError as e:
        raise click.BadParameter(str(e)) from e


@cli.command()
@click.argument("id")
@click.argument("duration", callback=_parse_duration_option)
def snooze(id: str, duration):
    """Hide a task from listings for DURATION (e.g. 4h, 3d)."""
    root = find_td_root()
    task = load_task(root, id)
    now = datetime.now()
    task.snoozed_until = now + duration
    task.updated = now
    save_task(root, task)
    click.echo(f"{id} snoozed until {task.snoozed_until:%Y-%m-%d %H:%M}")


@cli.command()
@click.argument("id")
def unsnooze(id: str):
    """Bring a snoozed task back before its snooze expires."""
    root = find_td_root()
    task = load_task(root, id)
    now = datetime.now()
    if not task.is_snoozed(now):
        click.echo(f"{id} is not snoozed")
        return
    task.snoozed_until = None
    task.updated = now
    save_task(root, task)
    click.echo(f"{id} unsnoozed")


@cli.command(name="ls")
@click.option(
    "--state",
    "filter_state",
    default=None,
    type=click.Choice(VALID_STATES, case_sensitive=False),
    help="Filter by state.",
)
@click.option(
    "--all", "show_all", is_flag=True, help="Show all tasks including done and snoozed."
)
@click.option("--snoozed", "only_snoozed", is_flag=True, help="Show only snoozed tasks.")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
def ls_cmd(filter_state: str | None, show_all: bool, only_snoozed: bool, as_json: bool):
    """List tasks."""
    root = find_td_root()
    tasks = load_all_tasks(root)
    now = datetime.now()

    if only_snoozed:
        tasks = [t for t in tasks if t.is_snoozed(now)]
    elif not show_all:
        tasks = [t for t in tasks if not t.is_snoozed(now)]

    if filter_state:
        tasks = [t for t in tasks if t.state == filter_state]
    elif not show_all and not only_snoozed:
        tasks = [t for t in tasks if t.state != "done"]

    # Sort: focus first, then active, then later, then done
    state_order = {s: i for i, s in enumerate(VALID_STATES)}
    tasks.sort(key=lambda t: state_order.get(t.state, 99))

    if as_json:
        out = []
        for t in tasks:
            entry: dict = {"id": t.id, "title": t.title, "state": t.state}
            if t.parent:
                entry["parent"] = t.parent
            if t.is_snoozed(now):
                entry["snoozed_until"] = t.snoozed_until.isoformat()
            out.append(entry)
        click.echo(json.dumps(out, indent=2))
        return

    if not tasks:
        click.echo("No tasks.")
        return

    # Calculate column widths
    id_width = max(len(t.id) for t in tasks)
    state_width = max(len(t.state) for t in tasks)
    if not any(t.is_snoozed(now) for t in tasks):
        click.echo(f"{'STATE':<{state_width}}  {'ID':<{id_width}}  TITLE")
        for t in tasks:
            click.echo(f"{t.state:<{state_width}}  {t.id:<{id_width}}  {t.title}")
        return

    until_width = len("YYYY-MM-DD HH:MM")
    click.echo(
        f"{'STATE':<{state_width}}  {'ID':<{id_width}}  {'SNOOZED UNTIL':<{until_width}}  TITLE"
    )
    for t in tasks:
        until = f"{t.snoozed_until:%Y-%m-%d %H:%M}" if t.is_snoozed(now) else ""
        click.echo(
            f"{t.state:<{state_width}}  {t.id:<{id_width}}  {until:<{until_width}}  {t.title}"
        )


@cli.command()
@click.argument("id", required=False)
def tree(id: str | None):
    """Show tasks as a tree."""
    root = find_td_root()
    tasks = load_all_tasks(root)

    # By default hide done and snoozed
    now = datetime.now()
    tasks = [t for t in tasks if t.state != "done" and not t.is_snoozed(now)]

    task_map = {t.id: t for t in tasks}
    children: dict[str | None, list[Task]] = {}
    for t in tasks:
        children.setdefault(t.parent, []).append(t)

    def print_tree(parent_id: str | None, indent: int = 0) -> None:
        for t in children.get(parent_id, []):
            prefix = "  " * indent
            click.echo(f"{prefix}{t.id} [{t.state}]")
            print_tree(t.id, indent + 1)

    if id:
        if id not in task_map:
            raise click.ClickException(f"Task '{id}' not found.")
        t = task_map[id]
        click.echo(f"{t.id} [{t.state}]")
        print_tree(id, indent=1)
    else:
        print_tree(None)


@cli.command()
@click.argument("id")
def show(id: str):
    """Show full details of a task."""
    root = find_td_root()
    task = load_task(root, id)
    click.echo(f"id:      {task.id}")
    click.echo(f"title:   {task.title}")
    click.echo(f"state:   {task.state}")
    if task.parent:
        click.echo(f"parent:  {task.parent}")
    if task.notes:
        click.echo(f"notes:   {task.notes}")
    if task.is_snoozed(datetime.now()):
        click.echo(f"snoozed: until {task.snoozed_until}")
    click.echo(f"created: {task.created}")
    click.echo(f"updated: {task.updated}")


@cli.command()
@click.argument("id")
@click.option("--title", default=None, help="New title.")
@click.option("--notes", default=None, help="New notes.")
@click.option("--parent", default=None, help="New parent ID (empty string to remove).")
def edit(id: str, title: str | None, notes: str | None, parent: str | None):
    """Edit a task's title, notes, or parent."""
    root = find_td_root()
    task = load_task(root, id)
    changed = False

    if title is not None:
        task.title = title
        changed = True
    if notes is not None:
        task.notes = notes if notes else None
        changed = True
    if parent is not None:
        task.parent = parent if parent else None
        changed = True

    if changed:
        task.updated = datetime.now()
        save_task(root, task)
        click.echo(f"Updated {id}")
    else:
        click.echo("Nothing to update.")


@cli.command()
@click.argument("id")
@click.argument("parent_id")
def mv(id: str, parent_id: str):
    """Move a task under a different parent."""
    root = find_td_root()
    task = load_task(root, id)
    task.parent = parent_id
    task.updated = datetime.now()
    save_task(root, task)
    click.echo(f"Moved {id} → {parent_id}")


@cli.command()
@click.argument("id")
@click.option("--force", is_flag=True, help="Skip confirmation.")
def rm(id: str, force: bool):
    """Remove a task."""
    root = find_td_root()
    # Verify it exists first
    load_task(root, id)

    if not force:
        click.confirm(f"Delete task '{id}'?", abort=True)

    delete_task(root, id)
    click.echo(f"Deleted {id}")


@cli.command()
def skill():
    """Print the td-tasks LLM skill (SKILL.md)."""
    content = files("td").joinpath("SKILL.md").read_text()
    click.echo(content)


@cli.command()
def status():
    """Show summary counts by state."""
    root = find_td_root()
    tasks = load_all_tasks(root)
    counts = {s: 0 for s in VALID_STATES}
    for t in tasks:
        counts[t.state] = counts.get(t.state, 0) + 1
    total = len(tasks)
    parts = [f"{s}: {counts[s]}" for s in VALID_STATES]
    parts.append(f"total: {total}")
    click.echo("  ".join(parts))
