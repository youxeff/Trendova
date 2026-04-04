import os
import json
from pathlib import Path
from urllib.parse import quote
from zipfile import ZipFile
from xml.etree import ElementTree as ET

from flask import Flask, redirect, render_template_string, request, session, url_for

from Model.syllabus_pipeline.brightspace_ics_client import (
    download_ics_feed,
    ics_events_to_workflow,
    load_ics_events,
)
from Model.syllabus_pipeline.gmail_connector import SCOPES, sync_ical_to_google_calendar
from Model.syllabus_pipeline.ical_converter import workflow_to_ical
from Model.syllabus_pipeline.gemini_client import extract_deadlines_with_gemini, extract_deadlines_from_text_with_gemini
from Model.syllabus_pipeline.format_converter import convert_rows_to_workflow_format

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret-change-me")

APP_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = APP_DIR / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

GOOGLE_CREDENTIALS_FILE = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", str(APP_DIR / "google_client_secret.json"))
GOOGLE_TOKEN_FILE = os.getenv("GOOGLE_TOKEN_FILE", str(OUTPUT_DIR / "web_google_token.json"))
DEFAULT_BRIGHTSPACE_BASE_URL = os.getenv("BRIGHTSPACE_BASE_URL", "https://purdue.brightspace.com")
GOOGLE_OAUTH_REDIRECT_URI = os.getenv("GOOGLE_OAUTH_REDIRECT_URI", "http://localhost:5050/google/callback")


def _build_env_google_client_config() -> dict:
  client_id = (os.getenv("GOOGLE_OAUTH_CLIENT_ID") or "").strip()
  client_secret = (os.getenv("GOOGLE_OAUTH_CLIENT_SECRET_VALUE") or "").strip()
  project_id = (os.getenv("GOOGLE_OAUTH_PROJECT_ID") or "").strip()

  if not client_id or not client_secret:
    return {}

  return {
    "web": {
      "client_id": client_id,
      "project_id": project_id,
      "auth_uri": "https://accounts.google.com/o/oauth2/auth",
      "token_uri": "https://oauth2.googleapis.com/token",
      "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
      "client_secret": client_secret,
      "redirect_uris": [
        "http://localhost:5050/google/callback",
        "http://127.0.0.1:5050/google/callback",
      ],
    }
  }


HARDCODED_GOOGLE_CLIENT_CONFIG = _build_env_google_client_config()


