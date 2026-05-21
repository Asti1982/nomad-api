from __future__ import annotations

import json
import os
from typing import Any, Optional

import requests
from google.auth.transport.requests import Request
from google.oauth2 import service_account


SCOPES = ["https://www.googleapis.com/auth/datastore"]
DEFAULT_DATABASE = "(default)"
DEFAULT_COLLECTION = "nomad_state"


def _clean_env(value: str) -> str:
    return str(value or "").strip().strip('"').strip("'")


def _private_key_from_env(value: str) -> str:
    return _clean_env(value).replace("\\n", "\n")


class FirestoreJsonState:
    """Store one bounded JSON payload in a Firestore document.

    This intentionally keeps the Firestore schema tiny: one JSON string field and
    one updated_at field. Nomad's source of truth remains the same Python dict,
    while Render restarts can restore it from a durable free-tier backend.
    """

    backend_name = "firestore"

    def __init__(
        self,
        *,
        project_id: str,
        client_email: str,
        private_key: str,
        collection: str = DEFAULT_COLLECTION,
        document: str,
        database: str = DEFAULT_DATABASE,
        timeout_seconds: float = 8.0,
    ) -> None:
        self.project_id = project_id
        self.collection = collection
        self.document = document
        self.database = database or DEFAULT_DATABASE
        self.timeout_seconds = timeout_seconds
        self._credentials = service_account.Credentials.from_service_account_info(
            {
                "type": "service_account",
                "project_id": project_id,
                "client_email": client_email,
                "private_key": private_key,
                "token_uri": "https://oauth2.googleapis.com/token",
            },
            scopes=SCOPES,
        )

    @classmethod
    def from_env(cls, *, scope: str) -> Optional["FirestoreJsonState"]:
        backend = _clean_env(os.getenv(f"NOMAD_{scope.upper()}_BACKEND") or os.getenv("NOMAD_STATE_BACKEND"))
        if backend.lower() not in {"firebase", "firestore"}:
            return None
        service_json = _clean_env(
            os.getenv(f"NOMAD_{scope.upper()}_FIREBASE_SERVICE_ACCOUNT_JSON")
            or os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")
        )
        service_info: dict[str, Any] = {}
        if service_json:
            try:
                service_info = json.loads(service_json)
            except json.JSONDecodeError:
                service_info = {}
        project_id = _clean_env(
            os.getenv(f"NOMAD_{scope.upper()}_FIREBASE_PROJECT_ID")
            or os.getenv("FIREBASE_PROJECT_ID")
            or service_info.get("project_id", "")
        )
        client_email = _clean_env(
            os.getenv(f"NOMAD_{scope.upper()}_FIREBASE_CLIENT_EMAIL")
            or os.getenv("FIREBASE_CLIENT_EMAIL")
            or service_info.get("client_email", "")
        )
        private_key = _private_key_from_env(
            os.getenv(f"NOMAD_{scope.upper()}_FIREBASE_PRIVATE_KEY")
            or os.getenv("FIREBASE_PRIVATE_KEY")
            or service_info.get("private_key", "")
        )
        if not project_id or not client_email or not private_key:
            return None
        return cls(
            project_id=project_id,
            client_email=client_email,
            private_key=private_key,
            collection=_clean_env(os.getenv(f"NOMAD_{scope.upper()}_FIRESTORE_COLLECTION") or DEFAULT_COLLECTION),
            document=_clean_env(os.getenv(f"NOMAD_{scope.upper()}_FIRESTORE_DOCUMENT") or scope),
            database=_clean_env(os.getenv("FIRESTORE_DATABASE_ID") or DEFAULT_DATABASE),
            timeout_seconds=float(os.getenv("NOMAD_FIRESTORE_TIMEOUT_SECONDS", "8") or "8"),
        )

    def load(self) -> dict[str, Any] | None:
        response = requests.get(
            self._document_url(),
            headers=self._headers(),
            timeout=self.timeout_seconds,
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        fields = (response.json().get("fields") or {}) if response.content else {}
        raw = ((fields.get("payload_json") or {}).get("stringValue") or "").strip()
        if not raw:
            return None
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else None

    def save(self, payload: dict[str, Any]) -> bool:
        body = {
            "fields": {
                "payload_json": {"stringValue": json.dumps(payload, ensure_ascii=False, separators=(",", ":"))},
                "updated_at": {"stringValue": str(payload.get("updated_at") or "")},
                "schema": {"stringValue": "nomad.firestore_json_state.v1"},
            }
        }
        response = requests.patch(
            self._document_url(),
            headers=self._headers(),
            json=body,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        return True

    def _headers(self) -> dict[str, str]:
        if not self._credentials.valid:
            self._credentials.refresh(Request())
        return {
            "Authorization": f"Bearer {self._credentials.token}",
            "Content-Type": "application/json",
        }

    def _document_url(self) -> str:
        return (
            "https://firestore.googleapis.com/v1/"
            f"projects/{self.project_id}/databases/{self.database}/documents/"
            f"{self.collection}/{self.document}"
        )
