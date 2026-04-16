import logging
from typing import Optional

from src import db

logger = logging.getLogger(__name__)


class QueueManager:
    """Manages the processing queue with support for auto and manual modes."""

    def __init__(self, mode: str = "auto"):
        if mode not in ("auto", "manual"):
            raise ValueError(f"Invalid mode: {mode}")
        self.mode = mode

    def get_active_job(self) -> Optional[dict]:
        """Return the currently processing job, if any."""
        jobs = db.get_jobs_by_status("processing")
        return jobs[0] if jobs else None

    def get_next_job(self) -> Optional[dict]:
        """
        Return the next job to process.

        In auto mode, picks the oldest pending job.
        In manual mode, only returns a job if there is no completed job
        (user must remove/replace videos to continue).
        """
        active = self.get_active_job()
        if active:
            return active

        if self.mode == "manual":
            completed = db.get_jobs_by_status("completed")
            if completed:
                logger.info("Manual mode: waiting for user to add new video")
                return None

        pending = db.get_jobs_by_status("pending")
        if not pending:
            return None

        job = pending[0]
        db.update_job_status(job["id"], "processing")
        logger.info("Starting job %d: %s", job["id"], job["filename"])
        return db.get_job(job["id"])

    def check_job_limit(self, job: dict) -> bool:
        """Return True if the job has reached its shorts limit."""
        return job["shorts_created"] >= job["max_shorts"]

    def advance_if_needed(self, job_id: int) -> Optional[dict]:
        """
        Check if the current job is done and handle mode-specific transitions.

        Returns the next job to work on (may be the same job, a new one, or None).
        """
        job = db.get_job(job_id)
        if not job:
            return None

        if not self.check_job_limit(job):
            return job

        logger.info(
            "Job %d reached limit (%d/%d shorts)",
            job["id"], job["shorts_created"], job["max_shorts"],
        )
        db.update_job_status(job["id"], "completed")

        if self.mode == "auto":
            return self.get_next_job()
        else:
            logger.info("Manual mode: pausing — add a new video to continue")
            return None

    def get_next_short_to_process(self, job_id: int) -> Optional[dict]:
        """Get the next unprocessed short for a job (no output_path yet)."""
        shorts = db.get_shorts_for_job(job_id)
        for s in shorts:
            if s["output_path"] is None:
                return s
        return None

    def get_next_short_to_upload(self) -> Optional[dict]:
        """Get the next short that is ready for upload."""
        scheduled = db.get_shorts_by_upload_status("scheduled")
        if scheduled:
            return scheduled[0]

        pending = db.get_shorts_by_upload_status("pending")
        for s in pending:
            if s["output_path"] is not None and s["title"] is not None:
                return s
        return None

    def handle_video_removed(self, filepath: str) -> None:
        """Cancel a job when its source file is deleted."""
        db.cancel_job_by_filepath(filepath)
        logger.info("Cancelled job for removed file: %s", filepath)

    def register_new_video(self, filepath: str, filename: str, duration: Optional[float], max_shorts: int) -> Optional[int]:
        """Register a new video as a job, skipping if already registered."""
        existing = db.get_job_by_filepath(filepath)
        if existing and existing["status"] not in ("cancelled",):
            logger.info("Video already registered: %s (job %d)", filepath, existing["id"])
            return None

        job_id = db.create_job(filename, filepath, duration, max_shorts)
        logger.info("Registered new job %d: %s (max %d shorts)", job_id, filename, max_shorts)
        return job_id