HTML = """
<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>Brightspace → Google Calendar</title>
    <style>
      body { font-family: Arial, sans-serif; max-width: 880px; margin: 30px auto; padding: 0 16px; }
      .card { border: 1px solid #ddd; border-radius: 8px; padding: 16px; margin-bottom: 16px; }
      .row { margin-bottom: 10px; }
      input[type=text] { width: 100%; padding: 8px; }
      button { padding: 10px 14px; cursor: pointer; }
      .ok { color: #0a7d24; }
      .warn { color: #ad1f1f; }
      .hint { color: #555; font-size: 14px; }
      pre { white-space: pre-wrap; background: #f6f6f6; padding: 12px; border-radius: 8px; }
      code { background: #f2f2f2; padding: 2px 4px; border-radius: 4px; }
    </style>
  </head>
  <body>
    <h2>Brightspace Calendar Sync</h2>
    <div class="card">
      <div class="row">
        <strong>Google Calendar:</strong>
        {% if connected %}
          <span class="ok">Connected</span>
          {% if connected_account %}
            <span class="ok">({{ connected_account }})</span>
          {% endif %}
        {% else %}
          <span class="warn">Not connected</span>
        {% endif %}
      </div>
      <div class="row hint">{{ connection_detail }}</div>
      <a href="{{ url_for('google_connect') }}"><button>Connect Google Calendar</button></a>
    </div>

    {% if not oauth_ready %}
    <div class="card">
      <h3>One-time Google setup</h3>
      <p class="hint">
        Upload your Google OAuth desktop client secret JSON here, then click <strong>Connect Google Calendar</strong>.
        This keeps the flow button-based without manual file copying.
      </p>
      <form method="post" action="{{ url_for('upload_google_credentials') }}" enctype="multipart/form-data">
        <div class="row">
          <input type="file" name="oauth_file" accept="application/json" required />
        </div>
        <button type="submit">Upload Google OAuth JSON</button>
      </form>
    </div>
    {% endif %}

    <div class="card">
      <form method="post" action="{{ url_for('sync') }}">
        <div class="row">
          <label>Brightspace base URL</label>
          <input type="text" name="base_url" value="{{ base_url }}" />
        </div>
        <div class="row">
          <label>Brightspace token or full ICS URL</label>
          <input type="text" name="token" placeholder="Paste feed token or full feed URL" required />
        </div>
        <div class="row">
          <label>Subject label</label>
          <input type="text" name="subject" value="Purdue Brightspace" />
        </div>
        <button type="submit">Sync to Google Calendar</button>
      </form>
    </div>

    <div class="card">
      <h3>Upload Syllabus (PDF/DOCX) → Gemini</h3>
      <form method="post" action="{{ url_for('extract_deadlines') }}" enctype="multipart/form-data">
        <div class="row">
          <label>File (.pdf or .docx)</label>
          <input type="file" name="syllabus_file" accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document" required />
        </div>
        <div class="row">
          <label>Gemini API key (optional if GEMINI_API_KEY env var is set)</label>
          <input type="text" name="gemini_api_key" placeholder="AIza..." />
        </div>
        <div class="row">
          <label>Gemini model</label>
          <input type="text" name="llm_model" value="gemini-3-flash-preview" />
        </div>
        <div class="row">
          <label>
            <input type="checkbox" name="sync_to_google" checked />
            Sync extracted deadlines to Google Calendar (requires connected Google account)
          </label>
        </div>
        <button type="submit">Extract Deadlines with Gemini</button>
      </form>
    </div>

    {% if message %}
      <div class="card"><strong>{{ message }}</strong></div>
    {% endif %}

    {% if events_text %}
      <div class="card">
        <h3>Events (Plaintext)</h3>
        <pre>{{ events_text }}</pre>
      </div>
    {% endif %}

    {% if gemini_rows_text %}
      <div class="card">
        <h3>Gemini Extracted Rows</h3>
        <pre>{{ gemini_rows_text }}</pre>
      </div>
    {% endif %}

    <p>
      Expected Google OAuth client secret path: <code>{{ credentials_file }}</code><br/>
      Token cache path: <code>{{ token_file }}</code>
    </p>
  </body>
</html>
"""


def _get_google_connection_status() -> tuple[bool, str, str]:
    token_path = Path(GOOGLE_TOKEN_FILE)
    if not token_path.exists():
        return False, "", f"No token file found at {token_path}"

    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            token_path.write_text(creds.to_json(), encoding="utf-8")
        if not creds.valid:
            return False, "", "Token file exists but credentials are not valid."

        try:
            service = build("calendar", "v3", credentials=creds)
            primary = service.calendars().get(calendarId="primary").execute()
            account = primary.get("id", "")
            return True, account, "Google OAuth token is valid."
        except Exception:
            return True, "", "Google OAuth token is valid."
    except Exception as exc:
        return False, "", f"Token check failed: {exc}"


def _credentials_exists() -> bool:
    return Path(GOOGLE_CREDENTIALS_FILE).exists()


def _oauth_ready() -> bool:
  return _credentials_exists() or bool(HARDCODED_GOOGLE_CLIENT_CONFIG.get("web", {}).get("client_id"))


def _get_redirect_uri() -> str:
    # Use request.host_url to dynamically determine if the user is on localhost or 127.0.0.1
    # which prevents cookie mismatching issues when Google redirects back.
    base = request.host_url.rstrip("/")
    return f"{base}/google/callback"


def _configure_oauth_transport_for_dev() -> None:
  redirect_uri = _get_redirect_uri().lower()
  if redirect_uri.startswith("http://localhost") or redirect_uri.startswith("http://127.0.0.1"):
    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"


