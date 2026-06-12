"""Optional YouTube upload via the YouTube Data API v3.

Setup (one-time):
  1. Google Cloud Console -> create project -> enable "YouTube Data API v3"
  2. OAuth consent screen -> add yourself as test user
  3. Credentials -> create OAuth client ID (Desktop app) -> download JSON
  4. Save it as client_secrets.json (or set YOUTUBE_CLIENT_SECRETS in .env)

First upload opens a browser for consent; the token is cached in .secrets/.
"""

from __future__ import annotations

import os
from pathlib import Path

from .config import ROOT

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
TOKEN_PATH = ROOT / ".secrets" / "youtube_token.json"


def _get_service():
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError:
        raise SystemExit(
            "YouTube upload requires the Google API packages:\n"
            "  pip install google-api-python-client google-auth-oauthlib"
        )

    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            secrets = os.environ.get("YOUTUBE_CLIENT_SECRETS", "client_secrets.json")
            secrets_path = Path(secrets)
            if not secrets_path.is_absolute():
                secrets_path = ROOT / secrets_path
            if not secrets_path.exists():
                raise SystemExit(
                    f"OAuth client secrets not found at {secrets_path}. "
                    f"See pipeline/upload.py docstring for setup."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(secrets_path), SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN_PATH.parent.mkdir(exist_ok=True)
        TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
    return build("youtube", "v3", credentials=creds)


def upload_video(meta: dict, video_path: Path, thumbnail_path: Path, log=print) -> str:
    from googleapiclient.http import MediaFileUpload

    service = _get_service()
    body = {
        "snippet": {
            "title": meta["title"],
            "description": meta["description"],
            "tags": meta.get("tags", []),
            "categoryId": meta.get("category_id", "27"),
        },
        "status": {
            "privacyStatus": meta.get("privacy_status", "private"),
            "selfDeclaredMadeForKids": bool(meta.get("made_for_kids", False)),
        },
    }
    media = MediaFileUpload(str(video_path), chunksize=8 * 1024 * 1024, resumable=True)
    request = service.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            log(f"    [upload] {int(status.progress() * 100)}%")
    video_id = response["id"]
    log(f"    [upload] video id: {video_id}")

    if thumbnail_path.exists():
        service.thumbnails().set(
            videoId=video_id,
            media_body=MediaFileUpload(str(thumbnail_path)),
        ).execute()
        log("    [upload] thumbnail set")

    log(f"    [upload] https://studio.youtube.com/video/{video_id}/edit")
    return video_id
