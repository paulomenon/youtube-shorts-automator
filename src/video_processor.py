import json
import logging
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from src.config import CaptionStyle

logger = logging.getLogger(__name__)

MAX_SHORT_DURATION = 60.0  # seconds


@dataclass
class ClipTimestamp:
    index: int
    start: float
    end: float

    @property
    def duration(self) -> float:
        return self.end - self.start


def get_video_duration(filepath: str) -> float:
    """Get video duration in seconds using ffprobe."""
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        filepath,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    info = json.loads(result.stdout)
    return float(info["format"]["duration"])


def generate_clip_timestamps(duration: float, num_shorts: int) -> list[ClipTimestamp]:
    """
    Split a video into evenly spaced segments, each <= 60 seconds.

    If the video is short enough that equal segments would be under a minimum
    useful length (5s), fewer clips are returned.
    """
    if duration <= 0:
        return []

    segment_length = min(duration / num_shorts, MAX_SHORT_DURATION)

    if segment_length < 5.0:
        num_shorts = max(1, int(duration / 5.0))
        segment_length = duration / num_shorts

    clips = []
    for i in range(num_shorts):
        start = i * segment_length
        end = min(start + segment_length, duration)
        if end - start < 1.0:
            break
        clips.append(ClipTimestamp(index=i, start=round(start, 3), end=round(end, 3)))

    return clips


def render_clip(input_path: str, start: float, end: float, output_path: str) -> str:
    """Extract a clip from a video using ffmpeg."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    duration = end - start

    cmd = [
        "ffmpeg",
        "-y",
        "-ss", str(start),
        "-i", input_path,
        "-t", str(duration),
        "-c:v", "libx264",
        "-c:a", "aac",
        "-preset", "fast",
        "-movflags", "+faststart",
        output_path,
    ]
    logger.info("Rendering clip: %.1fs–%.1fs → %s", start, end, output_path)
    subprocess.run(cmd, capture_output=True, text=True, check=True)
    return output_path


def burn_captions(
    clip_path: str,
    srt_path: str,
    output_path: str,
    style: CaptionStyle,
) -> str:
    """Burn SRT subtitles into a video clip using the ffmpeg subtitles filter."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # ffmpeg subtitles filter requires escaping colons and backslashes in paths
    escaped_srt = srt_path.replace("\\", "\\\\").replace(":", "\\:")

    force_style = (
        f"FontName={style.font},"
        f"FontSize={style.font_size},"
        f"PrimaryColour=&H00FFFFFF,"
        f"OutlineColour=&H00000000,"
        f"Outline={style.outline_width},"
        f"Alignment=2,"
        f"MarginV=30"
    )

    vf = f"subtitles='{escaped_srt}':force_style='{force_style}'"

    cmd = [
        "ffmpeg",
        "-y",
        "-i", clip_path,
        "-vf", vf,
        "-c:v", "libx264",
        "-c:a", "copy",
        "-preset", "fast",
        "-movflags", "+faststart",
        output_path,
    ]
    logger.info("Burning captions into: %s", output_path)
    subprocess.run(cmd, capture_output=True, text=True, check=True)
    return output_path


def build_clip_output_path(output_dir: str, job_id: int, clip_index: int, suffix: str = "") -> str:
    """Build a consistent output path for a clip file."""
    filename = f"job{job_id}_clip{clip_index:03d}{suffix}.mp4"
    return str(Path(output_dir) / filename)
