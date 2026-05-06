"""YouTube Shorts upload via the YouTube Data API v3.

Setup (once):
  1. Google Cloud project, enable "YouTube Data API v3".
  2. Create OAuth client (Type: "Desktop app"), download as client_secret.json.
  3. Drop the file at the path in YT_CLIENT_SECRET (default: ./secrets/client_secret.json).
  4. First run opens a browser to authorize; token cached to YT_TOKEN_CACHE.

Quota: videos.insert costs 1600 units; default daily quota is 10,000 -> ~6 uploads/day.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from .config import Config
from .script import VideoScript

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


@dataclass
class UploadResult:
    video_id: str
    url: str
    privacy: str


def _credentials(cfg: Config) -> Credentials:
    if not cfg.yt_client_secret.exists():
        raise RuntimeError(
            f"YT_CLIENT_SECRET not found at {cfg.yt_client_secret}. "
            "Download OAuth client (Desktop app) from Google Cloud Console."
        )

    cfg.yt_token_cache.parent.mkdir(parents=True, exist_ok=True)

    creds: Credentials | None = None
    if cfg.yt_token_cache.exists():
        creds = Credentials.from_authorized_user_file(
            str(cfg.yt_token_cache), SCOPES
        )

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    else:
        flow = InstalledAppFlow.from_client_secrets_file(
            str(cfg.yt_client_secret), SCOPES
        )
        creds = flow.run_local_server(port=0)

    cfg.yt_token_cache.write_text(creds.to_json(), encoding="utf-8")
    return creds


def _build_metadata(
    title: str,
    description: str,
    tags: list[str],
    *,
    category_id: str,
    language: str,
    privacy: str,
    made_for_kids: bool,
) -> dict:
    if "#shorts" not in title.lower() and "#short" not in title.lower():
        suffix = " #Shorts"
        title = (title[: 100 - len(suffix)] + suffix) if len(title) + len(suffix) > 100 else title + suffix

    return {
        "snippet": {
            "title": title[:100],
            "description": description[:5000],
            "tags": tags[:30],
            "categoryId": category_id,
            "defaultLanguage": language,
            "defaultAudioLanguage": language,
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": made_for_kids,
            "embeddable": True,
        },
    }


def upload(
    cfg: Config,
    video_path: Path,
    *,
    title: str,
    description: str,
    tags: list[str],
    privacy: str | None = None,
    category_id: str | None = None,
    language: str | None = None,
    made_for_kids: bool = False,
) -> UploadResult:
    """Upload a single video file as a Short."""
    if not video_path.exists():
        raise FileNotFoundError(video_path)

    privacy = (privacy or cfg.yt_default_privacy).lower()
    if privacy not in ("private", "unlisted", "public"):
        raise ValueError(f"privacy must be private/unlisted/public, got {privacy}")

    body = _build_metadata(
        title=title,
        description=description,
        tags=tags,
        category_id=category_id or cfg.yt_default_category,
        language=language or cfg.yt_default_language,
        privacy=privacy,
        made_for_kids=made_for_kids,
    )

    creds = _credentials(cfg)
    youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)

    media = MediaFileUpload(
        str(video_path), chunksize=8 * 1024 * 1024, resumable=True, mimetype="video/mp4"
    )
    request = youtube.videos().insert(
        part="snippet,status", body=body, media_body=media
    )

    response = None
    while response is None:
        _status, response = request.next_chunk()

    video_id = response["id"]
    return UploadResult(
        video_id=video_id,
        url=f"https://youtube.com/shorts/{video_id}",
        privacy=privacy,
    )


def upload_from_script(
    cfg: Config,
    video_path: Path,
    script: VideoScript,
    *,
    privacy: str | None = None,
) -> UploadResult:
    """Convenience wrapper: pull title/description/tags from a VideoScript."""
    return upload(
        cfg,
        video_path,
        title=script.title,
        description=script.description,
        tags=script.tags,
        privacy=privacy,
    )
