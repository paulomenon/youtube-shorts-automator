import argparse
import logging
import signal
import sys
import time

from src import db
from src.config import load_config

logger = logging.getLogger("shorts_automator")


def _setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def cmd_start(args):
    """Launch the folder watcher and posting scheduler."""
    from src.pipeline import Pipeline

    config = load_config(args.config)
    pipeline = Pipeline(config)

    def shutdown(signum, frame):
        logger.info("Shutting down…")
        pipeline.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    pipeline.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pipeline.stop()


def cmd_status(args):
    """Show all jobs and their progress."""
    config = load_config(args.config)
    db.init_db(config.database_path)

    jobs = db.get_all_jobs()
    if not jobs:
        print("No jobs found.")
        return

    print(f"\n{'ID':>4}  {'Status':<12}  {'Shorts':>10}  {'Filename'}")
    print("-" * 70)

    for job in jobs:
        shorts_info = f"{job['shorts_created']}/{job['max_shorts']}"
        print(f"{job['id']:>4}  {job['status']:<12}  {shorts_info:>10}  {job['filename']}")

    print()

    # Show upload summary
    for status in ("pending", "scheduled", "uploaded", "failed"):
        shorts = db.get_shorts_by_upload_status(status)
        if shorts:
            print(f"  {status}: {len(shorts)} short(s)")

    print()


def cmd_retry(args):
    """Retry a failed short upload."""
    config = load_config(args.config)
    db.init_db(config.database_path)

    short = db.get_short(args.short_id)
    if not short:
        print(f"Short {args.short_id} not found.")
        sys.exit(1)

    if short["upload_status"] != "failed":
        print(f"Short {args.short_id} is not in 'failed' state (current: {short['upload_status']}).")
        sys.exit(1)

    db.reset_short(args.short_id)
    print(f"Short {args.short_id} reset to 'pending'. It will be retried on the next upload trigger.")


def cmd_reset(args):
    """Reset a job for reprocessing."""
    config = load_config(args.config)
    db.init_db(config.database_path)

    job = db.get_job(args.job_id)
    if not job:
        print(f"Job {args.job_id} not found.")
        sys.exit(1)

    db.reset_job(args.job_id)
    print(f"Job {args.job_id} ({job['filename']}) reset for reprocessing.")


def main():
    _setup_logging()

    parser = argparse.ArgumentParser(
        prog="shorts-automator",
        description="Automate turning long videos into scheduled YouTube Shorts.",
    )
    parser.add_argument(
        "--config", default="config.yaml",
        help="Path to config file (default: config.yaml)",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    subparsers.add_parser("start", help="Launch folder watcher and scheduler")

    subparsers.add_parser("status", help="Show all jobs and their progress")

    retry_parser = subparsers.add_parser("retry", help="Retry a failed short upload")
    retry_parser.add_argument("short_id", type=int, help="ID of the short to retry")

    reset_parser = subparsers.add_parser("reset", help="Reset a job for reprocessing")
    reset_parser.add_argument("job_id", type=int, help="ID of the job to reset")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    commands = {
        "start": cmd_start,
        "status": cmd_status,
        "retry": cmd_retry,
        "reset": cmd_reset,
    }

    commands[args.command](args)


if __name__ == "__main__":
    main()
