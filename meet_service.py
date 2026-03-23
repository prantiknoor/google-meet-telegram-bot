"""
Google Meet API service.
Creates a meeting space with:
  - Access type: OPEN  (anyone with the link can join)
"""

import os
import logging
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.apps import meet_v2

logger = logging.getLogger(__name__)

# Scopes required to create AND configure spaces
SCOPES = [
    "https://www.googleapis.com/auth/meetings.space.created",
]

CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
TOKEN_FILE = os.getenv("GOOGLE_TOKEN_FILE", "token.json")


def _get_credentials() -> Credentials:
    """Load or refresh OAuth2 credentials, running the auth flow if needed."""
    creds = None

    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            logger.info("Refreshed Google OAuth token.")
        else:
            if not os.path.exists(CREDENTIALS_FILE):
                raise FileNotFoundError(
                    f"Google credentials file not found: '{CREDENTIALS_FILE}'. "
                    "Download it from Google Cloud Console and place it next to bot.py."
                )
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
            logger.info("New Google OAuth token obtained via browser flow.")

        with open(TOKEN_FILE, "w") as fh:
            fh.write(creds.to_json())

    return creds


def create_meet_space() -> dict:
    """
    Create a Google Meet space.

    Returns a dict with:
        name          - resource name  (e.g. "spaces/abc123")
        meeting_uri   - the full Meet URL
        meeting_code  - short join code
    """
    creds = _get_credentials()
    client = meet_v2.SpacesServiceClient(credentials=creds)

    # ── Step 1: Create the space ─────────────────────────────────────────────
    space_config = meet_v2.SpaceConfig(
        access_type=meet_v2.SpaceConfig.AccessType.OPEN,
    )
    space = meet_v2.Space(config=space_config)
    request = meet_v2.CreateSpaceRequest(space=space)
    response = client.create_space(request=request)

    logger.info("Space created: %s  URI: %s", response.name, response.meeting_uri)

    return {
        "name": response.name,
        "meeting_uri": response.meeting_uri,
        "meeting_code": response.meeting_code,
    }
