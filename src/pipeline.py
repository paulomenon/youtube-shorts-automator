import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from src import db
from src.caption_generator import transcribe_clip
from src.config import AppConfig
from src.metadata_generator import generate_metadata
from src.queue_manager import QueueManager
from src.scheduler import PostingScheduler, compute_publish_dates
from src.uploader import upload_short
from src.video_processor import (
    build_clip_output_path,
    burn_captions,
    generate_clip_timestamps,
    get_video_duration,
    render_clip,
)
from src.watcher import FolderWatcher

logger = logging.getLogger(__name__)


class Pipeline:
    """
    Orchestrates the full video-to-shorts pipeline:
    detect -> split -> caption -> metadata -> schedule -> upload.
    """

    def __init__(self, config: AppConfig):
        self.config = config
        self.queue = QueueManager(mode=config.mode)
        self.posting_scheduler = PostingScheduler()
        self.watcher = FolderWatcher(
            watch_dir=config.watch_dir,
            on_new_video=self._on_new_video,
            on_video_removed=self._on_video_removed,
        )

    def start(self) -> None:
        """Start the folder watcher, resume pending work, and begin the posting schedule."""
        db.init_db(self.config.database_path)

        self._resume_interrupted_jobs()

        self.watcher.scan_existing(self._on_new_video)

        self.watcher.start()
        logger.info("Folder watcher started")

        self.posting_scheduler.start(
            schedule=self.config.schedule,
            callback=self._on_upload_trigger,
        )
        logger.info("Pipeline running — press Ctrl+C to stop")

    def stop(self) -> None:
        self.watcher.stop()
        self.posting_scheduler.stop()
        logger.info("Pipeline stopped")

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_new_video(self, filepath: str) -> None:
        """Handle a newly detected video file."""
        filename = os.path.basename(filepath)

        try:
            duration = get_video_duration(filepath)
        except Exception as e:
            logger.error("Could not read duration for %s: %s", filepath, e)
            duration = None

        job_id = self.queue.register_new_video(
            filepath=filepath,
            filename=filename,
            duration=duration,
            max_shorts=self.config.number_of_shorts_per_video,
        )

        if job_id is None:
            return

        if duration:
            self._create_short_records(job_id, filepath, duration)

        if self.config.processing_mode == "eager":
            self._process_job_eager(job_id)

    def _on_video_removed(self, filepath: str) -> None:
        self.queue.handle_video_removed(filepath)

    def _on_upload_trigger(self) -> None:
        """Called by the scheduler when it's time to upload the next short."""
        short = self.queue.get_next_short_to_upload()
        if not short:
            logger.info("Upload trigger fired but no shorts ready")
            return

        if self.config.processing_mode == "lazy" and short["output_path"] is None:
            self._process_single_short(short)
            short = db.get_short(short["id"])

        self._upload_single_short(short)

    # ------------------------------------------------------------------
    # Processing
    # ------------------------------------------------------------------

    def _create_short_records(self, job_id: int, filepath: str, duration: float) -> None:
        """Generate clip timestamps and create short records in the DB."""
        clips = generate_clip_timestamps(duration, self.config.number_of_shorts_per_video)

        publish_dates = compute_publish_dates(
            num_shorts=len(clips),
            schedule=self.config.schedule,
        )

        for i, clip in enumerate(clips):
            short_id = db.create_short(
                job_id=job_id,
                clip_index=clip.index,
                start_time=clip.start,
                end_time=clip.end,
            )
            if i < len(publish_dates):
                db.update_short_schedule(short_id, publish_dates[i].isoformat())

        logger.info("Created %d short records for job %d", len(clips), job_id)

    def _process_job_eager(self, job_id: int) -> None:
        """Process all shorts for a job upfront."""
        db.update_job_status(job_id, "processing")
        job = db.get_job(job_id)

        shorts = db.get_shorts_for_job(job_id)
        for short in shorts:
            try:
                self._process_single_short(short, job=job)
                db.increment_shorts_created(job_id)
            except Exception as e:
                logger.error("Failed to process short %d: %s", short["id"], e)

        updated_job = db.get_job(job_id)
        if updated_job and updated_job["shorts_created"] >= updated_job["max_shorts"]:
            db.update_job_status(job_id, "completed")
            logger.info("Job %d fully processed", job_id)
            if self.config.mode == "auto":
                next_job = self.queue.get_next_job()
                if next_job:
                    self._process_job_eager(next_job["id"])

    def _process_single_short(self, short: dict, job: Optional[dict] = None) -> None:
        """Render clip, generate captions, burn them in, and generate metadata."""
        if job is None:
            job = db.get_job(short["job_id"])

        raw_clip_path = build_clip_output_path(
            self.config.output_dir, short["job_id"], short["clip_index"], suffix="_raw"
        )
        final_clip_path = build_clip_output_path(
            self.config.output_dir, short["job_id"], short["clip_index"]
        )

        render_clip(job["filepath"], short["start_time"], short["end_time"], raw_clip_path)

        srt_path, transcript = transcribe_clip(raw_clip_path)

        burn_captions(raw_clip_path, srt_path, final_clip_path, self.config.caption_style)

        # Clean up the raw (no-captions) clip
        try:
            os.unlink(raw_clip_path)
        except OSError:
            pass

        db.update_short_paths(short["id"], final_clip_path, srt_path)

        metadata = generate_metadata(
            transcript=transcript,
            api_key=self.config.openai_api_key,
            source_filename=job["filename"],
        )
        db.update_short_metadata(
            short["id"],
            title=metadata.title,
            description=metadata.full_description,
            hashtags=metadata.hashtags_str,
        )

        logger.info(
            "Short %d processed: '%s' → %s",
            short["id"], metadata.title, final_clip_path,
        )

    def _upload_single_short(self, short: dict) -> None:
        """Upload a single short to YouTube."""
        if not short["output_path"] or not os.path.exists(short["output_path"]):
            logger.error("Short %d has no output file", short["id"])
            db.update_short_upload_status(short["id"], "failed")
            return

        publish_at = None
        if short["scheduled_at"]:
            try:
                publish_at = datetime.fromisoformat(short["scheduled_at"])
            except ValueError:
                pass

        tags = [t.strip("#") for t in (short["hashtags"] or "").split() if t.startswith("#")]

        try:
            video_id = upload_short(
                filepath=short["output_path"],
                title=short["title"] or "Untitled Short",
                description=short["description"] or "",
                tags=tags,
                publish_at=publish_at,
                client_secrets_path=self.config.youtube_client_secrets,
            )
            db.update_short_upload_status(short["id"], "uploaded", youtube_video_id=video_id)
        except Exception as e:
            retry_count = db.increment_short_retry(short["id"])
            if retry_count >= 3:
                db.update_short_upload_status(short["id"], "failed")
                logger.error("Short %d failed permanently after %d retries: %s", short["id"], retry_count, e)
            else:
                logger.warning("Short %d upload failed (attempt %d): %s", short["id"], retry_count, e)

    # ------------------------------------------------------------------
    # Recovery
    # ------------------------------------------------------------------

    def _resume_interrupted_jobs(self) -> None:
        """Resume jobs that were interrupted by a previous shutdown."""
        jobs = db.get_resumable_jobs()
        if not jobs:
            return

        logger.info("Resuming %d interrupted job(s)", len(jobs))
        for job in jobs:
            if self.config.processing_mode == "eager":
                unprocessed = [
                    s for s in db.get_shorts_for_job(job["id"])
                    if s["output_path"] is None
                ]
                for short in unprocessed:
                    try:
                        self._process_single_short(short, job=job)
                        db.increment_shorts_created(job["id"])
                    except Exception as e:
                        logger.error("Failed to resume short %d: %s", short["id"], e)
