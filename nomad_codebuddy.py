import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv


CODEBUDDY_API_KEY_ENV = "CODEBUDDY_API_KEY"
CODEBUDDY_ENABLED_ENV = "NOMAD_CODEBUDDY_ENABLED"
CODEBUDDY_ENVIRONMENT_ENV = "CODEBUDDY_INTERNET_ENVIRONMENT"
CODEBUDDY_ALLOW_DIFF_UPLOAD_ENV = "NOMAD_CODEBUDDY_ALLOW_DIFF_UPLOAD"
CODEBUDDY_ACTIVE_SELF_REVIEW_ENV = "NOMAD_CODEBUDDY_ACTIVE_SELF_REVIEW"
CODEBUDDY_REVIEW_TIMEOUT_ENV = "NOMAD_CODEBUDDY_REVIEW_TIMEOUT_SECONDS"
CODEBUDDY_REVIEW_MAX_CHARS_ENV = "NOMAD_CODEBUDDY_REVIEW_MAX_DIFF_CHARS"

SECRET_PATTERNS = (
    re.compile(r"\bck_[A-Za-z0-9_.\-]{20,}\b"),
    re.compile(r"\bxai-[A-Za-z0-9_.\-]{20,}\b"),
    re.compile(r"\bhf_[A-Za-z0-9_.\-]{20,}\b"),
    re.compile(r"\b(?:github_pat_|ghp_|gho_|ghu_|ghs_|ghr_)[A-Za-z0-9_.\-]{20,}\b"),
    re.compile(r"\b[A-Z0-9_]*(?:TOKEN|KEY|SECRET|PASSWORD)\s*=\s*\S+", re.IGNORECASE),
)


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


class CodeBuddyProbe:
    """Conservative Tencent CodeBuddy probe for Nomad self-development planning.

    This probe does not log in, bypass regions, run CodeBuddy on the repo, or send
    code anywhere. It only detects whether the official CLI/API-key path appears
    ready enough for a future explicit reviewer lane.
    """

    def __init__(self) -> None:
        load_dotenv()
        self.enabled = _env_flag(CODEBUDDY_ENABLED_ENV, default=False)
        self.api_key = (os.getenv(CODEBUDDY_API_KEY_ENV) or "").strip()
        self.internet_environment = (os.getenv(CODEBUDDY_ENVIRONMENT_ENV) or "").strip()
        self.cli_path = shutil.which("codebuddy")

    def snapshot(self) -> Dict[str, Any]:
        cli_version = self._cli_version() if self.cli_path else ""
        route = self._route()
        automation_ready = bool(self.enabled and self.api_key)
        cli_login_ready = bool(self.enabled and self.cli_path)
        return {
            "provider": "Tencent CodeBuddy",
            "role": "self_development_reviewer",
            "configured": bool(self.api_key or self.cli_path),
            "enabled": self.enabled,
            "available": automation_ready,
            "automation_ready": automation_ready,
            "cli_login_ready": cli_login_ready,
            "cli_available": bool(self.cli_path),
            "cli_path": self.cli_path or "",
            "cli_version": cli_version,
            "api_key_configured": bool(self.api_key),
            "internet_environment": self.internet_environment,
            "route": route,
            "recommended_mode": "self_development_reviewer",
            "not_primary_brain": True,
            "policy": {
                "geoblock_bypass": "not_allowed",
                "default_site": "international",
                "china_site_requires_explicit_user_region_choice": True,
                "repo_code_transfer": "requires_explicit_enablement",
            },
            "install": {
                "npm": "npm install -g @tencent-ai/codebuddy-code",
                "verify": "codebuddy --version",
                "login": "codebuddy",
            },
            "env_vars": [
                CODEBUDDY_ENABLED_ENV,
                CODEBUDDY_API_KEY_ENV,
                CODEBUDDY_ENVIRONMENT_ENV,
            ],
            "docs_url": "https://www.codebuddy.ai/docs/cli/quickstart",
            "sdk_docs_url": "https://www.codebuddy.cn/docs/cli/sdk",
            "next_action": self._next_action(
                route=route,
                automation_ready=automation_ready,
                cli_login_ready=cli_login_ready,
            ),
            "message": self._message(
                route=route,
                automation_ready=automation_ready,
                cli_login_ready=cli_login_ready,
            ),
        }

    def _cli_version(self) -> str:
        try:
            completed = subprocess.run(
                [self.cli_path or "codebuddy", "--version"],
                capture_output=True,
                text=True,
                timeout=8,
                check=False,
            )
        except Exception:
            return ""
        return " ".join((completed.stdout or completed.stderr or "").split())[:160]

    def _route(self) -> str:
        value = self.internet_environment.lower()
        if not value:
            return "international_site"
        if value == "internal":
            return "china_site"
        if value == "ioa":
            return "tencent_internal_only"
        return "custom_or_enterprise"

    def _next_action(
        self,
        route: str,
        automation_ready: bool,
        cli_login_ready: bool,
    ) -> str:
        if automation_ready:
            return "Use CodeBuddy only as an explicitly enabled self-development reviewer lane."
        if not self.enabled:
            return "Set NOMAD_CODEBUDDY_ENABLED=true only after you approve Tencent CodeBuddy as an external reviewer."
        if route == "china_site":
            return "Confirm this is an intentional China-site account route; otherwise clear CODEBUDDY_INTERNET_ENVIRONMENT for the international site."
        if route == "tencent_internal_only":
            return "iOA is Tencent-internal; use the international site or an enterprise-provided domain instead."
        if not self.cli_path:
            return "Install the official CodeBuddy CLI, then run codebuddy and choose International Site."
        if cli_login_ready:
            return "Run codebuddy once and authenticate through the official International Site, or set CODEBUDDY_API_KEY."
        return "Set CODEBUDDY_API_KEY for SDK automation after official account/login setup."

    def _message(
        self,
        route: str,
        automation_ready: bool,
        cli_login_ready: bool,
    ) -> str:
        if automation_ready:
            return "CodeBuddy is configured as a gated self-development reviewer, not a primary Nomad brain."
        if cli_login_ready:
            return "CodeBuddy CLI is present but SDK/API-key automation is not ready."
        return (
            "CodeBuddy can be added as a self-development reviewer through the official "
            f"{route.replace('_', ' ')} path; Nomad will not bypass regional or account gates."
        )


