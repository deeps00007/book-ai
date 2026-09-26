"""
Google Drive storage via a Service Account.

Flow for large uploads (no Vercel body limit, no 50MB cap):
  1. Backend creates a resumable upload session -> returns session URI + file_id
  2. Browser PUTs the file directly to Google Drive (streamed, any size)
  3. Backend downloads by file_id ONCE during processing, extracts, indexes
"""

import json
import logging
import httpx
from app.core.config import settings

logger = logging.getLogger(__name__)

DRIVE_API = "https://www.googleapis.com/drive/v3"
DRIVE_UPLOAD = "https://www.googleapis.com/upload/drive/v3"
SCOPES = ["https://www.googleapis.com/auth/drive"]

_cached_creds = None


def _get_credentials():
    global _cached_creds
    if _cached_creds is not None:
        return _cached_creds

    # Preferred: single platform Google account via refresh token (uses that account's quota)
    if (settings.google_refresh_token or '').strip() and (settings.google_client_id or '').strip() and (settings.google_client_secret or '').strip():
        from google.oauth2.credentials import Credentials
        _cached_creds = Credentials(
            token=None,
            refresh_token=(settings.google_refresh_token or '').strip(),
            client_id=(settings.google_client_id or '').strip(),
            client_secret=(settings.google_client_secret or '').strip(),
            token_uri="https://oauth2.googleapis.com/token",
            scopes=SCOPES,
        )
        return _cached_creds

    # Fallback: service account (only works with a Shared Drive)
    from google.oauth2 import service_account
    info = json.loads((settings.google_service_account_json or '').strip())
    _cached_creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    return _cached_creds


def _get_access_token() -> str:
    from google.auth.transport.requests import Request
    creds = _get_credentials()
    if not creds.valid:
        creds.refresh(Request())
    return creds.token


def is_configured() -> bool:
    using_oauth = bool(
        settings.google_refresh_token
        and settings.google_client_id
        and settings.google_client_secret
    )
    return using_oauth or bool(settings.google_service_account_json)


async def create_resumable_upload_session(
    filename: str, mime_type: str = "application/pdf", origin: str | None = None
) -> dict:
    """Create a resumable upload session. Returns {upload_url}.

    `origin` MUST be the browser's origin so Google enables CORS on the
    upload session for that browser (otherwise the PUT is blocked).
    """
    token = _get_access_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    if origin:
        headers["Origin"] = origin
    metadata = {"name": filename, "mimeType": mime_type}
    if (settings.google_drive_folder_id or '').strip():
        metadata["parents"] = [settings.google_drive_folder_id]

    params = {"uploadType": "resumable", "supportsAllDrives": "true", "fields": "id,name"}

    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            f"{DRIVE_UPLOAD}/files",
            headers=headers,
            params=params,
            json=metadata,
        )
        r.raise_for_status()
        upload_url = r.headers.get("Location")
        if not upload_url:
            raise RuntimeError("Drive did not return an upload session URI")
        return {"upload_url": upload_url}


async def get_file_metadata(file_id: str) -> dict:
    token = _get_access_token()
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.get(
            f"{DRIVE_API}/files/{file_id}",
            headers={"Authorization": f"Bearer {token}"},
            params={"fields": "id,name,size,mimeType", "supportsAllDrives": "true"},
        )
        r.raise_for_status()
        return r.json()


async def download_file(file_id: str) -> bytes:
    """Download the entire file ONCE for processing."""
    token = _get_access_token()
    async with httpx.AsyncClient(timeout=600, follow_redirects=True) as client:
        r = await client.get(
            f"{DRIVE_API}/files/{file_id}",
            headers={"Authorization": f"Bearer {token}"},
            params={"alt": "media", "supportsAllDrives": "true"},
        )
        r.raise_for_status()
        return r.content


async def delete_file(file_id: str) -> bool:
    token = _get_access_token()
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.delete(
                f"{DRIVE_API}/files/{file_id}",
                headers={"Authorization": f"Bearer {token}"},
                params={"supportsAllDrives": "true"},
            )
            return r.status_code in (204, 200)
    except Exception as e:
        logger.warning(f"Failed to delete Drive file {file_id}: {e}")
        return False
