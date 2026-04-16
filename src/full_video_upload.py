"""
Full Video Upload Pipeline

Watches ./videos/ready_for_upload for new video files. For each video:
1. Transcribe with Whisper to generate captions (SRT)
2. Generate metadata (title, description, hashtags) via LLM
3. Upload the full video to YouTube as private
4. Upload the SRT as a separate subtitle track
5. Move the video to ./videos/input to trigger shorts generation

Can also be run once with --now to process all existing files and exit.
"""

import argparse
import logging
import os
import shutil
import signal
import sys
import time
from pathlib import Path

logger = logging.getLogger("full_video_upload")

VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}


def _setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def _is_video_file(path: str) -> bool:
    return Path(path).suffix.lower() in VIDEO_EXTENSIONS


def _process_video(filepath: str, config, privacy_status: str = "private") -> bool:
    """
    Process a single full-length video: transcribe, generate metadata,
    upload to YouTube, upload caption track, and move to input folder.

    Returns True on success, False on failure.
    """
    from src.caption_generator import transcribe_clip
    from src.metadata_generator import generate_metadata
    from src.uploader import upload_caption_track, upload_short

    filename = os.path.basename(filepath)
    logger.info("Processing full video: %s (visibility: %s)", filename, privacy_status)

    # 1. Transcribe
    logger.info("Step 1/4: Transcribing…")
    try:
        srt_path, transcript = transcribe_clip(filepath)
    except Exception as e:
        logger.error("Transcription failed for %s: %s", filename, e)
        return False

    # 2. Generate metadata
    logger.info("Step 2/4: Generating metadata…")
    metadata = generate_metadata(
        transcript=transcript,
        api_key=config.openai_api_key,
        source_filename=filename,
    )
    logger.info("Title: %s", metadata.title)

    # 3. Upload full video to YouTube
    logger.info("Step 3/4: Uploading to YouTube as %s…", privacy_status)
    try:
        video_id = upload_short(
            filepath=filepath,
            title=metadata.title,
            description=metadata.full_description,
            tags=[tag.strip("#") for tag in metadata.hashtags],
            publish_at=None,
            client_secrets_path=config.youtube_client_secrets,
            privacy_status=privacy_status,
        )
    except Exception as e:
        logger.error("Upload failed for %s: %s", filename, e)
        return False

    logger.info("Uploaded — YouTube ID: %s", video_id)

    # 4. Upload subtitle track
    logger.info("Step 4/4: Uploading subtitle track…")
    try:
        upload_caption_track(
            video_id=video_id,
            srt_path=srt_path,
            language="en",
            client_secrets_path=config.youtube_client_secrets,
        )
    except Exception as e:
        logger.warning("Caption upload failed (video still uploaded): %s", e)

    # Clean up SRT from the ready_for_upload folder
    try:
        os.unlink(srt_path)
    except OSError:
        pass

    # Move video to input folder to trigger shorts generation
    dest = os.path.join(config.watch_dir, filename)
    if os.path.exists(dest):
        base, ext = os.path.splitext(filename)
        dest = os.path.join(config.watch_dir, f"{base}_{video_id}{ext}")

    shutil.move(filepath, dest)
    logger.info("Moved to %s — shorts generation will begin automatically", dest)
    return True


def _process_existing(config, privacy_status: str = "private") -> int:
    """Process all video files currently in the ready_for_upload directory."""
    processed = 0
    for entry in sorted(os.scandir(config.ready_for_upload_dir), key=lambda e: e.name):
        if entry.is_file() and _is_video_file(entry.path):
            if _process_video(os.path.abspath(entry.path), config, privacy_status):
                processed += 1
    return processed


def _run_watcher(config, privacy_status: str = "private"):
    """Watch the ready_for_upload folder and process new videos as they appear."""
    from src.watcher import FolderWatcher

    def on_new_video(filepath: str):
        _process_video(filepath, config, privacy_status)

    watcher = FolderWatcher(
        watch_dir=config.ready_for_upload_dir,
        on_new_video=on_new_video,
    )

    _process_existing(config, privacy_status)

    watcher.start()
    logger.info(
        "Watching %s for full videos — press Ctrl+C to stop",
        config.ready_for_upload_dir,
    )

    def shutdown(signum, frame):
        logger.info("Shutting down…")
        watcher.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        watcher.stop()


def main():
    _setup_logging()

    parser = argparse.ArgumentParser(
        prog="full-video-upload",
        description="Upload full videos to YouTube, then move to input folder for shorts generation.",
    )
    parser.add_argument(
        "--config", default="config.yaml",
        help="Path to config file (default: config.yaml)",
    )
    parser.add_argument(
        "--now", action="store_true",
        help="Process all videos in ready_for_upload now and exit",
    )
    parser.add_argument(
        "--public", action="store_true",
        help="Upload as public instead of private (default: private)",
    )

    args = parser.parse_args()

    from src.config import load_config
    config = load_config(args.config)

    privacy_status = "public" if args.public else "private"

    if args.now:
        count = _process_existing(config, privacy_status)
        logger.info("Done — processed %d video(s)", count)
    else:
        _run_watcher(config, privacy_status)


if __name__ == "__main__":
    main()
