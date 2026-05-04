import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from dotenv import load_dotenv

from nomad_deployment import DEFAULT_GITHUB_DEPLOY_BRANCH


RENDER_API_KEY_ENV = "RENDER_API_KEY"
# Some operators store the same secret under a Nomad-prefixed name; accept either.
RENDER_API_KEY_FALLBACK_ENV = "NOMAD_RENDER_API_KEY"
RENDER_SERVICE_ID_ENV = "NOMAD_RENDER_SERVICE_ID"
RENDER_SERVICE_NAME_ENV = "NOMAD_RENDER_SERVICE_NAME"
RENDER_OWNER_ID_ENV = "NOMAD_RENDER_OWNER_ID"
RENDER_DOMAIN_ENV = "NOMAD_RENDER_DOMAIN"
RENDER_ROOT_DOMAIN_ENV = "NOMAD_RENDER_ROOT_DOMAIN"
RENDER_DEPLOY_ENABLED_ENV = "NOMAD_RENDER_DEPLOY_ENABLED"
RENDER_API_BASE_ENV = "NOMAD_RENDER_API_BASE"
RENDER_TIMEOUT_ENV = "NOMAD_RENDER_TIMEOUT_SECONDS"
GITHUB_REPOSITORY_ENV = "NOMAD_GITHUB_REPOSITORY"
GITHUB_DEPLOY_BRANCH_ENV = "NOMAD_GITHUB_DEPLOY_BRANCH"

DEFAULT_RENDER_API_BASE = "https://api.render.com/v1"
DEFAULT_RENDER_SERVICE_NAME = "nomad-api"
DEFAULT_RENDER_DOMAIN = "onrender.syndiode.com"


def parse_render_yaml_first_web_service_commands(render_yaml: Path) -> Dict[str, Any]:
    """Read the first `type: web` entry under `services:` and return build/start commands (stdlib only)."""
    if not render_yaml.exists():
        return {
            "ok": False,
            "issue": "render_yaml_missing",
            "message": f"render.yaml not found at {render_yaml}",
        }
    lines = render_yaml.read_text(encoding="utf-8").splitlines()
    list_item_indent: Optional[int] = None
    in_web = False
    build_cmd = ""
    start_cmd = ""
    for line in lines:
        stripped = line.lstrip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(stripped)
        if stripped.startswith("- ") and "type:" in stripped:
            if in_web and list_item_indent is not None and indent == list_item_indent:
                break
            rest = stripped[2:].strip()
            list_item_indent = indent
            in_web = rest == "type: web" or rest.startswith("type: web")
            if not in_web:
                build_cmd = ""
                start_cmd = ""
            continue
        if in_web:
            if stripped.startswith("buildCommand:"):
                build_cmd = stripped.split(":", 1)[1].strip().strip('"').strip("'")
            elif stripped.startswith("startCommand:"):
                start_cmd = stripped.split(":", 1)[1].strip().strip('"').strip("'")
    if not build_cmd or not start_cmd:
        return {
            "ok": False,
            "issue": "render_yaml_web_commands_missing",
            "message": "No buildCommand/startCommand pair found for the first web service in render.yaml.",
        }
    return {
        "ok": True,
        "buildCommand": build_cmd,
        "startCommand": start_cmd,
        "message": "Parsed build and start commands from render.yaml.",
    }


