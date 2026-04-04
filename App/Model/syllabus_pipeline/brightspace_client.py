from typing import Dict, List, Tuple

import requests


class BrightspaceClient:
    def __init__(self, base_url: str, access_token: str, api_version: str = "1.75") -> None:
        self.base_url = base_url.rstrip("/")
        self.access_token = access_token
        self.api_version = api_version

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    def _get(self, path: str) -> dict:
        url = f"{self.base_url}{path}"
        response = requests.get(url, headers=self._headers(), timeout=60)
        response.raise_for_status()
        return response.json()

    def get_latest_course_data(self, org_unit_id: str) -> Dict:
        endpoints = [
            f"/d2l/api/le/{self.api_version}/{org_unit_id}/calendar/events/",
            f"/d2l/api/le/{self.api_version}/{org_unit_id}/content/toc",
            f"/d2l/api/le/{self.api_version}/{org_unit_id}/news/",
        ]

        collected: List[dict] = []
        used_endpoints: List[str] = []

        for endpoint in endpoints:
            try:
                payload = self._get(endpoint)
                items = self._extract_items(payload)
                if items:
                    collected.extend(items)
                    used_endpoints.append(endpoint)
            except requests.RequestException:
                continue

        return {
            "org_unit_id": org_unit_id,
            "api_version": self.api_version,
            "used_endpoints": used_endpoints,
            "items": collected,
        }

    @staticmethod
    def _extract_items(payload) -> List[dict]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]

        if not isinstance(payload, dict):
            return []

        for key in ["Items", "Objects", "CalendarEvents", "Events", "Modules", "NewsItems"]:
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]

        return []