def _build_brightspace_ics_url(base_url: str, token: str) -> str:
    clean_base = base_url.rstrip("/")
    return f"{clean_base}/d2l/le/calendar/feed/user/feed.ics?token={quote(token)}"


def _resolve_brightspace_ics_url(base_url: str, token_or_url: str) -> str:
  value = (token_or_url or "").strip()
  if value.startswith("http://") or value.startswith("https://"):
    return value
  return _build_brightspace_ics_url(base_url, value)


def _to_plaintext(workflow: dict) -> str:
    lines = []

    lines.append("=== EXAMS / QUIZZES ===")
    for row in workflow.get("exams_quizzes", []):
        subject, date, event_type, start, end, location, name, weight = row
        lines.append(
            f"- [{event_type}] {date} {start}-{end} | {subject} | {name} | location={location or 'N/A'} | weight={weight or 'N/A'}"
        )

    lines.append("\n=== TAKE-HOME ASSIGNMENTS ===")
    for row in workflow.get("take_home_assignments", []):
        subject, date, event_type, due_time, name, weight = row
        lines.append(
            f"- [{event_type}] {date} {due_time or ''} | {subject} | {name} | weight={weight or 'N/A'}"
        )

    return "\n".join(lines)


def _extract_docx_text(docx_path: str, max_chars: int = 140000) -> str:
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    path = Path(docx_path)
    if not path.exists() or not path.is_file():
      raise FileNotFoundError(f"DOCX file not found: {path}")

    with ZipFile(path, "r") as archive:
      xml_bytes = archive.read("word/document.xml")

    root = ET.fromstring(xml_bytes)
    paragraphs = []
    for para in root.findall(".//w:p", ns):
      runs = [node.text for node in para.findall(".//w:t", ns) if node.text]
      if runs:
        paragraphs.append("".join(runs).strip())

    text = "\n".join(line for line in paragraphs if line)
    return text[:max_chars]


@app.route("/")
def index():
  connected, connected_account, connection_detail = _get_google_connection_status()
  return render_template_string(
    HTML,
    connected=connected,
    connected_account=connected_account,
    connection_detail=connection_detail,
    message=session.pop("message", None),
    events_text=session.pop("events_text", None),
    gemini_rows_text=session.pop("gemini_rows_text", None),
    base_url=DEFAULT_BRIGHTSPACE_BASE_URL,
    credentials_file=GOOGLE_CREDENTIALS_FILE,
    token_file=GOOGLE_TOKEN_FILE,
    oauth_ready=_oauth_ready(),
  )

@app.route("/extract/deadlines", methods=["POST"])
def extract_deadlines():
    upload = request.files.get("syllabus_file")
    if not upload or not upload.filename:
        session["message"] = "Please choose a PDF or DOCX file."
        return redirect(url_for("index"))

    api_key = (request.form.get("gemini_api_key") or "").strip() or os.getenv("GEMINI_API_KEY", "")
    model = (request.form.get("llm_model") or "gemini-3-flash-preview").strip()
    should_sync = (request.form.get("sync_to_google") or "").lower() in {"on", "true", "1", "yes"}
    if not api_key:
        session["message"] = "Gemini API key required. Paste it in the form or set GEMINI_API_KEY."
        return redirect(url_for("index"))

    filename = Path(upload.filename).name
    suffix = Path(filename).suffix.lower()
    if suffix not in {".pdf", ".docx"}:
        session["message"] = "Unsupported file type. Please upload .pdf or .docx."
        return redirect(url_for("index"))

    uploads_dir = OUTPUT_DIR / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)
    saved_path = uploads_dir / filename
    upload.save(saved_path)

    try:
        if suffix == ".pdf":
            rows = extract_deadlines_with_gemini(
                pdf_path=str(saved_path),
                api_key=api_key,
                model=model,
            )
        else:
            docx_text = _extract_docx_text(str(saved_path))
            rows = extract_deadlines_from_text_with_gemini(
                text=docx_text,
                api_key=api_key,
                model=model,
            )

        message = f"Gemini extraction complete. Found {len(rows)} rows from {filename}."
        if should_sync and rows:
          connected, _connected_account, _connection_detail = _get_google_connection_status()
          if connected:
            workflow = convert_rows_to_workflow_format(rows)
            generated_ics = workflow_to_ical(workflow, str(OUTPUT_DIR / "gemini_deadlines_sync.ics"))
            inserted = sync_ical_to_google_calendar(
              ics_path=generated_ics,
              credentials_file=GOOGLE_CREDENTIALS_FILE,
              token_file=GOOGLE_TOKEN_FILE,
              calendar_id="primary",
            )
            message += f" Synced {inserted} events to Google Calendar."
            session["events_text"] = _to_plaintext(workflow)
          else:
            message += " Google Calendar not connected, so sync was skipped."

        session["message"] = message
        session["gemini_rows_text"] = json.dumps(rows, indent=2, ensure_ascii=False)
    except Exception as exc:
        session["message"] = f"Gemini extraction failed: {exc}"

    return redirect(url_for("index"))


