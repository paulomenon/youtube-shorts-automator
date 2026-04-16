import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


def _format_timestamp(seconds: float) -> str:
    """Convert seconds to SRT timestamp format (HH:MM:SS,mmm)."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _segments_to_srt(segments: list[dict]) -> str:
    """Convert Whisper segments to SRT subtitle format."""
    lines = []
    for i, seg in enumerate(segments, start=1):
        start = _format_timestamp(seg["start"])
        end = _format_timestamp(seg["end"])
        text = seg["text"].strip()
        lines.append(f"{i}\n{start} --> {end}\n{text}\n")
    return "\n".join(lines)


def transcribe_clip(clip_path: str, model_name: str = "base") -> tuple[str, str]:
    """
    Transcribe a video clip using Whisper and return (srt_content, transcript_text).

    The SRT file is written alongside the clip with the same base name.
    """
    import whisper

    logger.info("Transcribing: %s (model=%s)", clip_path, model_name)

    model = whisper.load_model(model_name)
    result = model.transcribe(clip_path, verbose=False)

    segments = result.get("segments", [])
    srt_content = _segments_to_srt(segments)
    transcript = result.get("text", "").strip()

    srt_path = str(Path(clip_path).with_suffix(".srt"))
    with open(srt_path, "w", encoding="utf-8") as f:
        f.write(srt_content)

    logger.info("Captions written to: %s (%d segments)", srt_path, len(segments))
    return srt_path, transcript


def transcribe_clip_segment(
    video_path: str,
    start: float,
    end: float,
    output_srt_path: str,
    model_name: str = "base",
) -> tuple[str, str]:
    """
    Transcribe a specific segment of a video by first extracting audio,
    then running Whisper on it. Returns (srt_path, transcript_text).
    """
    import whisper
    import subprocess
    import tempfile

    logger.info("Transcribing segment %.1fs–%.1fs of %s", start, end, video_path)

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_audio = tmp.name

    try:
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-ss", str(start),
                "-i", video_path,
                "-t", str(end - start),
                "-vn",
                "-acodec", "pcm_s16le",
                "-ar", "16000",
                "-ac", "1",
                tmp_audio,
            ],
            capture_output=True,
            text=True,
            check=True,
        )

        model = whisper.load_model(model_name)
        result = model.transcribe(tmp_audio, verbose=False)
    finally:
        if os.path.exists(tmp_audio):
            os.unlink(tmp_audio)

    segments = result.get("segments", [])
    srt_content = _segments_to_srt(segments)
    transcript = result.get("text", "").strip()

    os.makedirs(os.path.dirname(output_srt_path), exist_ok=True)
    with open(output_srt_path, "w", encoding="utf-8") as f:
        f.write(srt_content)

    logger.info("Captions written to: %s (%d segments)", output_srt_path, len(segments))
    return output_srt_path, transcript
