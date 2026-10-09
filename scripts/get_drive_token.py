"""Generate a Google Drive OAuth refresh token for the platform account.

WHY: the app uploads/downloads books with ONE platform Google account via an
OAuth refresh token (see backend/app/services/google_drive_service.py). If the
OAuth consent screen is in "Testing" mode, Google expires that refresh token
after ~7 days — regenerate it with this script.

PREREQUISITES (one time):
  1. Google Cloud Console -> APIs & Services -> Library -> enable "Google Drive API".
  2. APIs & Services -> OAuth consent screen -> add the platform Google account
     as a "Test user" (or publish the app to stop tokens expiring every 7 days).
  3. APIs & Services -> Credentials -> Create credentials -> OAuth client ID
     -> Application type: "Desktop app".
     (If you already have a Web client, add http://localhost:8080/ to its
      "Authorized redirect URIs" and reuse it.)

USAGE:
  pip install google-auth-oauthlib
  # make sure GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET are set in backend/.env
  python scripts/get_drive_token.py

  Then sign in with the PLATFORM Google account and copy the printed refresh
  token into:
    - backend/.env            -> GOOGLE_REFRESH_TOKEN=...
    - Vercel (bookai-api)     -> GOOGLE_REFRESH_TOKEN  (Settings -> Env Vars)
  and redeploy the API.
"""

import os

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/drive"]


def _load_client():
    cid = os.environ.get("GOOGLE_CLIENT_ID")
    secret = os.environ.get("GOOGLE_CLIENT_SECRET")
    if cid and secret:
        return cid, secret
    for path in ("backend/.env", ".env"):
        if not os.path.exists(path):
            continue
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line.startswith("GOOGLE_CLIENT_ID="):
                cid = line.split("=", 1)[1].strip().strip("'\"")
            elif line.startswith("GOOGLE_CLIENT_SECRET="):
                secret = line.split("=", 1)[1].strip().strip("'\"")
        break
    return cid, secret


def main():
    cid, secret = _load_client()
    if not cid or not secret:
        raise SystemExit(
            "Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET (in backend/.env or the shell)."
        )

    flow = InstalledAppFlow.from_client_config(
        {
            "installed": {
                "client_id": cid,
                "client_secret": secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": ["http://localhost"],
            }
        },
        scopes=SCOPES,
    )
    creds = flow.run_local_server(port=8080, access_type="offline", prompt="consent")

    print("\n" + "=" * 60)
    print("GOOGLE_REFRESH_TOKEN=" + (creds.refresh_token or "(none returned)"))
    print("=" * 60)
    print("Add it to backend/.env AND the Vercel env vars, then redeploy.")


if __name__ == "__main__":
    main()
