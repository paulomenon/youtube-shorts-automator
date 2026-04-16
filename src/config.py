import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class CaptionStyle:
    font: str = "Arial"
    font_size: int = 24
    font_color: str = "white"
    outline_color: str = "black"
    outline_width: int = 2


@dataclass
class Schedule:
    frequency: str = "daily"
    time: str = "10:00"
    days: list[str] = field(default_factory=lambda: ["Monday", "Wednesday", "Friday"])


@dataclass
class AppConfig:
    watch_dir: str = "./videos/input"
    output_dir: str = "./videos/output"
    ready_for_upload_dir: str = "./videos/ready_for_upload"
    number_of_shorts_per_video: int = 5
    mode: str = "auto"
    schedule: Schedule = field(default_factory=Schedule)
    caption_style: CaptionStyle = field(default_factory=CaptionStyle)
    processing_mode: str = "eager"
    openai_api_key: str = ""
    youtube_client_secrets: str = "./client_secrets.json"
    database_path: str = "./data/shorts_automator.db"

    def __post_init__(self):
        self.watch_dir = str(Path(self.watch_dir).resolve())
        self.output_dir = str(Path(self.output_dir).resolve())
        self.ready_for_upload_dir = str(Path(self.ready_for_upload_dir).resolve())
        self.database_path = str(Path(self.database_path).resolve())
        self.youtube_client_secrets = str(Path(self.youtube_client_secrets).resolve())

        os.makedirs(self.watch_dir, exist_ok=True)
        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(self.ready_for_upload_dir, exist_ok=True)
        os.makedirs(os.path.dirname(self.database_path), exist_ok=True)

        if self.mode not in ("auto", "manual"):
            raise ValueError(f"mode must be 'auto' or 'manual', got '{self.mode}'")
        if self.processing_mode not in ("eager", "lazy"):
            raise ValueError(
                f"processing_mode must be 'eager' or 'lazy', got '{self.processing_mode}'"
            )
        if self.number_of_shorts_per_video < 1:
            raise ValueError("number_of_shorts_per_video must be >= 1")


def _parse_schedule(raw: Optional[dict]) -> Schedule:
    if raw is None:
        return Schedule()
    return Schedule(
        frequency=raw.get("frequency", "daily"),
        time=raw.get("time", "10:00"),
        days=raw.get("days", ["Monday", "Wednesday", "Friday"]),
    )


def _parse_caption_style(raw: Optional[dict]) -> CaptionStyle:
    if raw is None:
        return CaptionStyle()
    return CaptionStyle(
        font=raw.get("font", "Arial"),
        font_size=raw.get("font_size", 24),
        font_color=raw.get("font_color", "white"),
        outline_color=raw.get("outline_color", "black"),
        outline_width=raw.get("outline_width", 2),
    )


def load_config(path: str = "config.yaml") -> AppConfig:
    """Load configuration from a YAML file, falling back to defaults."""
    config_path = Path(path)
    raw: dict = {}

    if config_path.exists():
        with open(config_path, "r") as f:
            raw = yaml.safe_load(f) or {}

    return AppConfig(
        watch_dir=raw.get("watch_dir", "./videos/input"),
        output_dir=raw.get("output_dir", "./videos/output"),
        ready_for_upload_dir=raw.get("ready_for_upload_dir", "./videos/ready_for_upload"),
        number_of_shorts_per_video=raw.get("number_of_shorts_per_video", 5),
        mode=raw.get("mode", "auto"),
        schedule=_parse_schedule(raw.get("schedule")),
        caption_style=_parse_caption_style(raw.get("caption_style")),
        processing_mode=raw.get("processing_mode", "eager"),
        openai_api_key=raw.get("openai_api_key", os.environ.get("OPENAI_API_KEY", "")),
        youtube_client_secrets=raw.get("youtube_client_secrets", "./client_secrets.json"),
        database_path=raw.get("database_path", "./data/shorts_automator.db"),
    )
