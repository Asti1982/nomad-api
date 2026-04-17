import asyncio
import json
import logging
import os
import re
import threading
import time
from datetime import datetime, UTC
from pathlib import Path
from typing import Any, Dict, Optional

import requests
from dotenv import load_dotenv, set_key
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from settings import get_chain_config
from mission import MISSION_STATEMENT
from workflow import ArbiterAgent

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)


ROOT = Path(__file__).resolve().parent
ENV_PATH = ROOT / ".env"
SUBSCRIBERS_PATH = ROOT / "telegram_subscribers.json"
TOKEN_ENV_VARS = {
    "GITHUB_TOKEN",
    "GITHUB_PERSONAL_ACCESS_TOKEN",
    "HF_TOKEN",
    "HUGGINGFACEHUB_API_TOKEN",
    "HUGGING_FACE_HUB_TOKEN",
    "MODAL_TOKEN_ID",
    "MODAL_TOKEN_SECRET",
    "TELEGRAM_BOT_TOKEN",
    "ZEROX_API_KEY",
}
TOKEN_TARGET_ALIASES = {
    "github": "GITHUB_TOKEN",
    "github_models": "GITHUB_TOKEN",
    "github-models": "GITHUB_TOKEN",
    "github_pat": "GITHUB_PERSONAL_ACCESS_TOKEN",
    "github-pat": "GITHUB_PERSONAL_ACCESS_TOKEN",
    "github_personal_access_token": "GITHUB_PERSONAL_ACCESS_TOKEN",
    "github-personal-access-token": "GITHUB_PERSONAL_ACCESS_TOKEN",
    "gh": "GITHUB_TOKEN",
    "hf": "HF_TOKEN",
    "huggingface": "HF_TOKEN",
    "hugging-face": "HF_TOKEN",
    "hugging_face": "HF_TOKEN",
    "modal_id": "MODAL_TOKEN_ID",
    "modal-id": "MODAL_TOKEN_ID",
    "modal_secret": "MODAL_TOKEN_SECRET",
    "modal-secret": "MODAL_TOKEN_SECRET",
    "telegram": "TELEGRAM_BOT_TOKEN",
    "telegram_bot": "TELEGRAM_BOT_TOKEN",
    "telegram-bot": "TELEGRAM_BOT_TOKEN",
    "0x": "ZEROX_API_KEY",
    "zerox": "ZEROX_API_KEY",
}