@app.route("/google/upload-credentials", methods=["POST"])
def upload_google_credentials():
    upload = request.files.get("oauth_file")
    if not upload:
        session["message"] = "Please choose a JSON file to upload."
        return redirect(url_for("index"))

    try:
        raw = upload.read().decode("utf-8")
        data = json.loads(raw)
    except Exception:
        session["message"] = "Invalid JSON file. Please upload the Google OAuth client secret JSON."
        return redirect(url_for("index"))

    if not isinstance(data, dict) or ("installed" not in data and "web" not in data):
        session["message"] = "That file is not a valid Google OAuth client secret JSON."
        return redirect(url_for("index"))

    credentials_path = Path(GOOGLE_CREDENTIALS_FILE)
    credentials_path.parent.mkdir(parents=True, exist_ok=True)
    credentials_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    session["message"] = "Google OAuth credentials uploaded. Click Connect Google Calendar."
    return redirect(url_for("index"))


@app.route("/google/connect")
def google_connect():
    try:
        from google_auth_oauthlib.flow import Flow
    except ImportError:
        session["message"] = "Missing google auth packages. Install requirements first."
        return redirect(url_for("index"))

    _configure_oauth_transport_for_dev()

    redirect_uri = _get_redirect_uri()
    session["oauth_redirect_uri"] = redirect_uri
    session.pop("oauth_state", None)
    session.pop("oauth_code_verifier", None)

    credentials_path = Path(GOOGLE_CREDENTIALS_FILE)
    if credentials_path.exists():
        flow = Flow.from_client_secrets_file(
            str(credentials_path),
            scopes=SCOPES,
            redirect_uri=redirect_uri,
        )
    else:
        flow = Flow.from_client_config(
            HARDCODED_GOOGLE_CLIENT_CONFIG,
            scopes=SCOPES,
            redirect_uri=redirect_uri,
        )
    auth_url, state = flow.authorization_url(access_type="offline", include_granted_scopes="true", prompt="consent")
    session["oauth_state"] = state
    session["oauth_code_verifier"] = flow.code_verifier
    return redirect(auth_url)


