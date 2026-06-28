from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from pipeline.config import YOUTUBE_CLIENT_SECRET_FILE, YOUTUBE_TOKEN_FILE

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def get_authenticated_service():
    """Loads cached OAuth credentials, or runs the interactive consent flow once.

    Run `python -m pipeline.youtube_upload --authorize` once locally/manually to
    perform the one-time OAuth login. After that, the cached token at
    YOUTUBE_TOKEN_FILE is reused automatically (and refreshed) for daily uploads.
    """
    creds = None
    if YOUTUBE_TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(YOUTUBE_TOKEN_FILE), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not YOUTUBE_CLIENT_SECRET_FILE.exists():
                raise RuntimeError(
                    f"No cached token and no client secret file found at "
                    f"{YOUTUBE_CLIENT_SECRET_FILE}. Download OAuth client credentials "
                    f"from Google Cloud Console (Desktop app type) and place them there, "
                    f"then run: python -m pipeline.youtube_upload --authorize"
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(YOUTUBE_CLIENT_SECRET_FILE), SCOPES)
            creds = flow.run_local_server(port=0)
        YOUTUBE_TOKEN_FILE.write_text(creds.to_json())

    return build("youtube", "v3", credentials=creds)


def upload_video(
    video_path: Path,
    title: str,
    description: str,
    tags: list[str],
    thumbnail_path: Path | None = None,
    category_id: str = "27",  # Education
    privacy_status: str = "public",
) -> str:
    youtube = get_authenticated_service()

    body = {
        "snippet": {
            "title": title[:100],
            "description": description[:4900],
            "tags": tags[:500],
            "categoryId": category_id,
            "defaultLanguage": "ar",
            "defaultAudioLanguage": "ar",
        },
        "status": {
            "privacyStatus": privacy_status,
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(str(video_path), chunksize=-1, resumable=True, mimetype="video/mp4")
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"Upload progress: {int(status.progress() * 100)}%")

    video_id = response["id"]
    print(f"Uploaded video id: {video_id}")

    if thumbnail_path and thumbnail_path.exists():
        youtube.thumbnails().set(
            videoId=video_id, media_body=MediaFileUpload(str(thumbnail_path))
        ).execute()

    return video_id


if __name__ == "__main__":
    import sys

    if "--authorize" in sys.argv:
        get_authenticated_service()
        print(f"Authorization complete. Token saved to {YOUTUBE_TOKEN_FILE}")
    else:
        print("Usage: python -m pipeline.youtube_upload --authorize")
