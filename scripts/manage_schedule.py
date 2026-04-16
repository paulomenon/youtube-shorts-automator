#!/usr/bin/env python3
"""
Manage a system cron job for the YouTube Shorts Automator.

Works on macOS and Linux. Creates, updates, or removes a crontab entry
that runs the automator on a schedule.

Usage:
    python scripts/manage_schedule.py set "0 10 * * *"
    python scripts/manage_schedule.py set "0 10 * * MON,WED,FRI"
    python scripts/manage_schedule.py set "*/30 * * * *"
    python scripts/manage_schedule.py show
    python scripts/manage_schedule.py remove
"""

import argparse
import os
import subprocess
import sys

MARKER = "# youtube-shorts-automator"


def _get_project_dir() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _get_python() -> str:
    """Prefer the venv python if it exists."""
    venv_python = os.path.join(_get_project_dir(), "venv", "bin", "python")
    if os.path.exists(venv_python):
        return venv_python
    return sys.executable


def _read_crontab() -> str:
    result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    if result.returncode != 0:
        return ""
    return result.stdout


def _write_crontab(content: str) -> None:
    proc = subprocess.run(
        ["crontab", "-"],
        input=content,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        print(f"Error writing crontab: {proc.stderr}", file=sys.stderr)
        sys.exit(1)


def _remove_existing(crontab: str) -> str:
    lines = crontab.splitlines()
    filtered = [line for line in lines if MARKER not in line]
    return "\n".join(filtered).strip() + "\n" if filtered else ""


def _build_cron_line(expression: str) -> str:
    project = _get_project_dir()
    python = _get_python()
    cmd = f"cd {project} && {python} -m src.main start --now"
    return f"{expression} {cmd} >> {project}/data/cron.log 2>&1 {MARKER}"


def cmd_set(args):
    """Set or update the cron schedule."""
    crontab = _read_crontab()
    crontab = _remove_existing(crontab)
    new_line = _build_cron_line(args.cron_expression)
    crontab += new_line + "\n"
    _write_crontab(crontab)
    print(f"Cron schedule set: {args.cron_expression}")
    print(f"Entry: {new_line}")


def cmd_show(args):
    """Show the current cron entry for the automator."""
    crontab = _read_crontab()
    found = False
    for line in crontab.splitlines():
        if MARKER in line:
            print(f"Current schedule: {line}")
            found = True
    if not found:
        print("No cron schedule found for youtube-shorts-automator.")


def cmd_remove(args):
    """Remove the cron entry for the automator."""
    crontab = _read_crontab()
    cleaned = _remove_existing(crontab)
    _write_crontab(cleaned)
    print("Cron schedule removed.")


def main():
    parser = argparse.ArgumentParser(
        description="Manage system cron job for YouTube Shorts Automator",
    )
    subparsers = parser.add_subparsers(dest="command")

    set_parser = subparsers.add_parser("set", help="Set or update the cron schedule")
    set_parser.add_argument(
        "cron_expression",
        help='Cron expression in quotes, e.g. "0 10 * * *" for daily at 10 AM',
    )

    subparsers.add_parser("show", help="Show the current cron schedule")
    subparsers.add_parser("remove", help="Remove the cron schedule")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    {"set": cmd_set, "show": cmd_show, "remove": cmd_remove}[args.command](args)


if __name__ == "__main__":
    main()