@app.route("/google/callback")
def google_callback():
  if "error" in request.args:
    session["message"] = f"Google returned an error: {request.args.get('error')}"
    return redirect(url_for("index"))

  try:
    from google_auth_oauthlib.flow import Flow
  except ImportError:
    session["message"] = "Missing google auth packages."
    return redirect(url_for("index"))

  _configure_oauth_transport_for_dev()

  state = session.get("oauth_state")
  if not state:
    session["message"] = "OAuth state missing; please connect again."
    return redirect(url_for("index"))

  code_verifier = session.get("oauth_code_verifier")
  if not code_verifier:
    session["message"] = "OAuth code verifier missing; please connect again."
    return redirect(url_for("index"))

  redirect_uri = session.get("oauth_redirect_uri") or _get_redirect_uri()

  credentials_path = Path(GOOGLE_CREDENTIALS_FILE)
  if credentials_path.exists():
    flow = Flow.from_client_secrets_file(
      GOOGLE_CREDENTIALS_FILE,
      scopes=SCOPES,
      state=state,
      redirect_uri=redirect_uri,
    )
  else:
    flow = Flow.from_client_config(
      HARDCODED_GOOGLE_CLIENT_CONFIG,
      scopes=SCOPES,
      state=state,
      redirect_uri=redirect_uri,
    )

  flow.code_verifier = code_verifier

  try:
    flow.fetch_token(authorization_response=request.url)
  except Exception as exc:
    message_text = str(exc).lower()
    if "mismatching_state" in message_text:
      session.pop("oauth_state", None)
      session.pop("oauth_code_verifier", None)
      session.pop("oauth_redirect_uri", None)
      session["message"] = "OAuth session expired/mismatched. Click Connect Google Calendar again."
      return redirect(url_for("index"))
    if "missing code verifier" in message_text or "invalid_grant" in message_text:
      session.pop("oauth_state", None)
      session.pop("oauth_code_verifier", None)
      session.pop("oauth_redirect_uri", None)
      session["message"] = "OAuth grant expired/invalid. Click Connect Google Calendar and complete login again."
      return redirect(url_for("index"))
    if "client_secret is missing" in message_text or "invalid_client" in message_text:
      session["message"] = "Google OAuth client_secret missing/invalid. Upload the full OAuth client JSON from Google Cloud and reconnect."
      return redirect(url_for("index"))
    session["message"] = f"Google OAuth callback failed: {exc}"
    return redirect(url_for("index"))

  token_path = Path(GOOGLE_TOKEN_FILE)
  token_path.parent.mkdir(parents=True, exist_ok=True)
  token_path.write_text(flow.credentials.to_json(), encoding="utf-8")

  session.pop("oauth_state", None)
  session.pop("oauth_code_verifier", None)
  session.pop("oauth_redirect_uri", None)

  session["message"] = "Google Calendar connected successfully."
  return redirect(url_for("index"))


@app.route("/sync", methods=["POST"])
def sync():
  connected, _connected_account, _connection_detail = _get_google_connection_status()
  if not connected:
    session["message"] = "Please connect Google Calendar first."
    return redirect(url_for("index"))

  token_or_url = (request.form.get("token") or "").strip()
  base_url = (request.form.get("base_url") or DEFAULT_BRIGHTSPACE_BASE_URL).strip()
  subject = (request.form.get("subject") or "Brightspace").strip()

  if not token_or_url:
    session["message"] = "Brightspace token or full ICS feed URL is required."
    return redirect(url_for("index"))

  try:
    feed_url = _resolve_brightspace_ics_url(base_url, token_or_url)
    raw_ics_path = download_ics_feed(feed_url, output_path=str(OUTPUT_DIR / "brightspace_live.ics"))

    raw_bytes = Path(raw_ics_path).read_bytes()
    raw_prefix = raw_bytes[:512].decode("utf-8", errors="ignore").lower()
    if "<html" in raw_prefix or "<!doctype" in raw_prefix:
      raise ValueError(
        "Brightspace returned an HTML login page instead of an ICS file. "
        "Use the feed token only (not your login URL) or use a valid feed URL that already includes ?token=."
      )

    events = load_ics_events(raw_ics_path)
    workflow = ics_events_to_workflow(events, subject_fallback=subject)

    generated_ics = workflow_to_ical(workflow, str(OUTPUT_DIR / "brightspace_sync.ics"))
    inserted = sync_ical_to_google_calendar(
      ics_path=generated_ics,
      credentials_file=GOOGLE_CREDENTIALS_FILE,
      token_file=GOOGLE_TOKEN_FILE,
      calendar_id="primary",
    )

    session["message"] = f"Sync complete. Inserted {inserted} events into Google Calendar."
    session["events_text"] = _to_plaintext(workflow)
  except Exception as exc:
    session["message"] = f"Sync failed: {exc}"

  return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5050, debug=True)
