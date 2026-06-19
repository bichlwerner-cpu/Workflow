"""Optional YouTube uploader (Data API v3) for finished episodes.

Reads an episode's ``metadata.json`` and uploads ``video.mp4`` with the title,
description, tags, category, privacy and (optionally) a scheduled ``publishAt``,
then sets the thumbnail.

This needs Google OAuth, which can't run unattended without first authorising
once in a browser:

  1. Create an OAuth *Desktop* client in Google Cloud Console (enable the
     "YouTube Data API v3"), download ``client_secret.json``.
  2. ``pip install google-api-python-client google-auth-oauthlib``
  3. ``yt-automation channel upload <episode_dir> --client-secret client_secret.json``
     (first run opens a browser; the token is cached for later headless runs.)

``--dry-run`` validates everything and prints the upload plan without any
network calls or Google libraries.
"""

from __future__ import annotations

import json
from pathlib import Path

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def load_plan(episode_dir: Path) -> tuple[dict, Path, Path | None]:
    """Return (metadata, video_path, thumbnail_path) for an episode directory."""
    meta_path = episode_dir / "metadata.json"
    if not meta_path.exists():
        raise FileNotFoundError(f"No metadata.json in {episode_dir}")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    files = meta.get("files", {})
    video = episode_dir / files.get("video", "video.mp4")
    if not video.exists():
        raise FileNotFoundError(f"Video not found: {video}")
    thumb = episode_dir / files.get("thumbnail", "thumbnail.jpg")
    return meta, video, (thumb if thumb.exists() else None)


def describe_plan(meta: dict, video: Path, thumb: Path | None) -> str:
    lines = [
        f"  title      : {meta.get('title')}",
        f"  privacy    : {meta.get('privacyStatus')}",
        f"  category   : {meta.get('categoryId')}",
        f"  publishAt  : {meta.get('publishAt') or '(immediately)'}",
        f"  tags       : {', '.join(meta.get('tags', [])[:8])}",
        f"  video      : {video}  ({video.stat().st_size / 1e6:.1f} MB)",
        f"  thumbnail  : {thumb if thumb else '(none)'}",
    ]
    return "\n".join(lines)


def _get_credentials(client_secret: Path, token_store: Path):
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError as e:  # pragma: no cover - depends on optional extras
        raise RuntimeError(
            "YouTube upload needs google libraries. Install with:\n"
            "  pip install google-api-python-client google-auth-oauthlib"
        ) from e

    creds = None
    if token_store.exists():
        creds = Credentials.from_authorized_user_file(str(token_store), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(client_secret), SCOPES)
            creds = flow.run_local_server(port=0)
        token_store.write_text(creds.to_json(), encoding="utf-8")
    return creds


def upload_episode(
    episode_dir: Path,
    *,
    client_secret: Path,
    token_store: Path | None = None,
    dry_run: bool = False,
) -> str | None:
    """Upload one episode. Returns the new video id, or None for a dry run."""
    meta, video, thumb = load_plan(episode_dir)
    if dry_run:
        return None

    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    token_store = token_store or (episode_dir.parent / ".youtube_token.json")
    creds = _get_credentials(client_secret, token_store)
    youtube = build("youtube", "v3", credentials=creds)

    status = {"privacyStatus": meta.get("privacyStatus", "private"),
              "selfDeclaredMadeForKids": bool(meta.get("madeForKids", False))}
    if meta.get("publishAt"):
        status["publishAt"] = meta["publishAt"]
        status["privacyStatus"] = "private"  # required for scheduled uploads

    body = {
        "snippet": {
            "title": meta["title"],
            "description": meta.get("description", ""),
            "tags": meta.get("tags", []),
            "categoryId": str(meta.get("categoryId", "27")),
            "defaultLanguage": meta.get("language", "en"),
        },
        "status": status,
    }
    media = MediaFileUpload(str(video), chunksize=-1, resumable=True, mimetype="video/mp4")
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        _status, response = request.next_chunk()
    video_id = response["id"]

    if thumb is not None:
        youtube.thumbnails().set(
            videoId=video_id,
            media_body=MediaFileUpload(str(thumb), mimetype="image/jpeg"),
        ).execute()
    return video_id
