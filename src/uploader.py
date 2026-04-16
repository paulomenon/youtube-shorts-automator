import logging
import os
import time
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]
TOKEN_PATH = "token.json"
MAX_RETRIES = 3
BASE_BACKOFF = 60  # seconds


def _get_authenticated_service(client_secrets_path: str):
    """Build an authenticated YouTube API service using OAuth2."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    creds = None

    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(client_secrets_path):
                raise FileNotFoundError(
                    f"YouTube client secrets not found at {client_secrets_path}. "
                    "Download from Google Cloud Console."
                )
            flow = InstalledAppFlow.from_client_secrets_file(client_secrets_path, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(TOKEN_PATH, "w") as f:
            f.write(creds.to_json())

    return build("youtube", "v3", credentials=creds)


def upload_short(
    filepath: str,
    title: str,
    description: str,
    tags: list[str],
    publish_at: Optional[datetime],
    client_secrets_path: str,
    privacy_status: str = "private",
) -> str:
    """
    Upload a video to YouTube.

    Args:
        privacy_status: "private", "public", or "unlisted" (default: "private").

    Returns the YouTube video ID on success.
    Raises on unrecoverable failure.
    """
    youtube = _get_authenticated_service(client_secrets_path)

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": "22",  # People & Blogs
        },
        "status": {
            "privacyStatus": privacy_status,
            "selfDeclaredMadeForKids": False,
        },
    }

    if publish_at:
        body["status"]["publishAt"] = publish_at.strftime("%Y-%m-%dT%H:%M:%S.000Z")

    from googleapiclient.http import MediaFileUpload

    media = MediaFileUpload(filepath, mimetype="video/mp4", resumable=True)

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    logger.info("Uploading %s as '%s'…", filepath, title)
    response = _execute_with_retry(request)

    video_id = response["id"]
    logger.info("Upload complete — YouTube ID: %s", video_id)
    return video_id


def upload_caption_track(
    video_id: str,
    srt_path: str,
    language: str,
    client_secrets_path: str,
    name: str = "",
) -> str:
    """Upload an SRT file as a caption track on an existing YouTube video."""
    from googleapiclient.http import MediaFileUpload

    youtube = _get_authenticated_service(client_secrets_path)

    body = {
        "snippet": {
            "videoId": video_id,
            "language": language,
            "name": name or f"Captions ({language})",
            "isDraft": False,
        },
    }

    media = MediaFileUpload(srt_path, mimetype="application/x-subrip", resumable=True)

    request = youtube.captions().insert(
        part="snippet",
        body=body,
        media_body=media,
    )

    logger.info("Uploading caption track for video %s from %s", video_id, srt_path)
    response = _execute_with_retry(request)
    caption_id = response["id"]
    logger.info("Caption track uploaded — ID: %s", caption_id)
    return caption_id


def _execute_with_retry(request, max_retries: int = MAX_RETRIES) -> dict:
    """Execute a resumable upload with exponential backoff on transient errors."""
    response = None
    for attempt in range(max_retries):
        try:
            status, response = request.next_chunk()
            while response is None:
                status, response = request.next_chunk()
            return response
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            wait = BASE_BACKOFF * (2 ** attempt)
            logger.warning(
                "Upload attempt %d failed: %s — retrying in %ds",
                attempt + 1, e, wait,
            )
            time.sleep(wait)

    return response
