from pathlib import Path
from typing import Optional

SCOPES = ["https://www.googleapis.com/auth/calendar"]


def _get_google_credentials(credentials_file: str, token_file: str):
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError as exc:
        raise ImportError(
            "Google sync dependencies missing. Install: google-api-python-client google-auth-oauthlib icalendar"
        ) from exc

    creds: Optional[Credentials] = None
    token_path = Path(token_file)

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(credentials_file, SCOPES)
            creds = flow.run_local_server(port=0)

        token_path.write_text(creds.to_json(), encoding="utf-8")

    return creds


def sync_ical_to_google_calendar(
    ics_path: str,
    credentials_file: str,
    token_file: str = "google_token.json",
    calendar_id: str = "primary",
) -> int:
    try:
        from googleapiclient.discovery import build
        from icalendar import Calendar
    except ImportError as exc:
        raise ImportError(
            "Google sync dependencies missing. Install: google-api-python-client google-auth-oauthlib icalendar"
        ) from exc

    ics_file = Path(ics_path)
    if not ics_file.exists() or not ics_file.is_file():
        raise FileNotFoundError(f"ICS file not found: {ics_file}")

    creds = _get_google_credentials(credentials_file, token_file)
    service = build("calendar", "v3", credentials=creds)

    with open(ics_file, "rb") as file_handle:
        calendar = Calendar.from_ical(file_handle.read())

    inserted = 0
    for component in calendar.walk():
        if component.name != "VEVENT":
            continue

        summary = str(component.get("summary", "Untitled Event"))
        location = str(component.get("location", ""))
        description = str(component.get("description", ""))

        dtstart = component.get("dtstart")
        dtend = component.get("dtend")
        if not dtstart or not dtend:
            continue

        start_value = dtstart.dt
        end_value = dtend.dt

        if hasattr(start_value, "hour"):
            start_obj = {"dateTime": start_value.isoformat()}
            end_obj = {"dateTime": end_value.isoformat()}
        else:
            start_obj = {"date": start_value.isoformat()}
            end_obj = {"date": end_value.isoformat()}

        event_body = {
            "summary": summary,
            "location": location,
            "description": description,
            "start": start_obj,
            "end": end_obj,
        }

        service.events().insert(calendarId=calendar_id, body=event_body).execute()
        inserted += 1

    return inserted
