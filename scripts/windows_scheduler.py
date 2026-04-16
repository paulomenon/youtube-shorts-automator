#!/usr/bin/env python3
"""
Manage a Windows Task Scheduler task for the YouTube Shorts Automator.

Creates, updates, or removes a scheduled task that runs the automator
using `schtasks.exe`.

Usage:
    python scripts\\windows_scheduler.py set --time 10:00
    python scripts\\windows_scheduler.py set --time 10:00 --days MON,WED,FRI
    python scripts\\windows_scheduler.py set --time 10:00 --frequency hourly --interval 2
    python scripts\\windows_scheduler.py show
    python scripts\\windows_scheduler.py remove
"""

import argparse
import os
import subprocess
import sys

TASK_NAME = "YouTubeShortsAutomator"


def _get_project_dir() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _get_python() -> str:
    """Prefer the venv python if it exists."""
    venv_python = os.path.join(_get_project_dir(), "venv", "Scripts", "python.exe")
    if os.path.exists(venv_python):
        return venv_python
    return sys.executable


def _run_schtasks(args_list: list[str], check: bool = True) -> subprocess.CompletedProcess:
    cmd = ["schtasks.exe"] + args_list
    result = subprocess.run(cmd, capture_output=True, text=True)
    if check and result.returncode != 0:
        print(f"Error: {result.stderr.strip()}", file=sys.stderr)
        sys.exit(1)
    return result


def cmd_set(args):
    """Create or update the scheduled task."""
    project = _get_project_dir()
    python = _get_python()
    command = f'"{python}" -m src.main start --now'

    schtasks_args = [
        "/Create",
        "/TN", TASK_NAME,
        "/TR", f'cmd /c "cd /d {project} && {command}"',
        "/F",  # force overwrite if exists
    ]

    freq = args.frequency.upper()

    if freq == "DAILY":
        schtasks_args += ["/SC", "DAILY", "/ST", args.time]

    elif freq == "WEEKLY":
        if not args.days:
            print("Error: --days is required for weekly frequency (e.g. --days MON,WED,FRI)", file=sys.stderr)
            sys.exit(1)
        schtasks_args += ["/SC", "WEEKLY", "/D", args.days, "/ST", args.time]

    elif freq == "HOURLY":
        interval = args.interval or 1
        schtasks_args += [
            "/SC", "MINUTE",
            "/MO", str(interval * 60),
            "/ST", args.time,
        ]

    elif freq == "ONCE":
        schtasks_args += ["/SC", "ONCE", "/ST", args.time]

    else:
        print(f"Error: Unknown frequency '{args.frequency}'. Use: daily, weekly, hourly, once", file=sys.stderr)
        sys.exit(1)

    _run_schtasks(schtasks_args)
    print(f"Scheduled task '{TASK_NAME}' created/updated.")
    print(f"  Frequency: {args.frequency}")
    print(f"  Time: {args.time}")
    if args.days:
        print(f"  Days: {args.days}")


def cmd_show(args):
    """Show the current scheduled task."""
    result = _run_schtasks(["/Query", "/TN", TASK_NAME, "/V", "/FO", "LIST"], check=False)
    if result.returncode != 0:
        print(f"No scheduled task found with name '{TASK_NAME}'.")
        return
    print(result.stdout)


def cmd_remove(args):
    """Remove the scheduled task."""
    _run_schtasks(["/Delete", "/TN", TASK_NAME, "/F"])
    print(f"Scheduled task '{TASK_NAME}' removed.")


def main():
    parser = argparse.ArgumentParser(
        description="Manage Windows Task Scheduler for YouTube Shorts Automator",
    )
    subparsers = parser.add_subparsers(dest="command")

    set_parser = subparsers.add_parser("set", help="Create or update the scheduled task")
    set_parser.add_argument(
        "--time", required=True,
        help="Time to run (24h format, e.g. 10:00)",
    )
    set_parser.add_argument(
        "--frequency", default="daily",
        help="Frequency: daily, weekly, hourly, once (default: daily)",
    )
    set_parser.add_argument(
        "--days", default=None,
        help="Days for weekly schedule (e.g. MON,WED,FRI)",
    )
    set_parser.add_argument(
        "--interval", type=int, default=None,
        help="Interval in hours for hourly frequency (default: 1)",
    )

    subparsers.add_parser("show", help="Show the current scheduled task")
    subparsers.add_parser("remove", help="Remove the scheduled task")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    {"set": cmd_set, "show": cmd_show, "remove": cmd_remove}[args.command](args)


if __name__ == "__main__":
    main()