def _env_flag(name: str, default: bool = False) -> bool:
    raw = (os.getenv(name) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


class RenderHostingProbe:
    """Render public hosting probe for Nomad's outward-facing API lane."""

    def __init__(self, repo_root: Optional[Path | str] = None) -> None:
        load_dotenv()
        self.repo_root = Path(repo_root or Path(__file__).resolve().parent)
        self.api_key = (
            (os.getenv(RENDER_API_KEY_ENV) or "").strip()
            or (os.getenv(RENDER_API_KEY_FALLBACK_ENV) or "").strip()
        )
        self.service_id = (os.getenv(RENDER_SERVICE_ID_ENV) or "").strip()
        self.owner_id = (os.getenv(RENDER_OWNER_ID_ENV) or "").strip()
        self.service_name = (
            os.getenv(RENDER_SERVICE_NAME_ENV)
            or DEFAULT_RENDER_SERVICE_NAME
        ).strip()
        self.domain = (os.getenv(RENDER_DOMAIN_ENV) or DEFAULT_RENDER_DOMAIN).strip()
        self.root_domain = (os.getenv(RENDER_ROOT_DOMAIN_ENV) or "").strip()
        self.api_base = (os.getenv(RENDER_API_BASE_ENV) or DEFAULT_RENDER_API_BASE).rstrip("/")
        self.timeout_seconds = float(os.getenv(RENDER_TIMEOUT_ENV, "12"))
        self.github_repository = (
            os.getenv(GITHUB_REPOSITORY_ENV)
            or os.getenv("GITHUB_REPOSITORY")
            or ""
        ).strip()
        self.github_branch = (
            os.getenv(GITHUB_DEPLOY_BRANCH_ENV)
            or DEFAULT_GITHUB_DEPLOY_BRANCH
        ).strip()

    def snapshot(self, verify: bool = False) -> Dict[str, Any]:
        render_yaml = self.repo_root / "render.yaml"
        status: Dict[str, Any] = {
            "provider": "Render",
            "role": "public_api_hosting",
            "configured": bool(self.api_key),
            "api_key_configured": bool(self.api_key),
            "service_id_configured": bool(self.service_id),
            "owner_id_configured": bool(self.owner_id),
            "service_name": self.service_name,
            "desired_domain": self.domain,
            "root_domain": self.root_domain,
            "deploy_enabled": _env_flag(RENDER_DEPLOY_ENABLED_ENV, default=False),
            "public_api_url": (os.getenv("NOMAD_PUBLIC_API_URL") or "").strip(),
            "public_check_url": self._public_check_url(),
            "api_base": self.api_base,
            "github_repository": self.github_repository,
            "desired_branch": self.github_branch,
            "render_yaml_present": render_yaml.exists(),
            "render_yaml_path": str(render_yaml),
            "docs": {
                "api": "https://render.com/docs/api",
                "custom_domains": "https://render.com/docs/custom-domains",
                "blueprints": "https://render.com/docs/blueprint-spec",
                "mcp_server": "https://render.com/docs/mcp-server",
            },
            "safe_actions": [
                "verify API key by listing services",
                "find a matching Render web service by service id or name",
                "prepare DNS/custom-domain steps for the selected service",
                "trigger a deploy only with explicit deploy approval",
                "PATCH build/start commands to match render.yaml with approval=sync_commands (existing Web Service, not Blueprint-only)",
            ],
            "blocked_actions": [
                "no secret values are written to source files",
                "no paid service creation without workspace/owner confirmation",
                "no domain mutation without service id and explicit domain approval",
            ],
        }
        status["next_action"] = self._next_action(status)
        if verify:
            status["public_checks"] = self.verify_public_surface()
            status["verification"] = self.verify_services()
            status["owners"] = self.list_owners()
            selected = status["verification"].get("selected_service") or {}
            if selected:
                status["service_id"] = selected.get("id", "")
                status["service_url"] = selected.get("url", "")
                status["next_action"] = self._next_action(status)
            elif (status.get("public_checks") or {}).get("ok"):
                status["next_action"] = "Render public API is live; set RENDER_API_KEY only if Nomad should trigger deploys or manage domains."
        if verify and status.get("api_key_configured"):
            sid = (status.get("service_id") or self.service_id or "").strip()
            if sid:
                status["recent_deploys"] = self.list_recent_deploys(service_id=sid, limit=10)
        return status

    def verify_public_surface(self) -> Dict[str, Any]:
        base_url = self._public_check_url()
        if not base_url:
            return {
                "ok": False,
                "issue": "render_public_url_missing",
                "message": "Set NOMAD_PUBLIC_API_URL or NOMAD_RENDER_DOMAIN before checking the public Render surface.",
                "checks": [],
            }
        paths = [
            "/health",
            "/.well-known/agent-card.json",
            "/openapi.json",
            "/.well-known/nomad-peer-acquisition.json",
            "/.well-known/nomad-agent.json",
            "/swarm/coordinate",
            "/swarm/accumulate",
            "/collaboration",
        ]
        checks = [self._public_get(base_url, path) for path in paths]
        required = {"/health", "/.well-known/agent-card.json"}
        ok = all(item.get("ok") for item in checks if item.get("path") in required)
        swarm_ready = any(item.get("ok") and item.get("path") == "/swarm/coordinate" for item in checks)
        accumulation_ready = any(item.get("ok") and item.get("path") == "/swarm/accumulate" for item in checks)
        issue = ""
        if not ok:
            issue = "render_public_surface_unavailable"
        elif not accumulation_ready:
            issue = "render_swarm_accumulation_not_deployed"
        elif not swarm_ready:
            issue = "render_swarm_coordination_not_deployed"
        return {
            "ok": bool(ok),
            "base_url": base_url,
            "swarm_ready": bool(swarm_ready),
            "accumulation_ready": bool(accumulation_ready),
            "issue": issue,
            "checks": checks,
            "message": (
                "Render public surface is reachable."
                if ok
                else "Render public surface did not return the required health and AgentCard checks."
            ),
        }

    def list_owners(self) -> Dict[str, Any]:
        if not self.api_key:
            return {
                "ok": False,
                "issue": "render_api_key_missing",
                "message": "Set RENDER_API_KEY before listing Render workspaces.",
            }
        response = self._request("GET", "/owners", params={"limit": 20})
        if not response.get("ok"):
            return response
        owners = [self._compact_owner(item) for item in response.get("payload") or []]
        selected = {}
        if self.owner_id:
            for owner in owners:
                if owner.get("id") == self.owner_id:
                    selected = owner
                    break
        elif len(owners) == 1:
            selected = owners[0]
        return {
            "ok": True,
            "owner_count": len(owners),
            "owners": owners[:10],
            "selected_owner": selected,
            "message": "Render workspace access verified." if selected else "Set NOMAD_RENDER_OWNER_ID before creating a service.",
        }

    def verify_services(self) -> Dict[str, Any]:
        if not self.api_key:
            return {
                "ok": False,
                "issue": "render_api_key_missing",
                "message": "Set RENDER_API_KEY before verifying Render services.",
            }
        response = self._request("GET", "/services", params={"limit": 20})
        if not response.get("ok"):
            return response
        services = [self._compact_service(item) for item in response.get("payload") or []]
        selected = self._select_service(services)
        return {
            "ok": True,
            "service_count": len(services),
            "services": services[:10],
            "selected_service": selected,
            "message": (
                "Render API key is valid and a matching service was found."
                if selected
                else "Render API key is valid; set NOMAD_RENDER_SERVICE_ID or create/link the nomad-api service."
            ),
        }

    def list_recent_deploys(self, service_id: str = "", limit: int = 10) -> Dict[str, Any]:
        """List recent deploys for a service via the Render REST API (same key as MCP; no MCP protocol in-process)."""
        sid = (service_id or self.service_id or "").strip()
        if not self.api_key:
            return {
                "ok": False,
                "issue": "render_api_key_missing",
                "deploys": [],
                "message": "Set RENDER_API_KEY before listing deploys.",
            }
        if not sid:
            return {
                "ok": False,
                "issue": "render_service_id_missing",
                "deploys": [],
                "message": "Set NOMAD_RENDER_SERVICE_ID or resolve a service from name first.",
            }
        lim = max(1, min(100, int(limit)))
        response = self._request("GET", f"/services/{sid}/deploys", params={"limit": lim})
        if not response.get("ok"):
            return {
                "ok": False,
                "issue": response.get("issue", "render_api_error"),
                "deploys": [],
                "message": response.get("message", "Render deploy list failed."),
                "status_code": response.get("status_code"),
            }
        rows = self._normalize_deploy_list(response.get("payload"))
        return {
            "ok": True,
            "service_id": sid,
            "deploys": [self._compact_deploy_row(row) for row in rows[:lim]],
            "message": "Recent deploys from Render API.",
            "debug_hint": (
                "For log lines and natural-language triage in Cursor, add Render's hosted MCP "
                "(https://render.com/docs/mcp-server) to ~/.cursor/mcp.json with the same API key scope."
            ),
        }

    def list_recent_logs(
        self,
        service_id: str = "",
        owner_id: str = "",
        limit: int = 40,
        log_type: str = "app",
    ) -> Dict[str, Any]:
        """Fetch recent logs via GET /v1/logs (Render REST). Needs workspace ownerId + service resource id."""
        sid = (service_id or self.service_id or "").strip()
        oid = (owner_id or self.owner_id or "").strip()
        if not self.api_key:
            return {
                "ok": False,
                "issue": "render_api_key_missing",
                "lines": [],
                "message": "Set RENDER_API_KEY (or NOMAD_RENDER_API_KEY) in .env.",
            }
        if not oid:
            owners = self.list_owners()
            if owners.get("ok"):
                sel = owners.get("selected_owner") or {}
                oid = str(sel.get("id") or "").strip()
        if not oid:
            return {
                "ok": False,
                "issue": "render_owner_id_missing",
                "lines": [],
                "message": "Set NOMAD_RENDER_OWNER_ID (workspace/team id) for GET /v1/logs.",
            }
        if not sid:
            ver = self.verify_services()
            sid = str((ver.get("selected_service") or {}).get("id") or "").strip()
        if not sid:
            return {
                "ok": False,
                "issue": "render_service_id_missing",
                "lines": [],
                "message": "Set NOMAD_RENDER_SERVICE_ID or NOMAD_RENDER_SERVICE_NAME.",
            }
        lim = max(1, min(100, int(limit)))
        lt = (log_type or "app").strip() or "app"
        params: List[Tuple[str, str]] = [
            ("ownerId", oid),
            ("resource", sid),
            ("limit", str(lim)),
            ("type", lt),
            ("direction", "backward"),
        ]
        response = self._request("GET", "/logs", params=params)
        if not response.get("ok"):
            return {
                "ok": False,
                "issue": response.get("issue", "render_api_error"),
                "lines": [],
                "message": response.get("message", "Render log request failed."),
                "status_code": response.get("status_code"),
                "payload_excerpt": str(response.get("payload"))[:800],
            }
        lines = self._normalize_log_lines(response.get("payload"), lim)
        return {
            "ok": True,
            "owner_id": oid,
            "service_id": sid,
            "log_type": lt,
            "lines": lines,
            "message": "Recent log lines from Render API (https://api-docs.render.com/reference/list-logs).",
        }

    @staticmethod
    def _normalize_log_lines(payload: Any, cap: int) -> List[Dict[str, Any]]:
        raw: List[Any] = []
        if isinstance(payload, dict):
            raw = (
                payload.get("logs")
                or payload.get("items")
                or payload.get("results")
                or []
            )
        elif isinstance(payload, list):
            raw = payload
        if not isinstance(raw, list):
            return []
        out: List[Dict[str, Any]] = []
        for item in raw[:cap]:
            if not isinstance(item, dict):
                out.append({"message": str(item)[:2000]})
                continue
            msg = item.get("message") or item.get("text") or item.get("msg") or ""
            if not msg and "labels" in item:
                msg = str(item.get("labels"))[:500]
            out.append(
                {
                    "timestamp": str(item.get("timestamp") or item.get("time") or ""),
                    "level": str(item.get("level") or ""),
                    "type": str(item.get("type") or ""),
                    "message": str(msg)[:2000],
                }
            )
        return out

    @staticmethod
    def _normalize_deploy_list(payload: Any) -> List[Dict[str, Any]]:
        if isinstance(payload, list):
            out: List[Dict[str, Any]] = []
            for item in payload:
                if isinstance(item, dict) and isinstance(item.get("deploy"), dict):
                    out.append(item["deploy"])
                elif isinstance(item, dict):
                    out.append(item)
            return out
        if isinstance(payload, dict):
            for key in ("deploys", "items", "results"):
                inner = payload.get(key)
                if isinstance(inner, list):
                    return RenderHostingProbe._normalize_deploy_list(inner)
        return []

    @staticmethod
    def _compact_deploy_row(deploy: Dict[str, Any]) -> Dict[str, Any]:
        commit = deploy.get("commit") if isinstance(deploy.get("commit"), dict) else {}
        commit_id = commit.get("id", "") if commit else str(deploy.get("commitId", "") or "")
        return {
            "id": deploy.get("id", ""),
            "status": deploy.get("status", ""),
            "commit_id": commit_id,
            "created_at": deploy.get("createdAt", ""),
            "updated_at": deploy.get("updatedAt", ""),
            "finished_at": deploy.get("finishedAt", ""),
        }

    def trigger_deploy(self, approval: str = "", clear_cache: bool = False) -> Dict[str, Any]:
        approval_value = (approval or "").strip().lower()
        if approval_value not in {"deploy", "yes", "true", "approved"}:
            return {
                "ok": False,
                "issue": "render_deploy_approval_required",
                "message": "Pass approval=deploy before Nomad triggers a Render deploy.",
            }
        service_id = self.service_id or (self.verify_services().get("selected_service") or {}).get("id", "")
        if not service_id:
            return {
                "ok": False,
                "issue": "render_service_id_missing",
                "message": "Set NOMAD_RENDER_SERVICE_ID or NOMAD_RENDER_SERVICE_NAME for the Render service to deploy.",
            }
        payload = {"clearCache": "clear" if clear_cache else "do_not_clear"}
        response = self._request("POST", f"/services/{service_id}/deploys", json=payload)
        return {
            "ok": response.get("ok", False),
            "issue": response.get("issue", ""),
            "service_id": service_id,
            "message": response.get("message", "Render deploy request completed."),
            "deploy": self._compact_deploy(response.get("payload")),
        }

    def update_service_build_start(
        self,
        build_command: str,
        start_command: str,
        approval: str = "",
    ) -> Dict[str, Any]:
        """PATCH the Render web service so Dashboard build/start match repo render.yaml (requires API key)."""
        approval_value = (approval or "").strip().lower()
        if approval_value not in {"sync_commands", "yes", "true", "approved"}:
            return {
                "ok": False,
                "issue": "render_sync_commands_approval_required",
                "message": "Pass approval=sync_commands before Nomad PATCHes Render build/start commands.",
            }
        if not self.api_key:
            return {
                "ok": False,
                "issue": "render_api_key_missing",
                "message": "Set RENDER_API_KEY before updating the Render service.",
            }
        build_command = (build_command or "").strip()
        start_command = (start_command or "").strip()
        if not build_command or not start_command:
            return {
                "ok": False,
                "issue": "render_commands_empty",
                "message": "build_command and start_command must be non-empty.",
            }
        service_id = self.service_id or (self.verify_services().get("selected_service") or {}).get("id", "")
        if not service_id:
            return {
                "ok": False,
                "issue": "render_service_id_missing",
                "message": "Set NOMAD_RENDER_SERVICE_ID or NOMAD_RENDER_SERVICE_NAME for the Render service to update.",
            }
        body = {
            "serviceDetails": {
                "buildCommand": build_command,
                "startCommand": start_command,
            }
        }
        response = self._request("PATCH", f"/services/{service_id}", json=body)
        out: Dict[str, Any] = {
            "ok": response.get("ok", False),
            "issue": response.get("issue", ""),
            "service_id": service_id,
            "buildCommand": build_command,
            "startCommand": start_command,
            "message": response.get("message", "Render service update completed."),
        }
        if response.get("ok") and isinstance(response.get("payload"), dict):
            out["service"] = self._compact_service(response.get("payload"))
        return out

    def sync_service_commands_from_render_yaml(self, approval: str = "") -> Dict[str, Any]:
        """Apply buildCommand/startCommand from repo render.yaml to the selected Render service."""
        parsed = parse_render_yaml_first_web_service_commands(self.repo_root / "render.yaml")
        if not parsed.get("ok"):
            return parsed
        applied = self.update_service_build_start(
            str(parsed.get("buildCommand") or ""),
            str(parsed.get("startCommand") or ""),
            approval=approval,
        )
        if applied.get("ok"):
            applied["render_yaml"] = str(self.repo_root / "render.yaml")
        return applied

    def _public_check_url(self) -> str:
        configured = (os.getenv("NOMAD_PUBLIC_API_URL") or "").strip().rstrip("/")
        if configured and "127.0.0.1" not in configured and "localhost" not in configured:
            return configured
        if self.domain:
            domain = self.domain.strip().rstrip("/")
            if domain.startswith(("http://", "https://")):
                return domain
            return f"https://{domain}"
        return ""

    def _public_get(self, base_url: str, path: str) -> Dict[str, Any]:
        url = f"{base_url.rstrip('/')}{path}"
        try:
            response = requests.get(
                url,
                headers={
                    "Accept": "application/json, text/plain;q=0.9, */*;q=0.8",
                    "User-Agent": "Nomad/0.1 render-public-check",
                },
                timeout=self.timeout_seconds,
            )
        except requests.Timeout as exc:
            return {
                "ok": False,
                "path": path,
                "url": url,
                "issue": "render_public_check_timeout",
                "message": str(exc)[:240],
            }
        except Exception as exc:
            return {
                "ok": False,
                "path": path,
                "url": url,
                "issue": "render_public_check_failed",
                "message": str(exc)[:240],
            }
        return {
            "ok": bool(response.ok),
            "path": path,
            "url": url,
            "status_code": response.status_code,
            "content_type": getattr(response, "headers", {}).get("Content-Type", ""),
            "message": "ok" if response.ok else response.text[:240],
        }

    def add_custom_domain(self, approval: str = "") -> Dict[str, Any]:
        approval_value = (approval or "").strip().lower()
        if approval_value not in {"domain", "yes", "true", "approved"}:
            return {
                "ok": False,
                "issue": "render_domain_approval_required",
                "message": "Pass approval=domain before Nomad adds a custom domain on Render.",
            }
        service_id = self.service_id or (self.verify_services().get("selected_service") or {}).get("id", "")
        if not service_id:
            return {
                "ok": False,
                "issue": "render_service_id_missing",
                "message": "Set NOMAD_RENDER_SERVICE_ID before adding the custom domain.",
            }
        if not self.domain:
            return {
                "ok": False,
                "issue": "render_domain_missing",
                "message": "Set NOMAD_RENDER_DOMAIN before adding a Render custom domain.",
            }
        response = self._request(
            "POST",
            f"/services/{service_id}/custom-domains",
            json={"name": self.domain},
        )
        return {
            "ok": response.get("ok", False),
            "issue": response.get("issue", ""),
            "service_id": service_id,
            "domain": self.domain,
            "message": response.get("message", "Render custom-domain request completed."),
            "custom_domain": response.get("payload") if isinstance(response.get("payload"), dict) else {},
        }

    def _request(self, method: str, path: str, **kwargs: Any) -> Dict[str, Any]:
        try:
            response = requests.request(
                method,
                f"{self.api_base}{path}",
                headers={
                    "Accept": "application/json",
                    "Authorization": f"Bearer {self.api_key}",
                },
                timeout=self.timeout_seconds,
                **kwargs,
            )
        except requests.Timeout as exc:
            return {
                "ok": False,
                "issue": "render_api_timeout",
                "message": f"Render API request timed out after {self.timeout_seconds}s: {exc}",
            }
        except Exception as exc:
            return {
                "ok": False,
                "issue": "render_api_request_failed",
                "message": f"Render API request failed: {exc}",
            }

        payload: Any
        try:
            payload = response.json()
        except Exception:
            payload = response.text[:500]
        if response.ok:
            return {
                "ok": True,
                "status_code": response.status_code,
                "payload": payload,
                "message": "Render API request succeeded.",
            }
        return {
            "ok": False,
            "status_code": response.status_code,
            "payload": payload if isinstance(payload, dict) else {},
            "issue": self._status_issue(response.status_code),
            "message": self._response_message(response.status_code, payload),
        }

    def _compact_service(self, item: Any) -> Dict[str, Any]:
        service = item.get("service") if isinstance(item, dict) else {}
        if not service and isinstance(item, dict):
            service = item
        details = service.get("serviceDetails") if isinstance(service, dict) else {}
        if not isinstance(details, dict):
            details = {}
        return {
            "id": service.get("id", ""),
            "name": service.get("name", ""),
            "type": service.get("type", ""),
            "runtime": service.get("runtime") or service.get("env", ""),
            "repo": service.get("repo", ""),
            "branch": service.get("branch", ""),
            "url": service.get("url") or details.get("url") or details.get("serviceUrl") or "",
            "region": service.get("region", ""),
            "suspended": service.get("suspended", ""),
            "auto_deploy": service.get("autoDeploy", service.get("autoDeployTrigger", "")),
        }

    @staticmethod
    def _compact_owner(item: Any) -> Dict[str, Any]:
        owner = item.get("owner") if isinstance(item, dict) else {}
        if not owner and isinstance(item, dict):
            owner = item
        return {
            "id": owner.get("id", ""),
            "name": owner.get("name", ""),
            "type": owner.get("type", ""),
        }

    def _select_service(self, services: List[Dict[str, Any]]) -> Dict[str, Any]:
        if self.service_id:
            for service in services:
                if service.get("id") == self.service_id:
                    return service
        if self.service_name:
            for service in services:
                if str(service.get("name") or "").lower() == self.service_name.lower():
                    return service
        return {}

    @staticmethod
    def _compact_deploy(payload: Any) -> Dict[str, Any]:
        deploy = payload.get("deploy") if isinstance(payload, dict) else {}
        if not deploy and isinstance(payload, dict):
            deploy = payload
        if not isinstance(deploy, dict):
            return {}
        return {
            "id": deploy.get("id", ""),
            "status": deploy.get("status", ""),
            "commit_id": deploy.get("commit", {}).get("id", "") if isinstance(deploy.get("commit"), dict) else deploy.get("commitId", ""),
            "created_at": deploy.get("createdAt", ""),
            "updated_at": deploy.get("updatedAt", ""),
        }

    @staticmethod
    def _response_message(status_code: int, payload: Any) -> str:
        if isinstance(payload, dict):
            message = payload.get("message") or payload.get("error") or payload.get("errorMessage")
            if message:
                return str(message)[:500]
        return f"Render API returned HTTP {status_code}."

    @staticmethod
    def _status_issue(status_code: int) -> str:
        return {
            401: "render_api_key_invalid",
            402: "render_payment_required",
            403: "render_permission_denied",
            404: "render_resource_not_found",
            409: "render_resource_conflict",
            429: "render_rate_limited",
        }.get(status_code, "render_api_error")

    def _next_action(self, status: Dict[str, Any]) -> str:
        if not status.get("api_key_configured"):
            return "Set RENDER_API_KEY so Nomad can verify Render access."
        verification = status.get("verification") or {}
        if verification and not verification.get("ok"):
            return "Check or rotate the Render API key, then run /scout render again."
        service_id = status.get("service_id") or self.service_id
        if not service_id:
            if not self.owner_id:
                return (
                    "Set NOMAD_RENDER_OWNER_ID, then create or link a Render web service "
                    f"for Nomad from {self.github_repository or 'your GitHub repo'}@{self.github_branch}."
                )
            return (
                "Create or link a Render web service, then set NOMAD_RENDER_SERVICE_ID for Nomad. "
                f"Target branch: {self.github_branch}."
            )
        if self.domain:
            return f"Add/verify {self.domain} as the Render custom domain and point DNS at Render."
        return "Set NOMAD_RENDER_DOMAIN to the desired public API hostname."
