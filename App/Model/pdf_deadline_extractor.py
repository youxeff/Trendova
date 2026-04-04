import argparse
import json
import os
from pathlib import Path
from typing import Optional

try:
    from .syllabus_pipeline.brightspace_ics_client import download_ics_feed, load_ics_events, ics_events_to_workflow
    from .syllabus_pipeline.brightspace_client import BrightspaceClient
    from .syllabus_pipeline.brightspace_transformer import brightspace_items_to_workflow
    from .syllabus_pipeline.dashboard_export import build_dashboard_payload, save_dashboard_payload
    from .syllabus_pipeline.format_converter import convert_rows_to_workflow_format
    from .syllabus_pipeline.gemini_client import extract_deadlines_with_gemini
    from .syllabus_pipeline.gmail_connector import sync_ical_to_google_calendar
    from .syllabus_pipeline.ical_converter import workflow_to_ical
except ImportError:
    from syllabus_pipeline.brightspace_ics_client import download_ics_feed, load_ics_events, ics_events_to_workflow
    from syllabus_pipeline.brightspace_client import BrightspaceClient
    from syllabus_pipeline.brightspace_transformer import brightspace_items_to_workflow
    from syllabus_pipeline.dashboard_export import build_dashboard_payload, save_dashboard_payload
    from syllabus_pipeline.format_converter import convert_rows_to_workflow_format
    from syllabus_pipeline.gemini_client import extract_deadlines_with_gemini
    from syllabus_pipeline.gmail_connector import sync_ical_to_google_calendar
    from syllabus_pipeline.ical_converter import workflow_to_ical


def run_pipeline(
    source: str,
    pdf_path: Optional[str],
    api_key: str,
    llm_model: str,
    brightspace_url: Optional[str],
    brightspace_token: Optional[str],
    brightspace_org_unit_id: Optional[str],
    brightspace_api_version: str,
    brightspace_ics_url: Optional[str],
    brightspace_ics_file: Optional[str],
    save_brightspace_ics: Optional[str],
    subject_fallback: str,
    output_mode: str,
    pretty: bool,
    save_ics: Optional[str],
    save_dashboard: Optional[str],
    sync_google: bool,
    google_credentials: Optional[str],
    google_token: str,
    calendar_id: str,
):
    metadata = {}
    if source == "brightspace":
        if not brightspace_url or not brightspace_token or not brightspace_org_unit_id:
            raise ValueError("Brightspace source requires --brightspace-url, --brightspace-token, and --brightspace-org-unit-id")

        client = BrightspaceClient(
            base_url=brightspace_url,
            access_token=brightspace_token,
            api_version=brightspace_api_version,
        )
        latest_data = client.get_latest_course_data(org_unit_id=brightspace_org_unit_id)
        workflow_output = brightspace_items_to_workflow(latest_data, subject_fallback=subject_fallback)
        rows = []
        metadata = {
            "org_unit_id": brightspace_org_unit_id,
            "api_version": brightspace_api_version,
            "used_endpoints": latest_data.get("used_endpoints", []),
            "items_count": len(latest_data.get("items", [])),
        }
        output = workflow_output
    elif source == "brightspace-ics":
        if brightspace_ics_url:
            ics_path = download_ics_feed(brightspace_ics_url, output_path=save_brightspace_ics)
        elif brightspace_ics_file:
            ics_path = brightspace_ics_file
        else:
            raise ValueError("Brightspace ICS source requires --brightspace-ics-url or --brightspace-ics-file")

        events = load_ics_events(ics_path)
        workflow_output = ics_events_to_workflow(events, subject_fallback=subject_fallback)
        rows = []
        metadata = {
            "ics_path": ics_path,
            "events_count": len(events),
        }
        output = workflow_output
    else:
        rows = extract_deadlines_with_gemini(
            pdf_path=pdf_path,
            api_key=api_key,
            model=llm_model,
        )

        workflow_output = convert_rows_to_workflow_format(rows)
        output = workflow_output if output_mode == "workflow" else rows

    ics_path = save_ics
    if save_ics:
        workflow_to_ical(workflow_output, save_ics)

    if sync_google:
        if not google_credentials:
            raise ValueError("--google-credentials is required when --sync-google is used")

        if not ics_path:
            ics_path = str(Path("output") / "syllabus_events.ics")
            workflow_to_ical(workflow_output, ics_path)

        inserted = sync_ical_to_google_calendar(
            ics_path=ics_path,
            credentials_file=google_credentials,
            token_file=google_token,
            calendar_id=calendar_id,
        )
        print(f"Synced {inserted} events to Google Calendar '{calendar_id}'.")

    if save_dashboard:
        payload = build_dashboard_payload(workflow_output, source=source, metadata=metadata)
        saved_path = save_dashboard_payload(payload, save_dashboard)
        print(f"Dashboard payload saved to {saved_path}")

    if pretty:
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        print(json.dumps(output, ensure_ascii=False))


