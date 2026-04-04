import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict


def build_dashboard_payload(workflow_data: Dict, source: str, metadata: Dict = None) -> Dict:
    metadata = metadata or {}
    exams_count = len(workflow_data.get("exams_quizzes", []))
    tasks_count = len(workflow_data.get("take_home_assignments", []))

    return {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "counts": {
            "exams_quizzes": exams_count,
            "take_home_assignments": tasks_count,
            "total": exams_count + tasks_count,
        },
        "metadata": metadata,
        "workflow": workflow_data,
    }


def save_dashboard_payload(payload: Dict, output_path: str) -> str:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return str(path)