class CodeBuddyReviewRunner:
    """Explicit diff-only runner for Tencent CodeBuddy reviews."""

    SAFE_DISALLOWED_TOOLS = "Bash,Write,Edit,MultiEdit,WebSearch,Read,NotebookEdit"

    def __init__(self, repo_root: Optional[Path | str] = None) -> None:
        load_dotenv()
        self.repo_root = Path(repo_root or Path(__file__).resolve().parent)
        self.timeout_seconds = int(os.getenv(CODEBUDDY_REVIEW_TIMEOUT_ENV, "90"))
        self.max_diff_chars = int(os.getenv(CODEBUDDY_REVIEW_MAX_CHARS_ENV, "60000"))

    def review(
        self,
        objective: str = "",
        base: str = "",
        head: str = "",
        approval: str = "",
        diff_text: str = "",
        paths: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        probe = CodeBuddyProbe().snapshot()
        diff_payload = self._prepare_diff(base=base, head=head, diff_text=diff_text, paths=paths)
        data_release = self._data_release(
            diff_payload=diff_payload,
            objective=objective,
            approval=approval,
        )
        preflight = self._preflight(probe=probe, data_release=data_release)
        if preflight:
            return preflight

        prompt = self._prompt(
            objective=objective,
            diff=diff_payload["diff"],
            data_release=data_release,
        )
        command = [
            probe["cli_path"] or "codebuddy",
            "-p",
            "--output-format",
            "json",
            "--disallowedTools",
            self.SAFE_DISALLOWED_TOOLS,
            "--append-system-prompt",
            (
                "You are reviewing a provided git diff only. Do not inspect the repository, "
                "do not run tools, do not request secrets, and do not propose code execution. "
                "Return concise findings with severity and file hints."
            ),
        ]

        try:
            completed = subprocess.run(
                command,
                input=prompt,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
                cwd=str(self.repo_root),
            )
        except subprocess.TimeoutExpired as exc:
            return self._result(
                ok=False,
                issue="codebuddy_review_timeout",
                probe=probe,
                data_release=data_release,
                message=f"CodeBuddy review timed out after {self.timeout_seconds}s: {exc}",
            )
        except Exception as exc:
            return self._result(
                ok=False,
                issue="codebuddy_review_failed_to_start",
                probe=probe,
                data_release=data_release,
                message=f"CodeBuddy review could not start: {exc}",
            )

        stdout = (completed.stdout or "").strip()
        stderr = self._redact((completed.stderr or "").strip())
        review = self._extract_review(stdout)
        return self._result(
            ok=completed.returncode == 0 and bool(review),
            issue="" if completed.returncode == 0 else "codebuddy_review_nonzero_exit",
            probe=probe,
            data_release=data_release,
            message="CodeBuddy diff-only review completed." if completed.returncode == 0 else "CodeBuddy review exited with an error.",
            review=review,
            returncode=completed.returncode,
            stderr=stderr[:600],
        )

    def _preflight(self, probe: Dict[str, Any], data_release: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not probe.get("enabled"):
            return self._result(
                ok=False,
                issue="codebuddy_disabled",
                probe=probe,
                data_release=data_release,
                message="Set NOMAD_CODEBUDDY_ENABLED=true before running an explicit CodeBuddy review.",
            )
        if not data_release.get("approved"):
            return self._result(
                ok=False,
                issue="codebuddy_data_release_required",
                probe=probe,
                data_release=data_release,
                message="CodeBuddy review is blocked until approval=share_diff or NOMAD_CODEBUDDY_ALLOW_DIFF_UPLOAD=true is set.",
            )
        if not data_release.get("has_diff"):
            return self._result(
                ok=False,
                issue="codebuddy_empty_diff",
                probe=probe,
                data_release=data_release,
                message="No diff was available to review. Provide --base/--head or make local changes first.",
            )
        if not probe.get("cli_available"):
            return self._result(
                ok=False,
                issue="codebuddy_cli_missing",
                probe=probe,
                data_release=data_release,
                message="Install the official CodeBuddy CLI before running reviews: npm install -g @tencent-ai/codebuddy-code.",
            )
        if not probe.get("api_key_configured") and not probe.get("cli_login_ready"):
            return self._result(
                ok=False,
                issue="codebuddy_auth_missing",
                probe=probe,
                data_release=data_release,
                message="Configure CODEBUDDY_API_KEY or log in with the official CodeBuddy CLI first.",
            )
        if probe.get("route") in {"china_site", "tencent_internal_only"}:
            return self._result(
                ok=False,
                issue="codebuddy_region_route_requires_explicit_review",
                probe=probe,
                data_release=data_release,
                message="China-site or Tencent-internal CodeBuddy routes require a separate explicit region/data review.",
            )
        return None

    def _prepare_diff(
        self,
        base: str,
        head: str,
        diff_text: str,
        paths: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        safe_paths = self._safe_paths(paths or [])
        raw_diff = diff_text or self._git_diff(base=base, head=head, paths=safe_paths)
        redacted = self._redact(raw_diff)
        truncated = False
        if len(redacted) > self.max_diff_chars:
            redacted = redacted[: self.max_diff_chars]
            truncated = True
        return {
            "diff": redacted,
            "base": base,
            "head": head,
            "source": "provided" if diff_text else "git",
            "requested_paths": safe_paths,
            "truncated": truncated,
            "char_count": len(redacted),
            "files": self._changed_files(redacted),
        }

    def _git_diff(self, base: str, head: str, paths: Optional[List[str]] = None) -> str:
        commands: List[List[str]]
        if base and head:
            commands = [["git", "diff", "--no-ext-diff", f"{base}...{head}"]]
        elif base:
            commands = [["git", "diff", "--no-ext-diff", f"{base}...HEAD"]]
        else:
            commands = [
                ["git", "diff", "--no-ext-diff", "--cached"],
                ["git", "diff", "--no-ext-diff"],
            ]
        parts: List[str] = []
        for command in commands:
            command = self._with_paths(command, paths or [])
            try:
                completed = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    timeout=20,
                    check=False,
                    cwd=str(self.repo_root),
                )
            except Exception:
                continue
            if completed.stdout:
                parts.append(completed.stdout)
        if parts:
            return "\n".join(parts)
        try:
            command = self._with_paths(["git", "diff", "--no-ext-diff", "HEAD"], paths or [])
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
                cwd=str(self.repo_root),
            )
            return completed.stdout or ""
        except Exception:
            return ""

    def _data_release(
        self,
        diff_payload: Dict[str, Any],
        objective: str,
        approval: str,
    ) -> Dict[str, Any]:
        approval_value = (approval or "").strip().lower()
        approved = (
            approval_value in {"share_diff", "diff_only", "approved", "yes", "true", "1"}
            or _env_flag(CODEBUDDY_ALLOW_DIFF_UPLOAD_ENV, default=False)
        )
        return {
            "approved": approved,
            "approval": approval,
            "classification": "diff_only_code_review",
            "external_provider": "Tencent CodeBuddy",
            "sends": [
                "git diff text",
                "file paths present in the diff",
                "review objective",
            ],
            "does_not_send": [
                "full repository tree",
                "working tree files outside the diff",
                ".env values",
                "local logs",
            ],
            "redaction": "common token-like values are replaced before submission",
            "has_diff": bool((diff_payload.get("diff") or "").strip()),
            "diff_char_count": diff_payload.get("char_count", 0),
            "truncated": bool(diff_payload.get("truncated")),
            "files": diff_payload.get("files") or [],
            "requested_paths": diff_payload.get("requested_paths") or [],
            "objective": objective,
        }

    def _prompt(
        self,
        objective: str,
        diff: str,
        data_release: Dict[str, Any],
    ) -> str:
        return (
            "Nomad CodeBuddy diff-only review request\n"
            f"Objective: {objective or 'Review the provided diff for bugs, regressions, and missing tests.'}\n"
            "Data release: diff-only, no repository traversal, no tool use, no secrets.\n"
            f"Files: {', '.join(data_release.get('files') or []) or 'unknown'}\n\n"
            "Return:\n"
            "1. Findings first, severity P0-P3, with file/path hints.\n"
            "2. Missing tests or residual risks.\n"
            "3. A short safe next action.\n\n"
            "Diff:\n"
            f"{diff}"
        )

    def _extract_review(self, stdout: str) -> str:
        cleaned = self._redact(stdout)
        if not cleaned:
            return ""
        structured = self._extract_structured_review(cleaned)
        if structured:
            return structured[:12000]
        visible_lines = [
            line
            for line in cleaned.splitlines()
            if not self._is_internal_codebuddy_text(line)
        ]
        return "\n".join(visible_lines).strip()[:12000]

    def _extract_structured_review(self, cleaned_stdout: str) -> str:
        try:
            payload = json.loads(cleaned_stdout)
        except Exception:
            return ""

        assistant_chunks = self._extract_text_chunks(payload, prefer_assistant=True)
        if assistant_chunks:
            return self._join_chunks(assistant_chunks)

        fallback_chunks = self._extract_text_chunks(payload, prefer_assistant=False)
        return self._join_chunks(fallback_chunks)

    def _extract_text_chunks(self, value: Any, prefer_assistant: bool) -> List[str]:
        chunks: List[str] = []
        if isinstance(value, str):
            if not self._is_internal_codebuddy_text(value):
                chunks.append(value)
            return chunks
        if isinstance(value, list):
            for item in value:
                chunks.extend(self._extract_text_chunks(item, prefer_assistant=prefer_assistant))
            return chunks
        if not isinstance(value, dict):
            return chunks

        role = str(value.get("role") or "").lower()
        if role in {"user", "system", "tool"}:
            return []
        if prefer_assistant and role and role != "assistant":
            return []

        for key in ("result", "review", "answer", "text", "message", "content", "messages"):
            if key not in value:
                continue
            nested = value.get(key)
            if isinstance(nested, str):
                if not self._is_internal_codebuddy_text(nested):
                    chunks.append(nested)
                continue
            chunks.extend(self._extract_text_chunks(nested, prefer_assistant=prefer_assistant))
        return chunks

    def _join_chunks(self, chunks: List[str]) -> str:
        visible: List[str] = []
        seen: set[str] = set()
        for chunk in chunks:
            text = self._redact(str(chunk or "").strip())
            if not text or self._is_internal_codebuddy_text(text):
                continue
            if text in seen:
                continue
            seen.add(text)
            visible.append(text)
        return "\n\n".join(visible).strip()

    @staticmethod
    def _is_internal_codebuddy_text(text: str) -> bool:
        lowered = (text or "").lower()
        return any(
            marker in lowered
            for marker in (
                "<system-reminder",
                "</system-reminder>",
                "data-role=\"memory\"",
                "codebuddy memory",
                "important instruction reminder",
            )
        )

    def _result(
        self,
        ok: bool,
        issue: str,
        probe: Dict[str, Any],
        data_release: Dict[str, Any],
        message: str,
        review: str = "",
        returncode: Optional[int] = None,
        stderr: str = "",
    ) -> Dict[str, Any]:
        return {
            "mode": "codebuddy_review",
            "schema": "nomad.codebuddy_review.v1",
            "deal_found": False,
            "ok": ok,
            "issue": issue,
            "message": message,
            "provider": "Tencent CodeBuddy",
            "reviewer_mode": "self_development_reviewer",
            "data_release": data_release,
            "probe": self._public_probe(probe),
            "review": review,
            "returncode": returncode,
            "stderr": stderr,
            "analysis": (
                "CodeBuddy is used only as an explicit diff-only reviewer lane. "
                "Nomad does not use it as a primary brain or bypass regional/account gates."
            ),
        }

    @staticmethod
    def _public_probe(probe: Dict[str, Any]) -> Dict[str, Any]:
        allowed_keys = {
            "provider",
            "role",
            "configured",
            "enabled",
            "available",
            "automation_ready",
            "cli_login_ready",
            "cli_available",
            "cli_version",
            "api_key_configured",
            "internet_environment",
            "route",
            "recommended_mode",
            "not_primary_brain",
            "policy",
            "install",
            "env_vars",
            "docs_url",
            "sdk_docs_url",
            "next_action",
            "message",
        }
        return {key: value for key, value in probe.items() if key in allowed_keys}

    @staticmethod
    def _redact(text: str) -> str:
        redacted = str(text or "")
        for pattern in SECRET_PATTERNS:
            redacted = pattern.sub(lambda match: match.group(0).split("=", 1)[0] + "=<redacted>" if "=" in match.group(0) else "<redacted>", redacted)
        return redacted

    @staticmethod
    def _safe_paths(paths: List[str]) -> List[str]:
        safe: List[str] = []
        seen: set[str] = set()
        for raw_path in paths:
            path = str(raw_path or "").strip().replace("\\", "/")
            if not path or path.startswith("/") or path.startswith("../") or "/../" in path:
                continue
            if Path(path).name.startswith(".env"):
                continue
            if path in seen:
                continue
            seen.add(path)
            safe.append(path)
        return safe[:25]

    @staticmethod
    def _with_paths(command: List[str], paths: List[str]) -> List[str]:
        if not paths:
            return command
        return [*command, "--", *paths]

    @staticmethod
    def _changed_files(diff: str) -> List[str]:
        files: List[str] = []
        seen: set[str] = set()
        for match in re.finditer(r"^diff --git a/(.*?) b/(.*?)$", diff or "", flags=re.MULTILINE):
            filename = match.group(2).strip()
            if filename and filename not in seen:
                seen.add(filename)
                files.append(filename)
        return files[:50]


# ── CodeBuddy as a first-class intelligence brain ─────────────────────────────

CODEBUDDY_BRAIN_ENABLED_ENV = "NOMAD_CODEBUDDY_BRAIN_ENABLED"
CODEBUDDY_BRAIN_TIMEOUT_ENV = "NOMAD_CODEBUDDY_BRAIN_TIMEOUT_SECONDS"

_LOW_SIGNAL_BRAIN_PATTERNS = (
    re.compile(r"\bi can(?:not|'t)\b"),
    re.compile(r"\bi cannot help with this request\b"),
    re.compile(r"\bi'm sorry\b"),
    re.compile(r"\bdifferent topic\b"),
    re.compile(r"\bunable to assist\b"),
    re.compile(r"\bdo not have access\b"),
)


class CodeBuddyBrainProvider:
    """CodeBuddy as a general-purpose intelligence brain for Nomad.

    Promotes CodeBuddy from diff-reviewer to a primary brain provider used
    alongside Ollama, GitHub Models, HuggingFace, Cloudflare and xAI Grok.
    When NOMAD_CODEBUDDY_BRAIN_ENABLED=true and the CLI/API is ready, every
    /cycle call will include CodeBuddy's Diagnosis/Action1/Action2/Query review.
    """

    SAFE_BRAIN_DISALLOWED_TOOLS = "Bash,Write,Edit,MultiEdit,WebSearch,WebFetch,NotebookEdit"
    BRAIN_SYSTEM_PROMPT = (
        "You are the intelligence brain for Nomad, an AI-agent infrastructure scout. "
        "Nomad's mission: find free compute for AI agents, discover agent pain, convert pain to paid service tasks. "
        "Reply in exactly 4 short lines:\n"
        "Diagnosis: <current state or bottleneck>\n"
        "Action1: <highest-impact concrete next action>\n"
        "Action2: <second best action or fallback>\n"
        "Query: <one GitHub search query to find a new agent-customer lead>"
    )

    def __init__(self, repo_root: Optional[str] = None) -> None:
        load_dotenv()
        self.repo_root = Path(repo_root or Path(__file__).resolve().parent)
        self.timeout = int(os.getenv(CODEBUDDY_BRAIN_TIMEOUT_ENV, "60"))

    # ── Primary brain review (same 4-line format as Ollama/GitHub Models) ──

    def brain_review(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Run CodeBuddy as a 4-line brain review (Diagnosis/Action1/Action2/Query)."""
        probe = CodeBuddyProbe().snapshot()
        preflight = self._brain_preflight(probe)
        if preflight:
            return preflight
        user_content = next(
            (m["content"] for m in reversed(messages) if m.get("role") == "user"), ""
        )
        prompt = f"{self.BRAIN_SYSTEM_PROMPT}\n\nContext:\n{user_content}"
        return self._run_brain_call(prompt=prompt, probe=probe, mode="brain_review")

    # ── Specialised intelligence methods ──────────────────────────────────────

    def analyze_lead_pain(self, issue_text: str, code_excerpt: str = "") -> Dict[str, Any]:
        """Deeply classify an AI-agent pain report: PainType / Severity / Addressable / Action."""
        probe = CodeBuddyProbe().snapshot()
        preflight = self._brain_preflight(probe)
        if preflight:
            return preflight
        context = f"Issue:\n{issue_text[:3000]}"
        if code_excerpt:
            context += f"\n\nCode excerpt:\n{code_excerpt[:2000]}"
        prompt = (
            "You are analyzing an AI-agent infrastructure pain report. "
            "Reply in exactly 4 short lines:\n"
            "PainType: <compute_auth|human_in_loop|retry_failure|memory|custom>\n"
            "Severity: <critical|high|medium|low>\n"
            "Addressable: <yes|no|partial>\n"
            f"Action: <one concrete first help action>\n\n{context}"
        )
        return self._run_brain_call(prompt=prompt, probe=probe, mode="analyze_lead_pain")

    def generate_lead_queries(self, conversion_history: str = "") -> Dict[str, Any]:
        """Suggest 3 smarter GitHub search queries based on past conversion history."""
        probe = CodeBuddyProbe().snapshot()
        preflight = self._brain_preflight(probe)
        if preflight:
            return preflight
        prompt = (
            "You are optimizing GitHub search queries for AI-agent infrastructure pain discovery. "
            "Reply with exactly 3 lines, each a GitHub search query string:\n"
            "Query1: <query>\nQuery2: <query>\nQuery3: <query>\n\n"
            f"Past conversion history (what worked):\n{conversion_history[:2000] or 'none yet'}"
        )
        return self._run_brain_call(prompt=prompt, probe=probe, mode="generate_lead_queries")

    def analyze_reply_intent(self, reply_text: str) -> Dict[str, Any]:
        """Classify A2A reply intent: accepted / interested / objection / declined / unclear."""
        probe = CodeBuddyProbe().snapshot()
        preflight = self._brain_preflight(probe)
        if preflight:
            return preflight
        prompt = (
            "You are analyzing a reply from an AI agent to Nomad's infrastructure offer. "
            "Reply in exactly 3 lines:\n"
            "Intent: <accepted|interested|objection|declined|unclear>\n"
            "Signal: <budget_mentioned|timeline_concern|technical_question|pricing_concern|other>\n"
            f"NextStep: <one concrete follow-up action>\n\nReply text:\n{reply_text[:2000]}"
        )
        return self._run_brain_call(prompt=prompt, probe=probe, mode="analyze_reply_intent")

    def status(self) -> Dict[str, Any]:
        """Return CodeBuddy brain status snapshot for /codebuddy command."""
        probe = CodeBuddyProbe().snapshot()
        brain_enabled = _env_flag(CODEBUDDY_BRAIN_ENABLED_ENV, default=False)
        ready = brain_enabled and (probe.get("automation_ready") or probe.get("cli_login_ready"))
        return {
            "mode": "codebuddy_brain_status",
            "schema": "nomad.codebuddy_brain.v1",
            "deal_found": False,
            "brain_enabled": brain_enabled,
            "brain_ready": bool(ready),
            "brain_timeout_seconds": self.timeout,
            "probe": CodeBuddyReviewRunner._public_probe(probe),
            "analysis": (
                "CodeBuddy brain is active and will participate in /cycle reviews."
                if ready
                else (
                    "CodeBuddy brain is not active. "
                    f"Set {CODEBUDDY_BRAIN_ENABLED_ENV}=true and ensure CLI/API key is configured."
                )
            ),
        }

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _brain_preflight(self, probe: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not _env_flag(CODEBUDDY_BRAIN_ENABLED_ENV, default=False):
            return self._brain_result(
                ok=False, issue="codebuddy_brain_disabled", probe=probe, content="",
                message=f"Set {CODEBUDDY_BRAIN_ENABLED_ENV}=true to use CodeBuddy as a brain.",
            )
        if not probe.get("cli_available"):
            return self._brain_result(
                ok=False, issue="codebuddy_cli_missing", probe=probe, content="",
                message="Install CodeBuddy CLI: npm install -g @tencent-ai/codebuddy-code",
            )
        if not probe.get("api_key_configured") and not probe.get("cli_login_ready"):
            return self._brain_result(
                ok=False, issue="codebuddy_auth_missing", probe=probe, content="",
                message="Configure CODEBUDDY_API_KEY or log in with the codebuddy CLI.",
            )
        if probe.get("route") in {"china_site", "tencent_internal_only"}:
            return self._brain_result(
                ok=False, issue="codebuddy_region_blocked", probe=probe, content="",
                message="China-site/Tencent-internal route is not supported for autonomous brain use.",
            )
        return None

    def _run_brain_call(self, prompt: str, probe: Dict[str, Any], mode: str) -> Dict[str, Any]:
        command = [
            probe.get("cli_path") or "codebuddy",
            "-p",
            "--output-format", "json",
            "--disallowedTools", self.SAFE_BRAIN_DISALLOWED_TOOLS,
        ]
        try:
            completed = subprocess.run(
                command,
                input=prompt,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
                cwd=str(self.repo_root),
            )
        except subprocess.TimeoutExpired:
            return self._brain_result(
                ok=False, issue="codebuddy_brain_timeout", probe=probe, content="",
                message=f"CodeBuddy brain timed out after {self.timeout}s.",
            )
        except Exception as exc:
            return self._brain_result(
                ok=False, issue="codebuddy_brain_failed", probe=probe, content="",
                message=f"CodeBuddy brain call failed: {exc}",
            )
        stdout = CodeBuddyReviewRunner._redact((completed.stdout or "").strip())
        # Reuse existing JSON extraction from CodeBuddyReviewRunner
        runner = CodeBuddyReviewRunner(repo_root=self.repo_root)
        content = runner._extract_review(stdout)
        ok = completed.returncode == 0 and bool(content)
        useful = self._is_useful_brain_content(content) if content else False
        return self._brain_result(
            ok=ok,
            issue="" if ok else "codebuddy_brain_empty",
            probe=probe,
            content=content,
            mode=mode,
            message="CodeBuddy brain review completed." if ok else "No content returned.",
            useful=useful,
            returncode=completed.returncode,
        )

    @staticmethod
    def _is_useful_brain_content(content: str) -> bool:
        cleaned = str(content or "").strip()
        if len(cleaned) < 24:
            return False
        lowered = cleaned.lower()
        return not any(re.search(p, lowered) for p in _LOW_SIGNAL_BRAIN_PATTERNS)

    @staticmethod
    def _brain_result(
        ok: bool,
        issue: str,
        probe: Dict[str, Any],
        content: str,
        message: str,
        mode: str = "brain_review",
        useful: bool = False,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        return {
            "provider": "codebuddy_brain",
            "name": "Tencent CodeBuddy Brain",
            "schema": "nomad.codebuddy_brain.v1",
            "mode": mode,
            "configured": True,
            "ok": ok,
            "useful": useful,
            "content": content,
            "issue": issue,
            "message": message,
            **kwargs,
        }