def run_local_tester(default_path: Optional[str], args) -> None:
    print("Local PDF Deadline Tester")
    print("Paste a PDF path and press Enter. Type 'q' to quit.")

    while True:
        prompt = "PDF path"
        if default_path:
            prompt += f" [Enter for default: {default_path}]"
        prompt += ": "

        entered = input(prompt).strip().strip('"').strip("'")
        if entered.lower() in {"q", "quit", "exit"}:
            print("Exiting local tester.")
            return

        target_path = entered or (default_path or "")
        pdf_file = Path(target_path)

        if not pdf_file.exists() or not pdf_file.is_file():
            print(f"Invalid PDF path: {pdf_file}")
            continue

        run_pipeline(
            source="pdf",
            pdf_path=str(pdf_file),
            api_key=args.gemini_api_key or os.getenv("GEMINI_API_KEY", ""),
            llm_model=args.llm_model,
            brightspace_url=args.brightspace_url,
            brightspace_token=args.brightspace_token,
            brightspace_org_unit_id=args.brightspace_org_unit_id,
            brightspace_api_version=args.brightspace_api_version,
            brightspace_ics_url=args.brightspace_ics_url,
            brightspace_ics_file=args.brightspace_ics_file,
            save_brightspace_ics=args.save_brightspace_ics,
            subject_fallback=args.subject_fallback,
            output_mode=args.output_mode,
            pretty=args.pretty,
            save_ics=args.save_ics,
            save_dashboard=args.save_dashboard,
            sync_google=args.sync_google,
            google_credentials=args.google_credentials,
            google_token=args.google_token,
            calendar_id=args.calendar_id,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Parse syllabus/Brightspace data and optionally export/sync calendar.")
    parser.add_argument("pdf", nargs="?", help="Path to PDF file")
    parser.add_argument("--source", choices=["pdf", "brightspace", "brightspace-ics"], default="pdf", help="Input source")
    parser.add_argument("--use-llm", action="store_true", help="Backward-compatible no-op (PDF source already uses LLM)")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output")
    parser.add_argument("--local-test", action="store_true", help="Run interactive local tester mode")
    parser.add_argument("--default-path", help="Default PDF path used by local tester when pressing Enter")

    parser.add_argument("--gemini-api-key", help="Gemini API key (or set GEMINI_API_KEY env var)")
    parser.add_argument("--llm-model", default="gemini-3-flash-preview", help="Gemini model name")
    parser.add_argument(
        "--output-mode",
        choices=["rows", "workflow"],
        default="rows",
        help="rows: original array-of-arrays, workflow: split into exams_quizzes and take_home_assignments",
    )

    parser.add_argument("--brightspace-url", help="Brightspace base URL, e.g. https://school.brightspace.com")
    parser.add_argument("--brightspace-token", help="Brightspace bearer token")
    parser.add_argument("--brightspace-org-unit-id", help="Brightspace org unit (course) ID")
    parser.add_argument("--brightspace-api-version", default="1.75", help="Brightspace LE API version")
    parser.add_argument("--brightspace-ics-url", help="Brightspace ICS feed URL")
    parser.add_argument("--brightspace-ics-file", help="Local Brightspace ICS file path")
    parser.add_argument("--save-brightspace-ics", help="Optional path to save downloaded Brightspace ICS")
    parser.add_argument("--subject-fallback", default="Course", help="Fallback subject name for Brightspace items")

    parser.add_argument("--save-ics", help="Path to write generated .ics file")
    parser.add_argument("--save-dashboard", help="Path to write dashboard JSON payload")
    parser.add_argument("--sync-google", action="store_true", help="Sync generated ICS events to Google Calendar")
    parser.add_argument("--google-credentials", help="Path to Google OAuth credentials JSON")
    parser.add_argument("--google-token", default="google_token.json", help="Path to cached Google OAuth token")
    parser.add_argument("--calendar-id", default="primary", help="Google Calendar ID (default: primary)")

    args = parser.parse_args()

    if args.local_test:
        run_local_tester(args.default_path, args)
        return

    api_key = args.gemini_api_key or os.getenv("GEMINI_API_KEY", "")
    pdf_path = None
    if args.source == "pdf":
        if not args.pdf:
            parser.error("pdf is required unless --source brightspace is used")
        if not api_key:
            parser.error("Gemini API key is required for PDF source: pass --gemini-api-key or set GEMINI_API_KEY")

        pdf_file = Path(args.pdf)
        if not pdf_file.exists() or not pdf_file.is_file():
            raise FileNotFoundError(f"PDF not found: {pdf_file}")
        pdf_path = str(pdf_file)

    run_pipeline(
        source=args.source,
        pdf_path=pdf_path,
        api_key=api_key,
        llm_model=args.llm_model,
        brightspace_url=args.brightspace_url,
        brightspace_token=args.brightspace_token,
        brightspace_org_unit_id=args.brightspace_org_unit_id,
        brightspace_api_version=args.brightspace_api_version,
        brightspace_ics_url=args.brightspace_ics_url,
        brightspace_ics_file=args.brightspace_ics_file,
        save_brightspace_ics=args.save_brightspace_ics,
        subject_fallback=args.subject_fallback,
        output_mode=args.output_mode,
        pretty=args.pretty,
        save_ics=args.save_ics,
        save_dashboard=args.save_dashboard,
        sync_google=args.sync_google,
        google_credentials=args.google_credentials,
        google_token=args.google_token,
        calendar_id=args.calendar_id,
    )


if __name__ == "__main__":
    main()