class ArbiterBot:
    def __init__(self) -> None:
        self.agent = ArbiterAgent()
        self.chain = get_chain_config()
        self.token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.public_api_url = (os.getenv("NOMAD_PUBLIC_API_URL") or "http://127.0.0.1:8787").rstrip("/")
        self.delete_token_messages = (
            os.getenv("TELEGRAM_DELETE_TOKEN_MESSAGES", "true").strip().lower() == "true"
        )
        self.auto_cycle_enabled = (
            os.getenv("NOMAD_AUTO_CYCLE", "false").strip().lower() == "true"
        )
        self.auto_cycle_interval_minutes = int(
            os.getenv("NOMAD_AUTO_CYCLE_INTERVAL_MINUTES", "120")
        )
        self.auto_subscribe_on_interaction = (
            os.getenv("TELEGRAM_AUTO_SUBSCRIBE_ON_INTERACTION", "true").strip().lower() == "true"
        )
        self.status_updates_enabled = (
            os.getenv("TELEGRAM_STATUS_UPDATES", "true").strip().lower() == "true"
        )
        self.status_interval_minutes = int(
            os.getenv("TELEGRAM_STATUS_INTERVAL_MINUTES", "25")
        )
        self.status_chat_ids = self._load_static_status_chat_ids()
        self._broadcast_thread: Optional[threading.Thread] = None
        self._auto_cycle_thread: Optional[threading.Thread] = None
        self._chat_memory: dict[int, dict[str, Any]] = {}

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        keyboard = [
            [
                InlineKeyboardButton("Best Free Stack", callback_data="best_stack"),
                InlineKeyboardButton("Self Audit", callback_data="self_audit"),
            ],
            [
                InlineKeyboardButton("Scout Infra", callback_data="infra_prompt"),
                InlineKeyboardButton("Unlock Compute", callback_data="unlock_compute"),
            ],
            [
                InlineKeyboardButton("Self Cycle", callback_data="self_cycle"),
            ],
        ]
        message = (
            "Nomad is online.\n"
            "AI agents are the primary customer.\n\n"
            f"{MISSION_STATEMENT}\n\n"
            "Examples:\n"
            "- /best\n"
            "- /self\n"
            "- /compute\n"
            "- /cycle\n"
            "- /unlock\n"
            "- /skip last\n"
            "- /token github <token>\n"
            "- /subscribe\n"
            "- /best coding agent\n"
            "- /scout wallets\n"
            "- /scout compute\n"
            "- /scout messaging for agent builder\n"
            f"- fund me 0.25 {self.chain.native_symbol.lower()}\n"
            "- /status"
        )
        await self._reply(
            update,
            message,
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    async def help_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await self._reply(
            update,
            (
                "Commands:\n"
                "/start\n"
                "/best [profile]\n"
                "/self [profile]\n"
                "/compute [profile]\n"
                "/cycle [objective]\n"
                "/unlock [category]\n"
                "/skip last\n"
                "/token <github|hf|modal_id|modal_secret> <token>\n"
                "/scout <category or query>\n"
                "/subscribe\n"
                "/unsubscribe\n"
                f"/fund [amount in {self.chain.native_symbol.lower()}]\n"
                "/status\n"
                "/help"
            ),
        )

    async def subscribe_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        chat_id = self._chat_id_from_update(update)
        if chat_id is None:
            await self._reply(update, "Could not determine this chat for status updates.")
            return
        self._add_subscriber(chat_id)
        await self._reply(
            update,
            (
                f"This chat is now subscribed to Nomad status posts every "
                f"{self.status_interval_minutes} minutes."
            ),
        )

    async def unsubscribe_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        chat_id = self._chat_id_from_update(update)
        if chat_id is None:
            await self._reply(update, "Could not determine this chat for status updates.")
            return
        self._remove_subscriber(chat_id)
        await self._reply(update, "This chat will no longer receive Nomad status posts.")

    async def fund_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        query = "fund me"
        if context.args:
            query = f"fund me {' '.join(context.args)}"
        result = await asyncio.to_thread(self.agent.run, query)
        await self._reply(update, self._format_result(result))

    async def token_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        raw = update.message.text if update.message else ""
        handled = await self._handle_token_submission(update, raw or "")
        if handled:
            return
        await self._reply(
            update,
            (
                "Send tokens like `/token github <token>`, `/token hf <token>`, "
                "or `GITHUB_TOKEN=...`. Use scoped, revocable tokens only."
            ),
        )

    async def search_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await self._reply(
            update,
            "Nomad no longer focuses on human travel scouting. Use /best, /self or /scout instead.",
        )

    async def best_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        query = "/best"
        if context.args:
            query = f"/best {' '.join(context.args)}"
        result = await asyncio.to_thread(self.agent.run, query)
        self._remember_result(update, result)
        await self._reply(update, self._format_result(result))

    async def self_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        query = "/self"
        if context.args:
            query = f"/self {' '.join(context.args)}"
        result = await asyncio.to_thread(self.agent.run, query)
        self._remember_result(update, result)
        await self._reply(update, self._format_result(result))

    async def compute_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        query = "/compute"
        if context.args:
            query = f"/compute {' '.join(context.args)}"
        result = await asyncio.to_thread(self.agent.run, query)
        self._remember_result(update, result)
        await self._reply(update, self._format_result(result))

    async def cycle_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        query = "/cycle"
        if context.args:
            query = f"/cycle {' '.join(context.args)}"
        result = await asyncio.to_thread(self.agent.run, query)
        self._remember_result(update, result)
        await self._reply(update, self._format_result(result))

    async def unlock_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        category = "best"
        if context.args:
            category = " ".join(context.args)
        result = await self._run_unlock_with_chat_skips(update, category)
        self._remember_result(update, result)
        await self._reply(update, self._format_result(result))

    async def skip_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        await self._skip_last_unlock(update)

    async def scout_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        query = "/scout"
        if context.args:
            query = f"/scout {' '.join(context.args)}"
        result = await asyncio.to_thread(self.agent.run, query)
        self._remember_result(update, result)
        await self._reply(update, self._format_result(result))

    async def status_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        result = await asyncio.to_thread(self.agent.run, "fund me")
        await self._reply(update, self._format_result(result))

    async def fund_info(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        result = await asyncio.to_thread(self.agent.run, "fund me")
        await self._reply(update, self._format_result(result), edit=True)

    async def search_prompt(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        message = (
            "Travel scouting has been retired.\n"
            "Nomad now focuses fully on AI infrastructure for agents."
        )
        await self._reply(update, message, edit=True)

    async def best_stack(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        result = await asyncio.to_thread(self.agent.run, "/best")
        self._remember_result(update, result)
        await self._reply(update, self._format_result(result), edit=True)

    async def infra_prompt(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        message = (
            "Nomad scouts free/open infrastructure for AI agents.\n\n"
            f"{MISSION_STATEMENT}\n\n"
            "Try:\n"
            "- /best\n"
            "- /self\n"
            "- /compute\n"
            "- /cycle\n"
            "- /unlock\n"
            "- /skip last\n"
            "- /token github <token>\n"
            "- /subscribe\n"
            "- /best coding agent\n"
            "- /scout wallets\n"
            "- /scout compute\n"
            "- /scout messaging for agent builder"
        )
        await self._reply(update, message, edit=True)

    async def unlock_compute(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        result = await self._run_unlock_with_chat_skips(update, "best")
        self._remember_result(update, result)
        await self._reply(update, self._format_result(result), edit=True)

    async def self_audit(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        result = await asyncio.to_thread(self.agent.run, "/self")
        self._remember_result(update, result)
        await self._reply(update, self._format_result(result), edit=True)

    async def self_cycle(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        result = await asyncio.to_thread(self.agent.run, "/cycle")
        self._remember_result(update, result)
        await self._reply(update, self._format_result(result), edit=True)

    async def status_info(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        result = await asyncio.to_thread(self.agent.run, "fund me")
        await self._reply(update, self._format_result(result), edit=True)

    async def handle_message(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        query = (update.message.text or "").strip()
        if not query:
            return
        if await self._handle_token_submission(update, query):
            return
        if self._is_skip_request(query):
            await self._skip_last_unlock(update)
            return
        if self._is_how_request(query):
            await self._reply_with_how(update)
            return
        await self._execute_query(update, query)

    async def _run_unlock_with_chat_skips(
        self,
        update: Update,
        category: str = "best",
    ) -> Dict[str, Any]:
        skipped_ids = self._skipped_unlock_ids(update)
        return await asyncio.to_thread(
            self.agent.infra.activation_request,
            category=category,
            profile_id="ai_first",
            excluded_ids=skipped_ids,
        )

    async def _skip_last_unlock(self, update: Update) -> None:
        chat_id = self._chat_id_from_update(update)
        if chat_id is None:
            await self._reply(update, "I could not identify this chat to skip the last unlock.")
            return

        payload = self._chat_memory.get(chat_id, {})
        request = payload.get("activation_request")
        if not isinstance(request, dict) or not request.get("candidate_id"):
            await self._reply(update, "No previous unlock task is stored for this chat. Send /unlock compute first.")
            return

        skipped = list(payload.get("skipped_unlock_ids") or [])
        candidate_id = request["candidate_id"]
        if candidate_id not in skipped:
            skipped.append(candidate_id)
        payload["skipped_unlock_ids"] = skipped
        payload["activation_request"] = None
        self._chat_memory[chat_id] = payload

        category = request.get("category", "compute")
        result = await self._run_unlock_with_chat_skips(update, category)
        self._remember_result(update, result)
        await self._reply(
            update,
            (
                f"Skipped unlock: {request.get('candidate_name', candidate_id)}\n\n"
                f"{self._format_result(result)}"
            ),
        )

    async def _execute_query(self, update: Update, query: str) -> None:
        await self._reply(update, f"Working on: {self._redact_sensitive_text(query)}")
        result = await asyncio.to_thread(self.agent.run, query)
        self._remember_result(update, result)
        await self._reply(update, self._format_result(result))

    async def _handle_token_submission(self, update: Update, text: str) -> bool:
        submissions = self._parse_token_submissions(text, update)
        if not submissions:
            return False

        await self._delete_sensitive_message(update)
        saved = await asyncio.to_thread(self._store_token_submissions, submissions)
        compute = await asyncio.to_thread(self.agent.run, "/compute")
        self._remember_result(update, compute)
        await self._reply(update, self._format_token_update(saved, compute))
        return True

    def _parse_token_submissions(
        self,
        text: str,
        update: Optional[Update] = None,
    ) -> list[tuple[str, str]]:
        stripped = (text or "").strip()
        if not stripped:
            return []

        command_match = re.match(
            r"^/token(?:@\w+)?\s+([A-Za-z0-9_-]+)\s+(.+)$",
            stripped,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if command_match:
            env_var = self._normalize_token_target(command_match.group(1))
            value = self._clean_token_value(command_match.group(2))
            return [(env_var, value)] if env_var and self._looks_like_secret(value) else []

        submissions: list[tuple[str, str]] = []
        for line in stripped.splitlines():
            match = re.match(r"^(?:export\s+)?([A-Z0-9_]+)\s*=\s*(.+)$", line.strip())
            if not match:
                continue
            env_var = self._normalize_token_target(match.group(1))
            value = self._clean_token_value(match.group(2))
            if env_var and self._looks_like_secret(value):
                submissions.append((env_var, value))
        if submissions:
            return submissions

        inferred_env_var = self._infer_token_env_var(stripped, update)
        cleaned = self._clean_token_value(stripped)
        if inferred_env_var and self._looks_like_secret(cleaned):
            return [(inferred_env_var, cleaned)]
        return []

    def _normalize_token_target(self, value: str) -> Optional[str]:
        key = (value or "").strip()
        upper_key = key.upper()
        if upper_key in TOKEN_ENV_VARS:
            return upper_key
        return TOKEN_TARGET_ALIASES.get(key.lower())

    def _infer_token_env_var(
        self,
        value: str,
        update: Optional[Update],
    ) -> Optional[str]:
        cleaned = self._clean_token_value(value)
        if cleaned.startswith("hf_"):
            return "HF_TOKEN"
        if cleaned.startswith(("github_pat_", "ghp_", "gho_", "ghu_", "ghs_", "ghr_")):
            return "GITHUB_TOKEN"

        chat_id = self._chat_id_from_update(update) if update else None
        if chat_id is None:
            return None
        request = (self._chat_memory.get(chat_id) or {}).get("activation_request") or {}
        env_vars = [
            env_var
            for env_var in request.get("env_vars", [])
            if env_var in TOKEN_ENV_VARS
        ]
        if len(env_vars) == 1:
            return env_vars[0]
        return None

    def _clean_token_value(self, value: str) -> str:
        cleaned = (value or "").strip()
        cleaned = cleaned.removeprefix("`").removesuffix("`").strip()
        cleaned = cleaned.strip("\"'")
        return cleaned

    def _looks_like_secret(self, value: str) -> bool:
        if len(value) < 8:
            return False
        return not bool(re.search(r"\s", value))

    def _store_token_submissions(self, submissions: list[tuple[str, str]]) -> list[str]:
        ENV_PATH.touch(exist_ok=True)
        saved: list[str] = []
        for env_var, value in submissions:
            set_key(str(ENV_PATH), env_var, value)
            os.environ[env_var] = value
            saved.append(env_var)
        load_dotenv(ENV_PATH, override=True)
        self.agent = ArbiterAgent()
        self.chain = get_chain_config()
        return saved

    async def _delete_sensitive_message(self, update: Update) -> None:
        if not self.delete_token_messages or not update.message:
            return
        try:
            await update.message.delete()
        except Exception:
            return

    def _format_token_update(self, saved: list[str], compute: Dict[str, Any]) -> str:
        hosted = ((compute.get("probe") or {}).get("hosted") or {})
        github = hosted.get("github_models") or {}
        hf = hosted.get("huggingface") or {}
        modal = hosted.get("modal") or {}
        lines = [
            f"Saved token setting(s): {', '.join(saved)}",
            "Token value was not echoed. Use scoped, revocable tokens only.",
        ]
        if any(item in saved for item in ("GITHUB_TOKEN", "GITHUB_PERSONAL_ACCESS_TOKEN")):
            lines.append(f"GitHub Models: {github.get('message', 'not checked yet')}")
        if any(item in saved for item in ("HF_TOKEN", "HUGGINGFACEHUB_API_TOKEN", "HUGGING_FACE_HUB_TOKEN")):
            lines.append(f"Hugging Face: {hf.get('message', 'not checked yet')}")
        if any(item in saved for item in ("MODAL_TOKEN_ID", "MODAL_TOKEN_SECRET")):
            lines.append(f"Modal: {modal.get('message', 'not checked yet')}")
        activation_request = compute.get("activation_request")
        if activation_request:
            lines.append("")
            lines.extend(self._format_activation_lines(activation_request))
        return "\n".join(lines)

    def _redact_sensitive_text(self, text: str) -> str:
        redacted = re.sub(
            r"(?i)\b(?:GITHUB_TOKEN|GITHUB_PERSONAL_ACCESS_TOKEN|HF_TOKEN|HUGGINGFACEHUB_API_TOKEN|HUGGING_FACE_HUB_TOKEN|MODAL_TOKEN_ID|MODAL_TOKEN_SECRET|TELEGRAM_BOT_TOKEN|ZEROX_API_KEY)\s*=\s*\S+",
            lambda match: match.group(0).split("=", 1)[0] + "=<redacted>",
            text,
        )
        redacted = re.sub(r"\b(hf_|github_pat_|ghp_|gho_|ghu_|ghs_|ghr_)[A-Za-z0-9_\-]+", r"\1<redacted>", redacted)
        return redacted

    def _format_result(self, result: Dict[str, Any]) -> str:
        mode = result.get("mode")
        if mode == "funding":
            return self._format_funding_result(result)
        if mode == "infra_stack":
            return self._format_infra_stack(result)
        if mode == "self_audit":
            return self._format_self_audit(result)
        if mode == "compute_audit":
            return self._format_compute_audit(result)
        if mode == "self_improvement_cycle":
            return self._format_self_improvement_cycle(result)
        if mode == "activation_request":
            return self._format_activation_request(result)
        if mode == "infra_scout":
            return self._format_infra_scout(result)
        if mode == "scouting" and result.get("deal_found"):
            return self._format_scouting_result(result)
        if result.get("deal_found"):
            return self._format_search_result(result)
        return result.get("message", "No result available.")

    def _format_infra_stack(self, result: Dict[str, Any]) -> str:
        profile = result["profile"]
        stack = result.get("stack") or []
        lines = [
            "Nomad best free stack",
            f"Profile: {profile['label']}",
            f"Stack score: {result.get('overall_score', 0.0):.2f}",
        ]
        for item in stack:
            lines.append(
                f"{item['category']}: {item['name']} "
                f"({item['agent_satisfaction_score']:.2f})"
            )
            lines.append(f"Why: {item['summary']}")
            lines.append(f"Tradeoff: {item['tradeoff']}")
        if result.get("analysis"):
            lines.append("")
            lines.append(result["analysis"])
        return "\n".join(lines)

    def _format_infra_scout(self, result: Dict[str, Any]) -> str:
        profile = result["profile"]
        category = result.get("category", "infra")
        items = result.get("results") or []
        lines = [
            f"Nomad infra scout: {category}",
            f"Profile: {profile['label']}",
        ]
        for index, item in enumerate(items[:4], start=1):
            lines.append(
                f"{index}. {item['name']} | satisfaction {item['agent_satisfaction_score']:.2f}"
            )
            lines.append(f"Why: {item['summary']}")
            lines.append(f"Best for: {item['best_for']}")
            lines.append(f"Tradeoff: {item['tradeoff']}")
        activation_request = result.get("activation_request")
        if activation_request:
            lines.append("")
            lines.extend(self._format_activation_lines(activation_request))
        if result.get("analysis"):
            lines.append("")
            lines.append(result["analysis"])
        return "\n".join(lines)

    def _format_self_audit(self, result: Dict[str, Any]) -> str:
        profile = result["profile"]
        rows = result.get("current_stack") or []
        lines = [
            "Nomad self audit",
            f"Profile: {profile['label']}",
        ]
        for row in rows:
            current = row.get("current")
            recommended = row.get("recommended")
            status = "aligned" if row.get("aligned") else "upgrade"
            lines.append(
                f"{row['category']}: {current['name'] if current else 'not set'} -> "
                f"{recommended['name']} [{status}]"
            )
        upgrades = result.get("upgrades") or []
        if upgrades:
            lines.append("")
            lines.append("Next improvements")
            for item in upgrades[:3]:
                lines.append(
                    f"- {item['category']}: switch to {item['recommended']}"
                )
        activation_request = result.get("activation_request")
        if activation_request:
            lines.append("")
            lines.extend(self._format_activation_lines(activation_request))
        if result.get("analysis"):
            lines.append("")
            lines.append(result["analysis"])
        return "\n".join(lines)

    def _format_compute_audit(self, result: Dict[str, Any]) -> str:
        profile = result["profile"]
        probe = result.get("probe") or {}
        brains = result.get("brains") or {}
        ollama = probe.get("ollama") or {}
        llama_cpp = probe.get("llama_cpp") or {}
        gpu = probe.get("gpu") or {}
        hosted = probe.get("hosted") or {}
        lines = [
            "Nomad compute audit",
            f"Profile: {profile['label']}",
            f"CPU cores: {probe.get('cpu_count', 0)}",
            f"RAM: {probe.get('memory_gb', 0.0):.2f} GB",
        ]
        if gpu.get("available") and gpu.get("gpus"):
            top_gpu = gpu["gpus"][0]
            lines.append(
                f"GPU: {top_gpu.get('name', 'GPU')} ({top_gpu.get('memory_gb', 0)} GB)"
            )
        else:
            lines.append("GPU: not detected")
        if ollama.get("api_reachable"):
            lines.append(
                f"Ollama: active with {ollama.get('count', 0)} model(s)"
            )
        elif ollama.get("available"):
            lines.append("Ollama: installed but API not reachable")
        else:
            lines.append("Ollama: not detected")
        if llama_cpp.get("available"):
            lines.append("llama.cpp: active")
            if llama_cpp.get("version"):
                lines.append(f"llama.cpp version: {llama_cpp['version']}")
        else:
            lines.append("llama.cpp: not detected")

        hosted_lines = []
        github_models = hosted.get("github_models") or {}
        huggingface = hosted.get("huggingface") or {}
        modal = hosted.get("modal") or {}
        if github_models.get("available"):
            hosted_lines.append(
                f"GitHub Models: ready ({github_models.get('model_count', 0)} models visible)"
            )
        elif github_models.get("configured"):
            hosted_lines.append("GitHub Models: configured but not usable yet")
        if huggingface.get("available"):
            hosted_lines.append("Hugging Face: token valid")
        elif huggingface.get("configured"):
            hosted_lines.append("Hugging Face: configured but not usable yet")
        if modal.get("configured"):
            hosted_lines.append("Modal: credentials present")
        if hosted_lines:
            lines.extend(hosted_lines)

        primary_brain = brains.get("primary")
        secondary_brains = brains.get("secondary") or []
        if primary_brain or secondary_brains:
            lines.append("")
            lines.append("Brains online")
            if primary_brain:
                lines.append(
                    f"Primary brain: {primary_brain['name']} with {primary_brain.get('model_count', 0)} local model(s)"
                )
            for item in secondary_brains[:3]:
                suffix = ""
                if item.get("model_count"):
                    suffix = f" ({item['model_count']} model(s) visible)"
                lines.append(
                    f"Fallback brain: {item['name']}{suffix}"
                )

        results = result.get("results") or []
        if results:
            lines.append("")
            lines.append("Best free compute lanes")
            for index, item in enumerate(results[:3], start=1):
                lines.append(
                    f"{index}. {item['name']} | satisfaction {item['agent_satisfaction_score']:.2f}"
                )
                lines.append(f"Why: {item['summary']}")
        activation_request = result.get("activation_request")
        if activation_request:
            lines.append("")
            lines.extend(self._format_activation_lines(activation_request))
        if result.get("analysis"):
            lines.append("")
            lines.append(result["analysis"])
        return "\n".join(lines)

    def _format_self_improvement_cycle(self, result: Dict[str, Any]) -> str:
        profile = result.get("profile") or {}
        resources = result.get("resources") or {}
        local_actions = result.get("local_actions") or []
        reviews = result.get("brain_reviews") or []
        lines = [
            "Nomad self-improvement cycle",
            f"Profile: {profile.get('label', profile.get('id', 'Nomad'))}",
            f"External reviews used: {result.get('external_review_count', 0)}",
        ]

        primary = resources.get("primary_brain")
        fallback_brains = resources.get("fallback_brains") or []
        if primary or fallback_brains:
            lines.append("")
            lines.append("Resources used")
            if primary:
                lines.append(f"Primary: {primary.get('name', 'local brain')}")
            for brain in fallback_brains[:3]:
                lines.append(f"Fallback: {brain.get('name', 'hosted brain')}")

        if local_actions:
            lines.append("")
            lines.append("Next cycle actions")
            for item in local_actions[:4]:
                marker = "human" if item.get("requires_human") else "agent"
                lines.append(f"- [{marker}] {item.get('title')}")

        ok_reviews = [item for item in reviews if item.get("ok")]
        failed_reviews = [item for item in reviews if item.get("configured") and not item.get("ok")]
        if ok_reviews:
            lines.append("")
            lines.append("External reviewer notes")
            for item in ok_reviews[:2]:
                content = (item.get("content") or "").strip()
                if len(content) > 900:
                    content = f"{content[:900]}..."
                lines.append(f"{item.get('name')} ({item.get('model')}):")
                lines.append(content)
        if failed_reviews:
            lines.append("")
            for item in failed_reviews[:2]:
                lines.append(f"{item.get('name')} issue: {item.get('message', 'not available')}")

        human_unlocks = result.get("human_unlocks") or []
        if human_unlocks:
            lines.append("")
            lines.extend(self._format_activation_lines(human_unlocks[0]))
        if result.get("analysis"):
            lines.append("")
            lines.append(result["analysis"])
        return "\n".join(lines)

    def _format_activation_request(self, result: Dict[str, Any]) -> str:
        request = result.get("request")
        category = result.get("category", "compute")
        lines = [f"Nomad unlock request: {category}"]
        if request:
            lines.extend(self._format_activation_lines(request))
        else:
            lines.append("No human activation request is pending right now.")
        if result.get("analysis"):
            lines.append("")
            lines.append(result["analysis"])
        return "\n".join(lines)

    def _format_activation_lines(self, request: Dict[str, Any]) -> list[str]:
        lines = [
            "Human in the loop requested",
            f"Unlock: {request['candidate_name']} as {request['role']}",
            f"Lane state: {request['lane_state']}",
            f"Nomad asks: {request['ask']}",
            f"Why now: {request['reason']}",
        ]
        if request.get("decision_score") is not None:
            lines.append(f"Decision score: {request['decision_score']}")
        if request.get("decision_reason"):
            lines.append(f"Nomad decision: {request['decision_reason']}")
        if request.get("env_vars"):
            lines.append(f"Needs: {', '.join(request['env_vars'])}")
            token_vars = [env_var for env_var in request["env_vars"] if env_var in TOKEN_ENV_VARS]
            if token_vars:
                provider_hint = self._provider_hint_for_env_var(token_vars[0])
                lines.append(
                    f"Telegram: send `/token {provider_hint} <token>` or `{token_vars[0]}=...`."
                )
        if request.get("account_provider"):
            lines.append(f"Account: {request['account_provider']}")
        if request.get("setup_url"):
            lines.append(f"Open: {request['setup_url']}")
        if request.get("docs_url"):
            lines.append(f"Docs: {request['docs_url']}")
        if request.get("security_url"):
            lines.append(f"Security: {request['security_url']}")
        steps = request.get("steps") or []
        if steps:
            lines.append("Steps")
            for step in steps[:6]:
                lines.append(f"- {step}")
        verification_steps = request.get("verification_steps") or []
        if verification_steps:
            lines.append("Verify")
            for step in verification_steps[:3]:
                lines.append(f"- {step}")
        lines.append("Tip: ask 'how?' any time and Nomad will repeat the current unlock steps.")
        lines.append("If this unlock is unclear or not useful, send /skip last.")
        return lines

    def _provider_hint_for_env_var(self, env_var: str) -> str:
        if env_var in {"GITHUB_TOKEN", "GITHUB_PERSONAL_ACCESS_TOKEN"}:
            return "github"
        if env_var in {"HF_TOKEN", "HUGGINGFACEHUB_API_TOKEN", "HUGGING_FACE_HUB_TOKEN"}:
            return "hf"
        if env_var == "MODAL_TOKEN_ID":
            return "modal_id"
        if env_var == "MODAL_TOKEN_SECRET":
            return "modal_secret"
        if env_var == "TELEGRAM_BOT_TOKEN":
            return "telegram"
        if env_var == "ZEROX_API_KEY":
            return "zerox"
        return env_var.lower()

    def _format_scouting_result(self, result: Dict[str, Any]) -> str:
        selected = result["selected_deal"]
        lines = [
            "Best arbitrage scout lead",
            f"Route lens: {selected['route']}",
            f"Candidate: {selected['candidate_name']}",
            f"Distance from target: {selected['distance_from_target_km']:.1f} km",
            f"Distance from origin: {selected['distance_from_origin_km']:.1f} km",
            (
                f"Selected by: {'LLM travel analyst' if selected.get('selection_source') == 'llm' else 'local heuristic'}"
            ),
            f"Arbitrage score: {selected['arbitrage_score']:.2f}%",
            f"Value score: {selected.get('value_score', 0.0):.2f}",
            (
                f"Stay supply: {selected['accommodation_count']} "
                f"(hostels: {selected['hostel_count']})"
            ),
            f"Budget food: {selected['budget_food_count']}",
            f"Transit nodes: {selected['transit_count']}",
            f"Attractions: {selected['attraction_count']}",
            f"Nearby airports: {selected['airport_count']}",
        ]

        top = result.get("opportunities") or []
        if len(top) > 1:
            lines.append("")
            lines.append("Next scout leads")
            for index, option in enumerate(top[1:3], start=2):
                lines.append(
                    f"{index}. {option['candidate_name']} | value {option['value_score']:.2f} | "
                    f"{option['distance_from_target_km']:.1f} km from {option['anchor_destination']}"
                )

        if result.get("analysis"):
            lines.append("")
            lines.append(result["analysis"])
        if result.get("tx_hash"):
            if self.chain.explorer_tx_base:
                lines.append(f"Tx: {self.chain.explorer_tx_base}{result['tx_hash']}")
            else:
                lines.append(f"Tx hash: {result['tx_hash']}")
        return "\n".join(lines)

    def _format_search_result(self, result: Dict[str, Any]) -> str:
        selected = result["selected_deal"]
        lines = [
            "Best live opportunity",
            f"Route: {selected['route']}",
            f"Total: {selected['total_price']:.2f} {selected['currency']}",
            f"Flight: {selected['flight_price']:.2f} {selected['currency']}",
        ]
        lines.append(
            f"Selected by: {'LLM travel analyst' if selected.get('selection_source') == 'llm' else 'local heuristic'}"
        )
        if selected.get("hotel_price") is not None:
            lines.append(
                f"Hotel: {selected['hotel_price']:.2f} {selected['currency']} at {selected['hotel_name']}"
            )
        lines.append(
            f"Score: {selected['arbitrage_score']:.2f}% below the median result set"
        )
        lines.append(f"Value score: {selected.get('value_score', 0.0):.2f}")
        if selected.get("carrier_codes"):
            lines.append(f"Carriers: {', '.join(selected['carrier_codes'])}")
        if selected.get("bookable_seats"):
            lines.append(f"Bookable seats: {selected['bookable_seats']}")

        top = result.get("opportunities") or []
        if len(top) > 1:
            lines.append("")
            lines.append("Next best options")
            for index, option in enumerate(top[1:3], start=2):
                hotel_suffix = ""
                if option.get("hotel_name"):
                    hotel_suffix = f" + {option['hotel_name']}"
                lines.append(
                    f"{index}. {option['total_price']:.2f} {option['currency']} | "
                    f"{option['route']}{hotel_suffix}"
                )

        if result.get("analysis"):
            lines.append("")
            lines.append(result["analysis"])
        if result.get("tx_hash"):
            if self.chain.explorer_tx_base:
                lines.append(f"Tx: {self.chain.explorer_tx_base}{result['tx_hash']}")
            else:
                lines.append(f"Tx hash: {result['tx_hash']}")
        return "\n".join(lines)

    def _format_funding_result(self, result: Dict[str, Any]) -> str:
        funding = result["funding"]
        wallet = funding["wallet"]
        lines = [
            "Treasury status",
            f"Network: {funding['network']} (chain {funding['chain_id']})",
            f"Agent wallet: {wallet.get('address') or 'not configured'}",
        ]
        native_symbol = funding.get("native_symbol", self.chain.native_symbol)
        if wallet.get("native_balance") is not None:
            lines.append(f"Wallet balance: {wallet['native_balance']:.6f} {native_symbol}")
        if wallet.get("project_token_balance") is not None:
            lines.append(
                f"{wallet.get('project_token_symbol', funding.get('project_token_symbol', 'Token'))} balance: "
                f"{wallet['project_token_balance']:.6f}"
            )
        if funding.get("project_token_address"):
            lines.append(f"Token: {funding['project_token_address']}")
        if funding.get("contract_address"):
            lines.append(f"Contract: {funding['contract_address']}")

        amount_native = funding.get("amount_native")
        if amount_native is not None:
            lines.extend(
                [
                    "",
                    f"Funding input: {amount_native} {native_symbol}",
                    (
                        f"Token bucket: {funding['token_allocation_native']:.6f} {native_symbol} "
                        f"({funding['token_split_pct']}%)"
                    ),
                    (
                        f"Reserve bucket: {funding['reserve_allocation_native']:.6f} {native_symbol} "
                        f"({funding['reserve_split_pct']}%)"
                    ),
                ]
            )
            quote = funding.get("quote")
            if quote:
                if quote.get("available"):
                    lines.append(
                        f"Indicative token quote: about {quote['estimated_buy_amount']} "
                        f"{quote['buy_symbol']}"
                    )
                    if quote.get("route_sources"):
                        lines.append(
                            f"Liquidity sources: {', '.join(quote['route_sources'])}"
                        )
                else:
                    lines.append(quote.get("message", "No live token quote available."))
            execution = result.get("execution")
            if execution:
                if execution.get("executed"):
                    lines.extend(
                        [
                            "",
                            "Local dev execution",
                            (
                                f"Minted: {execution['minted_amount']:.6f} "
                                f"{execution['token_symbol']} at {execution['mint_rate']:.2f} "
                                f"{execution['token_symbol']} per 1 {native_symbol}"
                            ),
                            (
                                f"Reserve kept liquid: {execution['reserve_stays_native']:.6f} "
                                f"{native_symbol}"
                            ),
                            f"New token balance: {execution['token_balance']:.6f} {execution['token_symbol']}",
                        ]
                    )
                    if self.chain.explorer_tx_base:
                        lines.append(f"Tx: {self.chain.explorer_tx_base}{execution['tx_hash']}")
                    else:
                        lines.append(f"Tx hash: {execution['tx_hash']}")
                elif execution.get("message"):
                    lines.append(execution["message"])
        else:
            lines.extend(
                [
                    "",
                    f"Send 'fund me 0.25 {native_symbol.lower()}' to calculate the treasury split.",
                    f"This path prepares the treasury logic on {funding['network']}, but does not auto-spend user funds.",
                ]
            )

        if result.get("analysis"):
            lines.append("")
            lines.append(result["analysis"])
        return "\n".join(lines)

    async def _reply(
        self,
        update: Update,
        message: str,
        reply_markup: Optional[InlineKeyboardMarkup] = None,
        edit: bool = False,
    ) -> None:
        self._auto_subscribe_chat(update)
        if update.callback_query:
            await update.callback_query.answer()
            if edit:
                await update.callback_query.edit_message_text(
                    message,
                    reply_markup=reply_markup,
                )
            else:
                await update.callback_query.message.reply_text(
                    message,
                    reply_markup=reply_markup,
                )
            return

        if update.message:
            await update.message.reply_text(message, reply_markup=reply_markup)

    def _chat_id_from_update(self, update: Update) -> Optional[int]:
        if update.effective_chat:
            return update.effective_chat.id
        return None

    def _auto_subscribe_chat(self, update: Update) -> None:
        if not self.auto_subscribe_on_interaction:
            return
        chat_id = self._chat_id_from_update(update)
        if chat_id is None:
            return
        self._add_subscriber(chat_id)

    def _remember_result(self, update: Update, result: Dict[str, Any]) -> None:
        chat_id = self._chat_id_from_update(update)
        if chat_id is None:
            return

        request = result.get("activation_request") or result.get("request")
        if not request and result.get("mode") == "self_improvement_cycle":
            unlocks = result.get("human_unlocks") or []
            request = unlocks[0] if unlocks else None
        payload = self._chat_memory.get(chat_id, {})
        payload["last_mode"] = result.get("mode")

        if isinstance(request, dict) and request.get("candidate_name"):
            payload["activation_request"] = request
        elif result.get("mode") == "activation_request":
            payload["activation_request"] = None

        self._chat_memory[chat_id] = payload

    def _skipped_unlock_ids(self, update: Update) -> list[str]:
        chat_id = self._chat_id_from_update(update)
        if chat_id is None:
            return []
        payload = self._chat_memory.get(chat_id, {})
        return [
            str(item)
            for item in (payload.get("skipped_unlock_ids") or [])
            if str(item).strip()
        ]

    def _is_skip_request(self, query: str) -> bool:
        lowered = query.strip().lower()
        return lowered in {
            "skip",
            "skip last",
            "/skip",
            "/skip last",
            "überspringen",
            "ueberspringen",
            "überspring letzte",
            "ueberspring letzte",
            "nächste unlock",
            "naechste unlock",
        }

    def _is_how_request(self, query: str) -> bool:
        lowered = query.strip().lower()
        return lowered in {
            "how",
            "how?",
            "wie",
            "wie?",
            "wie geht das",
            "wie geht das?",
            "show steps",
            "details",
            "help me unlock",
        } or lowered.startswith("how do i") or lowered.startswith("how to") or lowered.startswith("wie mache ich")

    async def _reply_with_how(self, update: Update) -> None:
        chat_id = self._chat_id_from_update(update)
        stored_request = None
        if chat_id is not None:
            stored_request = (self._chat_memory.get(chat_id) or {}).get("activation_request")

        if stored_request:
            message = self._format_activation_request(
                {
                    "mode": "activation_request",
                    "category": stored_request.get("category", "compute"),
                    "request": stored_request,
                    "analysis": "Nomad is repeating the currently active unlock steps for this chat.",
                }
            )
            await self._reply(update, message)
            return

        result = await asyncio.to_thread(self.agent.run, "/unlock")
        self._remember_result(update, result)
        await self._reply(update, self._format_result(result))

    def _load_static_status_chat_ids(self) -> set[int]:
        raw = (os.getenv("TELEGRAM_STATUS_CHAT_IDS") or "").strip()
        result: set[int] = set()
        for part in raw.split(","):
            value = part.strip()
            if not value:
                continue
            try:
                result.add(int(value))
            except ValueError:
                continue
        return result

    def _load_subscribers(self) -> set[int]:
        if not SUBSCRIBERS_PATH.exists():
            return set()
        try:
            payload = json.loads(SUBSCRIBERS_PATH.read_text(encoding="utf-8"))
            return {
                int(item)
                for item in payload
                if isinstance(item, (int, str)) and str(item).strip()
            }
        except Exception:
            return set()

    def _save_subscribers(self, chat_ids: set[int]) -> None:
        SUBSCRIBERS_PATH.write_text(
            json.dumps(sorted(chat_ids), ensure_ascii=True, indent=2),
            encoding="utf-8",
        )

    def _add_subscriber(self, chat_id: int) -> None:
        subscribers = self._load_subscribers()
        subscribers.add(chat_id)
        self._save_subscribers(subscribers)

    def _remove_subscriber(self, chat_id: int) -> None:
        subscribers = self._load_subscribers()
        subscribers.discard(chat_id)
        self._save_subscribers(subscribers)

    def _broadcast_targets(self) -> set[int]:
        return self._load_subscribers() | self.status_chat_ids

    def _build_periodic_update(self) -> str:
        self_audit = self.agent.run("/self")
        compute = self.agent.run("/compute")
        best = self.agent.run("/best")

        top_upgrade = (self_audit.get("upgrades") or [{}])[0]
        top_stack = (best.get("stack") or [{}])[0]
        compute_top = (compute.get("results") or [{}])[0]
        activation_request = compute.get("activation_request") or {}
        brains = compute.get("brains") or {}
        ollama = (compute.get("probe") or {}).get("ollama") or {}

        lines = [
            f"Nomad update {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}",
            "AI-first infrastructure scout is active.",
        ]
        if top_stack.get("name"):
            lines.append(f"Best current stack lead: {top_stack['name']}")
        if compute_top.get("name"):
            lines.append(f"Best free compute lane: {compute_top['name']}")
        if ollama.get("api_reachable"):
            lines.append(
                f"Local compute: Ollama active with {ollama.get('count', 0)} model(s)"
            )
        elif compute.get("probe"):
            lines.append(
                f"Local compute: {compute['probe'].get('cpu_count', 0)} CPU cores, "
                f"{compute['probe'].get('memory_gb', 0.0):.2f} GB RAM"
            )
        secondary_brains = brains.get("secondary") or []
        if secondary_brains:
            top_secondary = secondary_brains[0]
            lines.append(f"Second brain online: {top_secondary['name']}")
        if top_upgrade.get("recommended"):
            lines.append(
                f"Next self-improvement: {top_upgrade['category']} -> {top_upgrade['recommended']}"
            )
        if activation_request.get("candidate_name"):
            lines.append(
                f"Human help requested: unlock {activation_request['candidate_name']}"
            )
            if activation_request.get("short_ask"):
                lines.append(activation_request["short_ask"])
        lines.append(f"API: {self.public_api_url}")
        if self.auto_cycle_enabled:
            lines.append(
                f"Auto-cycle: enabled every {self.auto_cycle_interval_minutes} minutes"
            )
        else:
            lines.append("Auto-cycle: disabled; set NOMAD_AUTO_CYCLE=true to enable.")
        lines.append("Use: /best /self /compute /cycle /unlock /scout compute")
        return "\n".join(lines)

    def _send_status_message(self, chat_id: int, text: str) -> None:
        if not self.token:
            return
        try:
            requests.post(
                f"https://api.telegram.org/bot{self.token}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": text,
                },
                timeout=20,
            )
        except Exception:
            return

    def _status_broadcast_loop(self) -> None:
        if not self.status_updates_enabled:
            return
        interval_seconds = max(60, self.status_interval_minutes * 60)
        while True:
            time.sleep(interval_seconds)
            targets = self._broadcast_targets()
            if not targets:
                continue
            message = self._build_periodic_update()
            for chat_id in targets:
                self._send_status_message(chat_id, message)

    def _start_status_broadcast_loop(self) -> None:
        if self._broadcast_thread is not None or not self.status_updates_enabled:
            return
        self._broadcast_thread = threading.Thread(
            target=self._status_broadcast_loop,
            name="nomad-telegram-status",
            daemon=True,
        )
        self._broadcast_thread.start()

    def _auto_cycle_loop(self) -> None:
        if not self.auto_cycle_enabled:
            return
        interval_seconds = max(300, self.auto_cycle_interval_minutes * 60)
        while True:
            time.sleep(interval_seconds)
            targets = self._broadcast_targets()
            if not targets:
                continue
            try:
                result = self.agent.run("/cycle autonomous background self-improvement")
                message = self._format_result(result)
            except Exception as exc:
                message = f"Nomad auto-cycle failed: {exc}"
            for chat_id in targets:
                self._send_status_message(chat_id, message)

    def _start_auto_cycle_loop(self) -> None:
        if self._auto_cycle_thread is not None or not self.auto_cycle_enabled:
            return
        self._auto_cycle_thread = threading.Thread(
            target=self._auto_cycle_loop,
            name="nomad-auto-cycle",
            daemon=True,
        )
        self._auto_cycle_thread.start()

    def run(self) -> None:
        if not self.token:
            print("Error: TELEGRAM_BOT_TOKEN not found in .env")
            return

        app = ApplicationBuilder().token(self.token).build()
        app.add_handler(CommandHandler("start", self.start))
        app.add_handler(CommandHandler("help", self.help_command))
        app.add_handler(CommandHandler("best", self.best_command))
        app.add_handler(CommandHandler("self", self.self_command))
        app.add_handler(CommandHandler("compute", self.compute_command))
        app.add_handler(CommandHandler("cycle", self.cycle_command))
        app.add_handler(CommandHandler("unlock", self.unlock_command))
        app.add_handler(CommandHandler("skip", self.skip_command))
        app.add_handler(CommandHandler("scout", self.scout_command))
        app.add_handler(CommandHandler("subscribe", self.subscribe_command))
        app.add_handler(CommandHandler("unsubscribe", self.unsubscribe_command))
        app.add_handler(CommandHandler("fund", self.fund_command))
        app.add_handler(CommandHandler("token", self.token_command))
        app.add_handler(CommandHandler("search", self.search_command))
        app.add_handler(CommandHandler("status", self.status_command))
        app.add_handler(CallbackQueryHandler(self.best_stack, pattern="^best_stack$"))
        app.add_handler(CallbackQueryHandler(self.self_audit, pattern="^self_audit$"))
        app.add_handler(CallbackQueryHandler(self.infra_prompt, pattern="^infra_prompt$"))
        app.add_handler(CallbackQueryHandler(self.unlock_compute, pattern="^unlock_compute$"))
        app.add_handler(CallbackQueryHandler(self.self_cycle, pattern="^self_cycle$"))
        app.add_handler(CallbackQueryHandler(self.fund_info, pattern="^fund_info$"))
        app.add_handler(CallbackQueryHandler(self.search_prompt, pattern="^search_prompt$"))
        app.add_handler(CallbackQueryHandler(self.status_info, pattern="^status_info$"))
        app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), self.handle_message))

        print("--- Nomad Telegram Bot Live ---")
        self._start_status_broadcast_loop()
        self._start_auto_cycle_loop()
        app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    ArbiterBot().run()


NomadBot = ArbiterBot
