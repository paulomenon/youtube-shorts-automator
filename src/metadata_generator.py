import json
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a YouTube Shorts metadata expert. Given a transcript from a short video clip, generate engaging metadata optimized for YouTube Shorts discovery.

Return a JSON object with exactly these keys:
- "title": A catchy, concise title (max 100 characters). Do not include hashtags in the title.
- "description": A brief, engaging description (2-3 sentences, max 500 characters).
- "hashtags": A list of 5-10 relevant hashtags as strings (without the # symbol).

Return ONLY valid JSON, no markdown formatting or extra text."""


@dataclass
class ShortMetadata:
    title: str
    description: str
    hashtags: list[str]

    @property
    def hashtags_str(self) -> str:
        return " ".join(f"#{tag}" for tag in self.hashtags)

    @property
    def full_description(self) -> str:
        return f"{self.description}\n\n{self.hashtags_str}"


def generate_metadata(transcript: str, api_key: str, source_filename: str = "") -> ShortMetadata:
    """
    Generate title, description, and hashtags for a YouTube Short
    using the OpenAI API based on the clip transcript.
    """
    if not api_key:
        logger.warning("No OpenAI API key configured — using fallback metadata")
        return _fallback_metadata(transcript, source_filename)

    from openai import OpenAI

    client = OpenAI(api_key=api_key)

    user_content = f"Source video: {source_filename}\n\nTranscript:\n{transcript}" if source_filename else f"Transcript:\n{transcript}"

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0.7,
            max_tokens=500,
            response_format={"type": "json_object"},
        )

        raw = response.choices[0].message.content.strip()
        data = json.loads(raw)

        return ShortMetadata(
            title=data.get("title", "Untitled Short")[:100],
            description=data.get("description", "")[:500],
            hashtags=data.get("hashtags", ["shorts", "youtube"]),
        )
    except Exception as e:
        logger.error("Metadata generation failed: %s — using fallback", e)
        return _fallback_metadata(transcript, source_filename)


def _fallback_metadata(transcript: str, source_filename: str = "") -> ShortMetadata:
    """Generate basic metadata without an LLM when the API is unavailable."""
    preview = transcript[:80].strip() if transcript else "Video clip"
    title = preview if len(preview) <= 100 else preview[:97] + "..."

    name = source_filename.rsplit(".", 1)[0] if source_filename else "video"

    return ShortMetadata(
        title=title,
        description=f"Short clip from {name}.",
        hashtags=["shorts", "youtube", "clips"],
    )
