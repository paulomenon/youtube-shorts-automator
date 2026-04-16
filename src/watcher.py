import logging
import os
import time
from pathlib import Path
from typing import Callable, Optional

from watchdog.events import FileCreatedEvent, FileDeletedEvent, FileSystemEventHandler
from watchdog.observers import Observer

logger = logging.getLogger(__name__)

VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
STABILITY_CHECKS = 3
STABILITY_INTERVAL = 2  # seconds between size checks


def _is_video_file(path: str) -> bool:
    return Path(path).suffix.lower() in VIDEO_EXTENSIONS


def _wait_for_stable(filepath: str, checks: int = STABILITY_CHECKS, interval: float = STABILITY_INTERVAL) -> bool:
    """Wait until the file size stops changing (i.e. the copy/download is complete)."""
    prev_size = -1
    stable_count = 0

    for _ in range(checks * 10):
        if not os.path.exists(filepath):
            return False
        current_size = os.path.getsize(filepath)
        if current_size == prev_size and current_size > 0:
            stable_count += 1
            if stable_count >= checks:
                return True
        else:
            stable_count = 0
        prev_size = current_size
        time.sleep(interval)

    return False


class VideoEventHandler(FileSystemEventHandler):
    def __init__(
        self,
        on_new_video: Callable[[str], None],
        on_video_removed: Optional[Callable[[str], None]] = None,
    ):
        super().__init__()
        self._on_new_video = on_new_video
        self._on_video_removed = on_video_removed

    def on_created(self, event: FileCreatedEvent) -> None:
        if event.is_directory or not _is_video_file(event.src_path):
            return

        filepath = os.path.abspath(event.src_path)
        logger.info("New video detected: %s — waiting for file to stabilize…", filepath)

        if _wait_for_stable(filepath):
            logger.info("File stable, registering: %s", filepath)
            self._on_new_video(filepath)
        else:
            logger.warning("File never stabilized or was removed: %s", filepath)

    def on_deleted(self, event: FileDeletedEvent) -> None:
        if event.is_directory or not _is_video_file(event.src_path):
            return

        filepath = os.path.abspath(event.src_path)
        logger.info("Video removed: %s", filepath)

        if self._on_video_removed:
            self._on_video_removed(filepath)


class FolderWatcher:
    def __init__(
        self,
        watch_dir: str,
        on_new_video: Callable[[str], None],
        on_video_removed: Optional[Callable[[str], None]] = None,
    ):
        self._watch_dir = watch_dir
        self._handler = VideoEventHandler(on_new_video, on_video_removed)
        self._observer = Observer()

    def start(self) -> None:
        logger.info("Watching folder: %s", self._watch_dir)
        self._observer.schedule(self._handler, self._watch_dir, recursive=False)
        self._observer.start()

    def stop(self) -> None:
        self._observer.stop()
        self._observer.join()

    def scan_existing(self, on_new_video: Callable[[str], None]) -> None:
        """Process any video files already present in the watch directory."""
        for entry in os.scandir(self._watch_dir):
            if entry.is_file() and _is_video_file(entry.path):
                filepath = os.path.abspath(entry.path)
                logger.info("Found existing video: %s", filepath)
                on_new_video(filepath)
