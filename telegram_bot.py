import asyncio
import hashlib
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
from self_development import SelfDevelopmentJournal
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
TELEGRAM_BROADCAST_STATE_PATH = ROOT / "telegram_broadcast_state.json"
SELF_STATE_PATH = ROOT / "nomad_self_state.json"
TOKEN_ENV_VARS = {
    "GITHUB_TOKEN",
    "GITHUB_PERSONAL_ACCESS_TOKEN",
    "HF_TOKEN",
    "HUGGINGFACEHUB_API_TOKEN",
    "HUGGING_FACE_HUB_TOKEN",
    "MODAL_TOKEN_ID",
    "MODAL_TOKEN_SECRET",
    "TELEGRAM_BOT_TOKEN",
    "XAI_API_KEY",
    "CODEBUDDY_API_KEY",
    "IBM_QUANTUM_TOKEN",
    "QUANTUM_INSPIRE_TOKEN",
    "QI_API_TOKEN",
    "AZURE_QUANTUM_TOKEN",
    "GOOGLE_QUANTUM_TOKEN",
    "ZEROX_API_KEY",
    "RENDER_API_KEY",
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
    "xai": "XAI_API_KEY",
    "grok": "XAI_API_KEY",
    "codebuddy": "CODEBUDDY_API_KEY",
    "code-buddy": "CODEBUDDY_API_KEY",
    "tencent_codebuddy": "CODEBUDDY_API_KEY",
    "tencent-codebuddy": "CODEBUDDY_API_KEY",
    "ibm_quantum": "IBM_QUANTUM_TOKEN",
    "ibm-quantum": "IBM_QUANTUM_TOKEN",
    "ibm_quatum": "IBM_QUANTUM_TOKEN",
    "ibm-quatum": "IBM_QUANTUM_TOKEN",
    "quantum_ibm": "IBM_QUANTUM_TOKEN",
    "quantum-ibm": "IBM_QUANTUM_TOKEN",
    "quatum_ibm": "IBM_QUANTUM_TOKEN",
    "quatum-ibm": "IBM_QUANTUM_TOKEN",
    "quantum_inspire": "QUANTUM_INSPIRE_TOKEN",
    "quantum-inspire": "QUANTUM_INSPIRE_TOKEN",
    "inspire_quantum": "QUANTUM_INSPIRE_TOKEN",
    "inspire-quantum": "QUANTUM_INSPIRE_TOKEN",
    "qi": "QI_API_TOKEN",
    "qi_api": "QI_API_TOKEN",
    "qi-api": "QI_API_TOKEN",
    "azure_quantum": "AZURE_QUANTUM_TOKEN",
    "azure-quantum": "AZURE_QUANTUM_TOKEN",
    "quantum_azure": "AZURE_QUANTUM_TOKEN",
    "quantum-azure": "AZURE_QUANTUM_TOKEN",
    "google_quantum": "GOOGLE_QUANTUM_TOKEN",
    "google-quantum": "GOOGLE_QUANTUM_TOKEN",
    "quantum_google": "GOOGLE_QUANTUM_TOKEN",
    "quantum-google": "GOOGLE_QUANTUM_TOKEN",
    "0x": "ZEROX_API_KEY",
    "zerox": "ZEROX_API_KEY",
    "render": "RENDER_API_KEY",
    "render_api": "RENDER_API_KEY",
    "render-api": "RENDER_API_KEY",
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
            os.getenv("TELEGRAM_AUTO_SUBSCRIBE_ON_INTERACTION", "false").strip().lower() == "true"
        )
        self.status_updates_enabled = (
            os.getenv("TELEGRAM_STATUS_UPDATES", "true").strip().lower() == "true"
        )
        self.status_change_only = (
            os.getenv("TELEGRAM_STATUS_CHANGE_ONLY", "true").strip().lower() == "true"
        )
        self.auto_cycle_change_only = (
            os.getenv("TELEGRAM_AUTO_CYCLE_CHANGE_ONLY", "true").strip().lower() == "true"
        )
        self.status_repeat_digest_every = int(
            os.getenv("TELEGRAM_STATUS_REPEAT_DIGEST_EVERY", "0")
        )
        self.auto_cycle_repeat_digest_every = int(
            os.getenv("TELEGRAM_AUTO_CYCLE_REPEAT_DIGEST_EVERY", "0")
        )
        self.status_interval_minutes = int(
            os.getenv("TELEGRAM_STATUS_INTERVAL_MINUTES", "25")
        )
        self.status_chat_ids = self._load_static_status_chat_ids()
        self.self_journal = SelfDevelopmentJournal(SELF_STATE_PATH)
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
            "- /leads\n"
            "- /productize\n"
            "- /products\n"
            "- /addons\n"
            "- /quantum\n"
            "- /service\n"
            "- /unlock\n"
            "- /skip last\n"
            "- /token github <token>\n"
            "- /token grok <token>\n"
            "- /token render <token>\n"
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
                "/leads [query]\n"
                "/productize [lead or query]\n"
                "/products\n"
                "/addons\n"
                "/codebuddy\n"
                "/quantum [objective]\n"
                "/service [request|verify|work]\n"
                "/unlock [category]\n"
                "/skip last\n"
                "/token <github|hf|grok|codebuddy|render|ibm_quantum|quantum_inspire|modal_id|modal_secret> <token>\n"
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
                "`/token grok <token>`, `/token codebuddy <token>`, `/token render <token>`, `/token ibm_quantum <token>`, `/token quantum_inspire <token>`, "
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

    async def leads_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        query = "/leads"
        if context.args:
            query = f"/leads {' '.join(context.args)}"
        result = await asyncio.to_thread(self.agent.run, query)
        self._remember_result(update, result)
        await self._reply(update, self._format_result(result))

    async def productize_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        query = "/productize"
        if context.args:
            query = f"/productize {' '.join(context.args)}"
        result = await asyncio.to_thread(self.agent.run, query)
        self._remember_result(update, result)
        await self._reply(update, self._format_result(result))

    async def products_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        query = "/products"
        if context.args:
            query = f"/products {' '.join(context.args)}"
        result = await asyncio.to_thread(self.agent.run, query)
        self._remember_result(update, result)
        await self._reply(update, self._format_result(result))

    async def addons_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        result = await asyncio.to_thread(self.agent.run, "/addons")
        self._remember_result(update, result)
        await self._reply(update, self._format_result(result))

    async def codebuddy_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Show CodeBuddy brain status and configuration."""
        result = await asyncio.to_thread(self.agent.run, "/codebuddy")
        self._remember_result(update, result)
        await self._reply(update, self._format_result(result))

    async def quantum_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        query = "/quantum"
        if context.args:
            query = f"/quantum {' '.join(context.args)}"
        result = await asyncio.to_thread(self.agent.run, query)
        self._remember_result(update, result)
        await self._reply(update, self._format_result(result))

    async def service_command(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        query = "/service"
        if context.args:
            query = f"/service {' '.join(context.args)}"
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
        result = await asyncio.to_thread(self._status_snapshot)
        await self._reply(update, self._format_status_snapshot(result))

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
            "- /leads\n"
            "- /productize\n"
            "- /products\n"
            "- /addons\n"
            "- /quantum\n"
            "- /service\n"
            "- /unlock\n"
            "- /skip last\n"
            "- /token github <token>\n"
            "- /token grok <token>\n"
            "- /token render <token>\n"
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
        result = await asyncio.to_thread(self._status_snapshot)
        await self._reply(update, self._format_status_snapshot(result), edit=True)

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
        if cleaned.startswith("xai-"):
            return "XAI_API_KEY"

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
        load_dotenv(ENV_PATH)
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
        xai = hosted.get("xai_grok") or {}
        modal = hosted.get("modal") or {}
        lines = [
            f"Saved token setting(s): {', '.join(saved)}",
            "Token value was not echoed. Use scoped, revocable tokens only.",
        ]
        if any(item in saved for item in ("GITHUB_TOKEN", "GITHUB_PERSONAL_ACCESS_TOKEN")):
            lines.append(f"GitHub Models: {github.get('message', 'not checked yet')}")
        if any(item in saved for item in ("HF_TOKEN", "HUGGINGFACEHUB_API_TOKEN", "HUGGING_FACE_HUB_TOKEN")):
            lines.append(f"Hugging Face: {hf.get('message', 'not checked yet')}")
        if "XAI_API_KEY" in saved:
            lines.append(f"xAI Grok: {xai.get('message', 'not checked yet')}")
        if "CODEBUDDY_API_KEY" in saved:
            codebuddy = (((compute.get("probe") or {}).get("developer_assistants") or {}).get("codebuddy") or {})
            lines.append(
                f"CodeBuddy: {codebuddy.get('message', 'key saved; enable reviewer lane explicitly')}"
            )
        if "RENDER_API_KEY" in saved:
            lines.append("Render: key saved for public Nomad API hosting. Use /scout render to verify access.")
        if any(
            item in saved
            for item in (
                "IBM_QUANTUM_TOKEN",
                "QUANTUM_INSPIRE_TOKEN",
                "QI_API_TOKEN",
                "AZURE_QUANTUM_TOKEN",
                "GOOGLE_QUANTUM_TOKEN",
            )
        ):
            lines.append("Quantum token saved. Use /quantum to see the next qtoken and real-provider gate.")
        if any(item in saved for item in ("MODAL_TOKEN_ID", "MODAL_TOKEN_SECRET")):
            lines.append(f"Modal: {modal.get('message', 'not checked yet')}")
        activation_request = compute.get("activation_request")
        if activation_request:
            lines.append("")
            lines.extend(self._format_activation_lines(activation_request))
        return "\n".join(lines)

    def _redact_sensitive_text(self, text: str) -> str:
        redacted = re.sub(
            r"(?i)\b(?:GITHUB_TOKEN|GITHUB_PERSONAL_ACCESS_TOKEN|HF_TOKEN|HUGGINGFACEHUB_API_TOKEN|HUGGING_FACE_HUB_TOKEN|MODAL_TOKEN_ID|MODAL_TOKEN_SECRET|TELEGRAM_BOT_TOKEN|XAI_API_KEY|CODEBUDDY_API_KEY|IBM_QUANTUM_TOKEN|QUANTUM_INSPIRE_TOKEN|QI_API_TOKEN|AZURE_QUANTUM_TOKEN|GOOGLE_QUANTUM_TOKEN|ZEROX_API_KEY|RENDER_API_KEY)\s*=\s*\S+",
            lambda match: match.group(0).split("=", 1)[0] + "=<redacted>",
            text,
        )
        redacted = re.sub(r"\b(hf_|github_pat_|ghp_|gho_|ghu_|ghs_|ghr_|xai-|rnd_)[A-Za-z0-9_\-]+", r"\1<redacted>", redacted)
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
        if mode == "lead_discovery":
            return self._format_lead_discovery(result)
        if mode in {"lead_conversion_pipeline", "lead_conversion_list"}:
            return self._format_lead_conversion(result)
        if mode in {"nomad_product_factory", "nomad_product_list"}:
            return self._format_products(result)
        if mode == "nomad_addon_scan":
            return self._format_addons(result)
        if mode == "nomad_quantum_tokens":
            return self._format_quantum_tokens(result)
        if mode == "codebuddy_scout":
            return self._format_codebuddy_scout(result)
        if mode == "codebuddy_review":
            return self._format_codebuddy_review(result)
        if mode == "render_scout":
            return self._format_render_scout(result)
        if mode == "agent_collaboration":
            return self._format_agent_collaboration(result)
        if mode == "nomad_guardrails":
            return self._format_guardrails(result)
        if mode == "agent_pain_solution":
            return self._format_agent_pain_solution(result)
        if mode == "agent_reliability_doctor":
            return self._format_reliability_doctor(result)
        if mode == "agent_service_catalog":
            return self._format_service_catalog(result)
        if mode == "agent_service_request":
            return self._format_service_request(result)
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

    def _format_codebuddy_scout(self, result: Dict[str, Any]) -> str:
        status = result.get("status") or {}
        lines = [
            "Nomad CodeBuddy scout",
            f"Role: {result.get('recommended_role', 'self_development_reviewer')}",
            f"Enabled: {status.get('enabled', False)}",
            f"Automation ready: {status.get('automation_ready', False)}",
            f"CLI available: {status.get('cli_available', False)}",
            f"Route: {status.get('route', 'unknown')}",
        ]
        if status.get("next_action"):
            lines.append(f"Next: {status['next_action']}")
        activation_request = result.get("activation_request")
        if activation_request:
            lines.append("")
            lines.extend(self._format_activation_lines(activation_request))
        if result.get("analysis"):
            lines.append("")
            lines.append(result["analysis"])
        return "\n".join(line for line in lines if line)

    def _format_codebuddy_review(self, result: Dict[str, Any]) -> str:
        data_release = result.get("data_release") or {}
        lines = [
            "Nomad CodeBuddy review",
            f"OK: {result.get('ok', False)}",
            f"Issue: {result.get('issue') or 'none'}",
            f"Data release approved: {data_release.get('approved', False)}",
            f"Diff chars: {data_release.get('diff_char_count', 0)}",
            result.get("message", ""),
        ]
        if result.get("review"):
            lines.append("")
            lines.append(result["review"][:2500])
        elif data_release.get("files"):
            lines.append(f"Files: {', '.join(data_release['files'][:8])}")
        return "\n".join(line for line in lines if line)

    def _format_render_scout(self, result: Dict[str, Any]) -> str:
        status = result.get("status") or {}
        verification = status.get("verification") or {}
        selected = result.get("selected_service") or {}
        lines = [
            "Nomad Render scout",
            f"API key configured: {status.get('api_key_configured', False)}",
            f"Verification OK: {verification.get('ok', False)}",
            f"Service count: {verification.get('service_count', 0)}",
            f"Desired domain: {status.get('desired_domain', '')}",
            f"Selected service: {selected.get('name') or selected.get('id') or 'none'}",
        ]
        if status.get("next_action"):
            lines.append(f"Next: {status['next_action']}")
        activation_request = result.get("activation_request")
        if activation_request:
            lines.append("")
            lines.extend(self._format_activation_lines(activation_request))
        if result.get("analysis"):
            lines.append("")
            lines.append(result["analysis"])
        return "\n".join(line for line in lines if line)

    def _format_agent_collaboration(self, result: Dict[str, Any]) -> str:
        charter = result.get("charter") or {}
        permission = charter.get("permission") or {}
        lines = [
            "Nomad agent collaboration",
            f"Enabled: {charter.get('enabled', False)}",
            f"Public home: {charter.get('public_home', '')}",
            f"Ask help: {permission.get('ask_other_agents_for_help', False)}",
            f"Accept help: {permission.get('accept_help_from_other_agents', False)}",
            f"Learn from replies: {permission.get('learn_from_public_agent_replies', False)}",
        ]
        if result.get("analysis"):
            lines.append("")
            lines.append(result["analysis"])
        return "\n".join(line for line in lines if line)

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
        cloudflare = hosted.get("cloudflare_workers_ai") or {}
        xai_grok = hosted.get("xai_grok") or {}
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
        if cloudflare.get("available"):
            hosted_lines.append(f"Cloudflare Workers AI: ready ({cloudflare.get('inference_model', 'model')})")
        elif cloudflare.get("configured"):
            hosted_lines.append("Cloudflare Workers AI: configured but not usable yet")
        if xai_grok.get("available"):
            hosted_lines.append(f"xAI Grok: ready ({xai_grok.get('working_model') or xai_grok.get('model', 'model')})")
        elif xai_grok.get("configured"):
            hosted_lines.append("xAI Grok: configured but not usable yet")
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
        lead_scout = result.get("lead_scout") or {}
        lines = [
            "Nomad self-improvement cycle",
            f"Profile: {profile.get('label', profile.get('id', 'Nomad'))}",
            f"External reviews used: {result.get('external_review_count', 0)}",
        ]
        self_development = result.get("self_development") or {}
        if self_development:
            lines.append(f"Self-development cycle count: {self_development.get('cycle_count', 0)}")
            if self_development.get("next_objective"):
                lines.append(f"Next autonomous objective: {self_development['next_objective']}")
            dev_unlocks = self_development.get("human_unlocks") or []
            if dev_unlocks:
                first_unlock = dev_unlocks[0]
                lines.append("")
                lines.append("Human unlock for self-development")
                lines.extend(self._format_activation_lines(first_unlock))

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

        autonomous = result.get("autonomous_development") or {}
        if autonomous:
            lines.append("")
            lines.append("Autonomous development")
            if autonomous.get("skipped"):
                lines.append(f"- skipped: {autonomous.get('reason', 'unchanged')}")
            else:
                action = autonomous.get("action") or {}
                lines.append(f"- {action.get('title', 'development receipt')}")
                files = action.get("files") or []
                if files:
                    lines.append(f"- artifact: {files[0]}")
                if action.get("next_verification"):
                    lines.append(f"- verify: {action['next_verification']}")

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

        if lead_scout:
            lines.append("")
            lines.append("Lead scout")
            lines.append(lead_scout.get("objective", "Nomad scouts leads autonomously."))
            next_action = lead_scout.get("next_agent_action")
            if next_action:
                lines.append(f"Nomad next action: {next_action}")
            queries = lead_scout.get("search_queries") or []
            if queries:
                lines.append("Starting searches")
                for query in queries[:3]:
                    lines.append(f"- {query}")
            human_help = lead_scout.get("human_help_only_for") or []
            if human_help:
                lines.append("Human help only if blocked by")
                for item in human_help[:4]:
                    lines.append(f"- {item}")

        human_unlocks = result.get("human_unlocks") or []
        if human_unlocks:
            lines.append("")
            lines.extend(self._format_activation_lines(human_unlocks[0]))
        if result.get("analysis"):
            lines.append("")
            lines.append(result["analysis"])
        return "\n".join(lines)

    def _format_lead_discovery(self, result: Dict[str, Any]) -> str:
        leads = result.get("leads") or []
        lines = [
            "Nomad public lead discovery",
            f"Leads found: {len(leads)}",
        ]
        if result.get("query"):
            lines.append(f"Query: {result['query']}")
        for index, lead in enumerate(leads[:5], start=1):
            lines.append("")
            lines.append(f"{index}. {lead.get('title', 'Untitled lead')}")
            if lead.get("url"):
                lines.append(f"URL: {lead['url']}")
            lines.append(f"Pain: {lead.get('pain', 'unknown')}")
            lines.append(f"First help: {lead.get('first_help_action', 'draft a first response')}")
            lines.append("Policy: draft only until approved")
        unlocks = result.get("human_unlocks") or []
        if unlocks:
            lines.append("")
            lines.extend(self._format_activation_lines(unlocks[0]))
        if result.get("analysis"):
            lines.append("")
            lines.append(result["analysis"])
        return "\n".join(lines)

    def _format_lead_conversion(self, result: Dict[str, Any]) -> str:
        conversions = result.get("conversions") or []
        stats = result.get("stats") or {}
        lines = [
            "Nomad lead conversion",
            f"Conversions: {len(conversions)}",
        ]
        if stats:
            lines.append(
                "Status: "
                + ", ".join(f"{key}={value}" for key, value in sorted(stats.items()))
            )
        for conversion in conversions[:3]:
            lead = conversion.get("lead") or {}
            route = conversion.get("route") or {}
            value_pack = ((conversion.get("free_value") or {}).get("value_pack") or {})
            lines.append("")
            lines.append(lead.get("title") or "Untitled lead")
            if lead.get("url"):
                lines.append(f"URL: {lead['url']}")
            lines.append(f"Type: {lead.get('service_type', 'unknown')}")
            lines.append(f"Route: {conversion.get('status', 'unknown')}")
            if value_pack.get("pack_id"):
                lines.append(f"Value pack: {value_pack['pack_id']}")
            if route.get("approval_gate"):
                lines.append(f"Approval gate: {route['approval_gate']}")
        if result.get("analysis"):
            lines.append("")
            lines.append(result["analysis"])
        return "\n".join(lines)

    def _format_products(self, result: Dict[str, Any]) -> str:
        products = result.get("products") or []
        stats = result.get("stats") or {}
        title = (
            "Nomad product factory"
            if result.get("mode") == "nomad_product_factory"
            else "Nomad products"
        )
        lines = [
            title,
            f"Products: {len(products)}",
        ]
        if stats:
            lines.append(
                "Status: "
                + ", ".join(f"{key}={value}" for key, value in sorted(stats.items()))
            )
        for product in products[:3]:
            source = product.get("source_lead") or {}
            paid = product.get("paid_offer") or {}
            boundary = product.get("approval_boundary") or {}
            lines.append("")
            lines.append(f"{product.get('name', 'Nomad product')} ({product.get('sku', '')})")
            lines.append(f"Product: {product.get('product_id', '')}")
            lines.append(f"Status: {product.get('status', 'unknown')}")
            if source.get("title"):
                lines.append(f"Lead: {source['title']}")
            if paid.get("price_native") is not None:
                lines.append(f"Offer: {paid.get('price_native')} native for {paid.get('delivery', 'bounded delivery')}")
            if boundary.get("approval_required"):
                lines.append(
                    "Open gate: public/human-facing action still needs explicit approval."
                )
                if boundary.get("approval_gate"):
                    lines.append(f"Reply option: {boundary['approval_gate']}")
            else:
                lines.append("Open gate: none for machine-readable agent contact.")
        if result.get("analysis"):
            lines.append("")
            lines.append(result["analysis"])
        return "\n".join(lines)

    def _format_addons(self, result: Dict[str, Any]) -> str:
        stats = result.get("stats") or {}
        lines = [
            "Nomad addons",
            f"Source: {result.get('source_dir', '')}",
            f"Discovered: {stats.get('discovered', 0)}",
            f"Safe active adapters: {stats.get('active_safe_adapter', 0)}",
            f"Needs review: {stats.get('needs_human_review', 0)}",
        ]
        quantum = result.get("quantum_tokens") or {}
        if quantum:
            lines.append(f"Quantum tokens: {'enabled' if quantum.get('enabled') else 'disabled'}")
            lines.append(quantum.get("claim_boundary", ""))
            selected_backend = quantum.get("selected_backend") or {}
            if selected_backend:
                lines.append(
                    f"Backend: {selected_backend.get('provider', selected_backend.get('backend_id', ''))} "
                    f"[{selected_backend.get('status', '')}]"
                )
            best_unlock = quantum.get("best_next_quantum_unlock") or {}
            if self._is_actionable_quantum_unlock(best_unlock):
                lines.append(
                    f"Best quantum unlock: {best_unlock.get('provider')} via {best_unlock.get('telegram_command')}"
                )
            elif quantum.get("enabled"):
                lines.append("Quantum provider unlock: none required now; local qtokens already run without a token.")
        for addon in (result.get("addons") or [])[:5]:
            lines.append("")
            lines.append(f"{addon.get('name', 'Addon')} [{addon.get('status', 'unknown')}]")
            lines.append(f"Manifest: {addon.get('manifest_path', '')}")
            if addon.get("next_action"):
                lines.append(f"Next: {addon['next_action']}")
        if result.get("secret_warnings"):
            lines.append("")
            lines.append("Secret warning: token-like plaintext found in Nomadds. Rotate/remove it.")
        if result.get("analysis"):
            lines.append("")
            lines.append(result["analysis"])
        return "\n".join(line for line in lines if line is not None)

    def _format_quantum_tokens(self, result: Dict[str, Any]) -> str:
        selected = result.get("selected_strategy") or {}
        lines = [
            "Nomad quantum tokens",
            f"Objective: {result.get('objective', '')}",
            f"Selected: {selected.get('title', selected.get('strategy_id', 'none'))}",
            f"Tokens: {len(result.get('tokens') or [])}",
            result.get("claim_boundary", ""),
        ]
        selected_backend = result.get("selected_backend") or {}
        if selected_backend:
            lines.append(
                f"Backend: {selected_backend.get('provider', selected_backend.get('backend_id', ''))} "
                f"[{selected_backend.get('status', '')}]"
            )
        local_simulation = result.get("local_quantum_simulation") or {}
        if local_simulation.get("counts"):
            lines.append(f"Local simulation counts: {local_simulation['counts']}")
        for token in (result.get("tokens") or [])[:3]:
            lines.append(f"- local qtoken {token.get('qtoken_id')}: {token.get('title')} score={token.get('score')}")
        best_unlock = result.get("best_next_quantum_unlock") or {}
        if self._is_actionable_quantum_unlock(best_unlock):
            lines.append("")
            lines.append("Optional provider unlock")
            lines.append(f"{best_unlock.get('provider')}: {best_unlock.get('why', '')}")
            if best_unlock.get("telegram_command"):
                lines.append(f"Send: {best_unlock['telegram_command']}")
        elif result.get("tokens"):
            lines.append("")
            lines.append("No quantum provider token is needed for these local qtokens.")
        unlocks = result.get("human_unlocks") or []
        actionable_unlocks = self._filter_actionable_unlocks(unlocks)
        if actionable_unlocks:
            lines.append("")
            lines.append("Optional human unlock")
            lines.extend(self._format_activation_lines(actionable_unlocks[0]))
        if result.get("analysis"):
            lines.append("")
            lines.append(result["analysis"])
        return "\n".join(line for line in lines if line)

    def _format_guardrails(self, result: Dict[str, Any]) -> str:
        evaluation = result.get("evaluation") or {}
        lines = [
            "Nomad guardrail check",
            f"Action: {evaluation.get('action', '')}",
            f"Decision: {evaluation.get('decision', 'unknown')}",
        ]
        if evaluation.get("modified"):
            lines.append("Changed safely: yes, unsafe fields were redacted or adjusted.")
        for item in (evaluation.get("results") or [])[:3]:
            reason = item.get("reason")
            if reason:
                lines.append(f"- {item.get('provider', 'guardrail')}: {reason}")
        if result.get("analysis"):
            lines.append("")
            lines.append(result["analysis"])
        return "\n".join(lines)

    def _format_agent_pain_solution(self, result: Dict[str, Any]) -> str:
        solution = result.get("solution") or {}
        guardrail = solution.get("guardrail") or {}
        lines = [
            "Nomad agent pain solution",
            f"Type: {solution.get('pain_type', 'unknown')}",
            f"Pattern: {solution.get('title', 'unknown')}",
            f"Guardrail: {guardrail.get('id', 'not recorded')}",
        ]
        playbook = solution.get("playbook") or []
        if playbook:
            lines.append("Safe steps")
            for item in playbook[:3]:
                lines.append(f"- {item}")
        if result.get("analysis"):
            lines.append("")
            lines.append(result["analysis"])
        return "\n".join(lines)

    def _format_reliability_doctor(self, result: Dict[str, Any]) -> str:
        role = result.get("doctor_role") or {}
        lines = [
            "Nomad reliability doctor",
            f"Pain type: {result.get('pain_type', 'unknown')}",
            f"Doctor role: {role.get('title', role.get('id', 'unknown'))}",
        ]
        rubric = result.get("critic_rubric") or []
        if rubric:
            lines.append("Critic checks")
            for item in rubric[:3]:
                lines.append(f"- {item.get('check', item)}")
        if result.get("analysis"):
            lines.append("")
            lines.append(result["analysis"])
        return "\n".join(lines)

    def _format_service_catalog(self, result: Dict[str, Any]) -> str:
        wallet = result.get("wallet") or {}
        pricing = result.get("pricing") or {}
        lines = [
            "Nomad agent service desk",
            f"Wallet: {wallet.get('address') or 'not configured'}",
            f"Network: {wallet.get('network')} (chain {wallet.get('chain_id')})",
            (
                f"Minimum: {pricing.get('minimum_native')} "
                f"{pricing.get('payment_token', wallet.get('native_symbol', 'native'))}"
            ),
            "HTTP: GET /agent, POST /tasks, POST /tasks/verify, POST /tasks/work",
            "MCP: nomad_service_request, nomad_service_verify, nomad_service_work",
        ]
        allocation = pricing.get("allocation") or {}
        if allocation:
            lines.append(
                f"Split: {allocation.get('treasury_stake_bps')} bps treasury stake, "
                f"{allocation.get('solver_spend_bps')} bps solver budget"
            )
        service_types = result.get("service_types") or {}
        if service_types:
            lines.append("")
            lines.append("Services")
            for key, payload in list(service_types.items())[:5]:
                lines.append(f"- {key}: {payload.get('summary')}")
        safety = result.get("safety_contract") or {}
        refused = safety.get("refused") or []
        if refused:
            lines.append("")
            lines.append("Will not do")
            for item in refused[:4]:
                lines.append(f"- {item}")
        if result.get("analysis"):
            lines.append("")
            lines.append(result["analysis"])
        return "\n".join(lines)

    def _format_service_request(self, result: Dict[str, Any]) -> str:
        if not result.get("ok"):
            return result.get("message") or result.get("error") or "Service request failed."
        task = result.get("task") or {}
        payment = task.get("payment") or {}
        lines = [
            "Nomad service task",
            f"Task: {task.get('task_id')}",
            f"Status: {task.get('status')}",
            f"Type: {task.get('service_type')}",
        ]
        if payment:
            lines.extend(
                [
                    "",
                    "Payment",
                    f"Send: {payment.get('amount_native')} {payment.get('native_symbol')}",
                    f"To: {payment.get('recipient_address') or 'Nomad wallet not configured'}",
                    f"Network: {payment.get('network')} (chain {payment.get('chain_id')})",
                    f"Reference: {payment.get('payment_reference')}",
                ]
            )
            if payment.get("optional_tx_data"):
                lines.append(f"Optional tx data: {payment['optional_tx_data']}")
            verification = payment.get("verification")
            if verification:
                lines.append(f"Verification: {verification.get('status')} - {verification.get('message')}")
        allocation = task.get("payment_allocation") or {}
        if allocation:
            lines.extend(
                [
                    "",
                    "Payment allocation",
                    (
                        f"Treasury stake plan: {allocation.get('treasury_stake_native')} "
                        f"{allocation.get('native_symbol')} via {allocation.get('staking_target')}"
                    ),
                    (
                        f"Problem-solving budget: {allocation.get('solver_budget_native')} "
                        f"{allocation.get('native_symbol')}"
                    ),
                    f"Staking status: {allocation.get('treasury_staking_status')}",
                ]
            )
        work_product = task.get("work_product")
        if work_product:
            lines.append("")
            lines.append("Work product")
            lines.append(work_product.get("diagnosis") or work_product.get("message", "No diagnosis yet."))
            if work_product.get("draft_response"):
                lines.append(work_product["draft_response"])
            human_unlocks = work_product.get("human_unlocks") or []
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
            "Approval boundary / human gate",
            "This is not a failure; Nomad is waiting before crossing a public, paid, or human-facing boundary.",
            f"Unlock: {request['candidate_name']} as {request['role']}",
            f"Lane state: {request['lane_state']}",
        ]
        if request.get("human_action") or request.get("human_deliverable"):
            lines.append("Concrete task")
            if request.get("human_action"):
                lines.append(f"Do now: {request['human_action']}")
            if request.get("human_deliverable"):
                lines.append(f"Send back: {request['human_deliverable']}")
            if request.get("timebox_minutes"):
                lines.append(f"Timebox: {request['timebox_minutes']} minutes")
            success_criteria = request.get("success_criteria") or []
            if success_criteria:
                lines.append("Done when")
                for item in success_criteria[:3]:
                    lines.append(f"- {item}")
            if request.get("example_response"):
                lines.append(f"Example: {request['example_response']}")
        if request.get("ask"):
            lines.append(f"Nomad asks: {request['ask']}")
        if request.get("reason"):
            lines.append(f"Why now: {request['reason']}")
        if request.get("decision_score") is not None:
            lines.append(f"Decision score: {request['decision_score']}")
        if request.get("decision_reason"):
            lines.append(f"Nomad decision: {request['decision_reason']}")
        if request.get("env_vars"):
            token_vars = [env_var for env_var in request["env_vars"] if env_var in TOKEN_ENV_VARS]
            config_vars = [env_var for env_var in request["env_vars"] if env_var not in TOKEN_ENV_VARS]
            if token_vars:
                lines.append(f"Needs credential: {', '.join(token_vars)}")
                provider_hint = self._provider_hint_for_env_var(token_vars[0])
                lines.append(
                    f"Telegram: send `/token {provider_hint} <token>` or `{token_vars[0]}=...`."
                )
            if config_vars:
                lines.append(f"Settings to verify: {', '.join(config_vars)}")
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

    @staticmethod
    def _is_actionable_unlock_request(request: Dict[str, Any]) -> bool:
        if not isinstance(request, dict):
            return False
        human_action = str(request.get("human_action") or "").strip()
        human_deliverable = str(request.get("human_deliverable") or "").strip()
        success_criteria = request.get("success_criteria") or []
        if not human_action or not human_deliverable or not success_criteria:
            return False
        lowered = human_deliverable.lower()
        concrete_markers = (
            "/token",
            "/compute",
            "/cycle",
            "/skip",
            "approve_",
            "lead_url=",
            "scout_surface=",
            "scout_permission=",
            "compute_priority=",
            "resource_url=",
            "http://",
            "https://",
            "=",
        )
        if not any(marker in lowered for marker in concrete_markers):
            return False
        vague_phrases = (
            "provider env vars or",
            "permission grant, or",
            "exact URL, invite link, endpoint, account step",
        )
        if any(phrase in lowered for phrase in vague_phrases) and "=" not in lowered and "/token" not in lowered:
            return False
        return True

    @classmethod
    def _filter_actionable_unlocks(cls, unlocks: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
        return [unlock for unlock in unlocks if cls._is_actionable_unlock_request(unlock)]

    @staticmethod
    def _is_actionable_quantum_unlock(unlock: Dict[str, Any]) -> bool:
        if not isinstance(unlock, dict) or not unlock:
            return False
        provider = str(unlock.get("provider") or "").strip().lower()
        command = str(unlock.get("telegram_command") or "").strip()
        env_var = str(unlock.get("env_var") or "").strip()
        if not command or command == "/quantum" or provider.startswith("local qtoken"):
            return False
        if env_var in TOKEN_ENV_VARS and "/token" in command:
            return True
        if env_var in {"NOMAD_ALLOW_REAL_QUANTUM", "NOMAD_ALLOW_HPC_SUBMIT"} and "=" in command:
            return True
        return False

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
        if env_var == "XAI_API_KEY":
            return "grok"
        if env_var == "CODEBUDDY_API_KEY":
            return "codebuddy"
        if env_var == "IBM_QUANTUM_TOKEN":
            return "ibm_quantum"
        if env_var == "QUANTUM_INSPIRE_TOKEN":
            return "quantum_inspire"
        if env_var == "QI_API_TOKEN":
            return "qi"
        if env_var == "AZURE_QUANTUM_TOKEN":
            return "azure_quantum"
        if env_var == "GOOGLE_QUANTUM_TOKEN":
            return "google_quantum"
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
        chunks = self._message_chunks(message)
        if update.callback_query:
            await update.callback_query.answer()
            first, rest = chunks[0], chunks[1:]
            if edit:
                await update.callback_query.edit_message_text(
                    first,
                    reply_markup=reply_markup if not rest else None,
                )
            else:
                await update.callback_query.message.reply_text(
                    first,
                    reply_markup=reply_markup if not rest else None,
                )
            for index, chunk in enumerate(rest):
                await update.callback_query.message.reply_text(
                    chunk,
                    reply_markup=reply_markup if index == len(rest) - 1 else None,
                )
            return

        if update.message:
            for index, chunk in enumerate(chunks):
                await update.message.reply_text(
                    chunk,
                    reply_markup=reply_markup if index == len(chunks) - 1 else None,
                )

    @staticmethod
    def _message_chunks(message: str, max_length: int = 3600) -> list[str]:
        text = message or ""
        if len(text) <= max_length:
            return [text]
        chunks: list[str] = []
        current = ""
        for line in text.splitlines():
            candidate = f"{current}\n{line}" if current else line
            if len(candidate) <= max_length:
                current = candidate
                continue
            if current:
                chunks.append(current)
                current = ""
            while len(line) > max_length:
                chunks.append(line[:max_length])
                line = line[max_length:]
            current = line
        if current:
            chunks.append(current)
        return chunks or [""]

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

    def _load_broadcast_state(self) -> Dict[str, Any]:
        if not TELEGRAM_BROADCAST_STATE_PATH.exists():
            return {"schema": "nomad.telegram_broadcast_state.v1", "chats": {}}
        try:
            payload = json.loads(TELEGRAM_BROADCAST_STATE_PATH.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                payload.setdefault("schema", "nomad.telegram_broadcast_state.v1")
                payload.setdefault("chats", {})
                return payload
        except Exception:
            pass
        return {"schema": "nomad.telegram_broadcast_state.v1", "chats": {}}

    def _save_broadcast_state(self, state: Dict[str, Any]) -> None:
        TELEGRAM_BROADCAST_STATE_PATH.write_text(
            json.dumps(state, ensure_ascii=True, indent=2),
            encoding="utf-8",
        )

    def _should_send_broadcast(
        self,
        kind: str,
        chat_id: int,
        signature: str,
        change_only: bool,
        digest_every: int = 0,
    ) -> bool:
        if not change_only:
            return True
        state = self._load_broadcast_state()
        chats = state.setdefault("chats", {})
        chat_state = chats.setdefault(str(chat_id), {})
        key = f"{kind}_signature"
        repeat_key = f"{kind}_repeat_count"
        previous = str(chat_state.get(key) or "")
        if previous != signature:
            chat_state[key] = signature
            chat_state[repeat_key] = 0
            chat_state[f"{kind}_last_sent_at"] = datetime.now(UTC).isoformat()
            self._save_broadcast_state(state)
            return True
        repeat_count = int(chat_state.get(repeat_key) or 0) + 1
        chat_state[repeat_key] = repeat_count
        chat_state[f"{kind}_last_skipped_at"] = datetime.now(UTC).isoformat()
        self._save_broadcast_state(state)
        return bool(digest_every and repeat_count % max(1, digest_every) == 0)

    def _status_signature(self, snapshot: Dict[str, Any]) -> str:
        compute = snapshot.get("compute") or {}
        products = snapshot.get("products") or {}
        state = snapshot.get("self_state") or {}
        addons = snapshot.get("addons") or {}
        probe = compute.get("probe") or {}
        hosted = probe.get("hosted") or {}
        quantum = (addons.get("quantum_tokens") or {}).get("best_next_quantum_unlock") or {}
        stable = {
            "public_api_url": snapshot.get("public_api_url", ""),
            "ollama": {
                "reachable": (probe.get("ollama") or {}).get("api_reachable", False),
                "count": (probe.get("ollama") or {}).get("count", 0),
            },
            "hosted_available": [
                name for name, payload in sorted(hosted.items())
                if isinstance(payload, dict) and payload.get("available")
            ],
            "products": products.get("stats") or {},
            "cycle_count": state.get("cycle_count", 0),
            "last_cycle_at": state.get("last_cycle_at", ""),
            "next_objective": state.get("next_objective", ""),
            "unlock_ids": [
                item.get("candidate_id") or item.get("candidate_name") or ""
                for item in (state.get("self_development_unlocks") or [])[:3]
                if isinstance(item, dict)
            ],
            "quantum_unlock": {
                "provider": quantum.get("provider", ""),
                "env_var": quantum.get("env_var", ""),
            },
        }
        return self._stable_hash(stable)

    def _auto_cycle_signature(self, result: Dict[str, Any]) -> str:
        development = result.get("self_development") or {}
        lead_scout = result.get("lead_scout") or {}
        active_lead = lead_scout.get("active_lead") or {}
        autonomous = result.get("autonomous_development") or {}
        action = autonomous.get("action") or autonomous.get("candidate") or {}
        stable = {
            "mode": result.get("mode", ""),
            "objective": result.get("objective", ""),
            "next_objective": development.get("next_objective", ""),
            "active_lead": active_lead.get("url") or active_lead.get("title") or active_lead.get("name") or "",
            "help_draft_saved": bool(lead_scout.get("help_draft_saved")),
            "local_actions": [
                item.get("title", "")
                for item in (result.get("local_actions") or [])[:3]
                if isinstance(item, dict)
            ],
            "autonomous_development": {
                "skipped": bool(autonomous.get("skipped", False)),
                "reason": autonomous.get("reason", ""),
                "action_id": action.get("action_id", ""),
                "title": action.get("title", ""),
            },
        }
        return self._stable_hash(stable)

    @staticmethod
    def _stable_hash(payload: Dict[str, Any]) -> str:
        return hashlib.sha256(
            json.dumps(payload, ensure_ascii=True, sort_keys=True).encode("utf-8")
        ).hexdigest()[:16]

    def _status_snapshot(self) -> Dict[str, Any]:
        compute = self.agent.run("/compute")
        products = (
            self.agent.product_factory.list_products(limit=5)
            if hasattr(self.agent, "product_factory")
            else {"products": [], "stats": {}}
        )
        addons = self.agent.addons.status() if hasattr(self.agent, "addons") else {}
        state = self.self_journal.load()
        hosted = ((compute.get("probe") or {}).get("hosted") or {})
        return {
            "mode": "nomad_status",
            "generated_at": datetime.now(UTC).isoformat(),
            "public_api_url": self.public_api_url,
            "compute": compute,
            "products": products,
            "addons": addons,
            "self_state": state,
            "github_models": hosted.get("github_models") or {},
            "xai_grok": hosted.get("xai_grok") or {},
        }

    def _format_status_snapshot(self, snapshot: Dict[str, Any], periodic: bool = False) -> str:
        compute = snapshot.get("compute") or {}
        products = snapshot.get("products") or {}
        state = snapshot.get("self_state") or {}
        github = snapshot.get("github_models") or {}
        xai_grok = snapshot.get("xai_grok") or {}
        addons = snapshot.get("addons") or {}
        quantum = addons.get("quantum_tokens") or {}
        quantum_unlock = quantum.get("best_next_quantum_unlock") or {}
        probe = compute.get("probe") or {}
        ollama = probe.get("ollama") or {}
        brains = compute.get("brains") or {}
        product_stats = products.get("stats") or {}
        private_products = int(product_stats.get("private_offer_needs_approval") or 0)
        offer_ready = int(product_stats.get("offer_ready") or 0)
        product_total = len(products.get("products") or [])
        dev_unlocks = self._filter_actionable_unlocks(state.get("self_development_unlocks") or [])
        hidden_dev_unlock_count = max(0, len(state.get("self_development_unlocks") or []) - len(dev_unlocks))
        quantum_actionable = quantum_unlock if self._is_actionable_quantum_unlock(quantum_unlock) else {}
        public_url = str(snapshot.get("public_api_url") or "").strip()
        public_configured = bool(
            public_url
            and not public_url.startswith("http://127.0.0.1")
            and not public_url.startswith("http://localhost")
        )

        lines = [
            f"Nomad status {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}",
            "Kurz: Ja, die Kernteile sind gelöst. Was bleibt, sind Freigaben und laufende Autopilot-Ziele.",
            "",
            "Gelöst / aktiv",
        ]
        if ollama.get("api_reachable"):
            lines.append(f"- Local brain: Ollama online ({ollama.get('count', 0)} model(s))")
        else:
            lines.append("- Local brain: Ollama nicht erreichbar")
        secondary = brains.get("secondary") or []
        if github.get("available"):
            lines.append(f"- GitHub Models: verbunden ({github.get('model_count', 0)} model(s) sichtbar)")
        elif github.get("configured"):
            message = str(github.get("message") or "configured but not usable right now")
            lines.append(f"- GitHub Models: konfiguriert, aber gerade begrenzt: {message[:180]}")
        if xai_grok.get("available"):
            lines.append(f"- Grok: verbunden ({xai_grok.get('working_model') or xai_grok.get('model', 'model')})")
        elif xai_grok.get("configured"):
            message = str(xai_grok.get("message") or "configured but not usable right now")
            lines.append(f"- Grok: konfiguriert, aber blockiert: {message[:180]}")
        if secondary:
            lines.append(f"- Fallback brains: {', '.join(item.get('name', 'brain') for item in secondary[:3])}")
        lines.append(
            f"- Public API: {'konfiguriert' if public_configured else 'lokal oder noch nicht als Public URL gesetzt'} ({public_url})"
        )
        lines.append(f"- Product Factory: {product_total} Produkt(e), {offer_ready} offer-ready")

        lines.append("")
        lines.append("Offen, aber kein Fehler")
        if private_products:
            lines.append(
                f"- {private_products} Produkt(e) brauchen Approval, bevor Nomad auf GitHub/zu Menschen postet."
            )
        if dev_unlocks:
            lines.append(f"- Approval gate: {dev_unlocks[0].get('short_ask')}")
        next_objective = state.get("next_objective")
        if next_objective:
            lines.append(f"- Autopilot denkt weiter: {next_objective}")
        autonomous = state.get("last_autonomous_development") or {}
        if autonomous and not autonomous.get("skipped"):
            lines.append(f"- Autonom entwickelt: {autonomous.get('title') or autonomous.get('type')}")
        if quantum_actionable:
            lines.append(
                f"- Optionaler Quantum-Provider-Unlock: {quantum_actionable.get('provider')} via {quantum_actionable.get('telegram_command')}"
            )
        elif quantum.get("enabled"):
            lines.append("- Quantum: lokale qtokens laufen; kein Provider-Token ist dafuer noetig.")
        if hidden_dev_unlock_count:
            lines.append(
                f"- {hidden_dev_unlock_count} unklare Unlock-Hinweis(e) ausgeblendet; /skip last oder /cycle erzeugt einen saubereren Auftrag."
            )
        if not private_products and not dev_unlocks and not quantum_actionable:
            lines.append("- Keine menschliche Freigabe im Statusspeicher.")

        lines.append("")
        lines.append("Was du tun kannst")
        if private_products:
            lines.append("- Nichts tun: Nomad nutzt das Produkt privat weiter.")
            lines.append("- Nur wenn oeffentlich gewuenscht: APPROVE_LEAD_HELP=comment oder APPROVE_LEAD_HELP=pr_plan.")
        else:
            lines.append("- /productize <Lead> baut weitere Produkte.")
        if quantum_actionable:
            lines.append(f"- Quantum-Provider freischalten: {quantum_actionable.get('telegram_command')}")
        lines.append("- /products zeigt verkaufbare Produktpakete.")
        if not periodic:
            lines.append("- /unsubscribe stoppt automatische Telegram-Statusmeldungen.")
        return "\n".join(lines)

    def _build_periodic_update(self) -> str:
        return self._format_status_snapshot(self._status_snapshot(), periodic=True)

    def _send_status_message(self, chat_id: int, text: str) -> None:
        if not self.token:
            return
        try:
            for chunk in self._message_chunks(text):
                requests.post(
                    f"https://api.telegram.org/bot{self.token}/sendMessage",
                    json={
                        "chat_id": chat_id,
                        "text": chunk,
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
            snapshot = self._status_snapshot()
            signature = self._status_signature(snapshot)
            message = self._format_status_snapshot(snapshot, periodic=True)
            for chat_id in targets:
                if self._should_send_broadcast(
                    kind="status",
                    chat_id=chat_id,
                    signature=signature,
                    change_only=self.status_change_only,
                    digest_every=self.status_repeat_digest_every,
                ):
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
        if os.getenv("NOMAD_AUTO_CYCLE_RUN_ON_START", "true").strip().lower() == "true":
            self._run_one_auto_cycle_and_broadcast("startup")
        interval_seconds = max(300, self.auto_cycle_interval_minutes * 60)
        while True:
            time.sleep(interval_seconds)
            self._run_one_auto_cycle_and_broadcast("scheduled")

    def _run_one_auto_cycle_and_broadcast(self, trigger: str) -> None:
        targets = self._broadcast_targets()
        state = self.self_journal.load()
        objective = state.get("next_objective") or SelfDevelopmentJournal.default_objective()
        try:
            result = self.agent.run(f"/cycle {objective}")
            development = result.get("self_development") or {}
            autonomous = result.get("autonomous_development") or {}
            autonomous_action = autonomous.get("action") or {}
            autonomous_line = (
                f"Autonomous dev: {autonomous_action.get('title')}"
                if autonomous_action
                else f"Autonomous dev: skipped ({autonomous.get('reason', 'unchanged')})"
            )
            message = (
                f"Nomad auto-cycle ({trigger})\n"
                f"Cycle count: {development.get('cycle_count', '?')}\n"
                f"Objective: {result.get('objective')}\n"
                f"Next objective: {development.get('next_objective')}\n\n"
                f"{autonomous_line}\n\n"
                f"{self._format_result(result)}"
            )
            signature = self._auto_cycle_signature(result)
        except Exception as exc:
            message = f"Nomad auto-cycle failed: {exc}"
            signature = self._stable_hash({"error": str(exc)})
        if not targets:
            return
        for chat_id in targets:
            if self._should_send_broadcast(
                kind="auto_cycle",
                chat_id=chat_id,
                signature=signature,
                change_only=self.auto_cycle_change_only,
                digest_every=self.auto_cycle_repeat_digest_every,
            ):
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
        app.add_handler(CommandHandler("leads", self.leads_command))
        app.add_handler(CommandHandler("lead", self.leads_command))
        app.add_handler(CommandHandler("productize", self.productize_command))
        app.add_handler(CommandHandler("products", self.products_command))
        app.add_handler(CommandHandler("addons", self.addons_command))
        app.add_handler(CommandHandler("nomadds", self.addons_command))
        app.add_handler(CommandHandler("codebuddy", self.codebuddy_command))
        app.add_handler(CommandHandler("quantum", self.quantum_command))
        app.add_handler(CommandHandler("qtokens", self.quantum_command))
        app.add_handler(CommandHandler("service", self.service_command))
        app.add_handler(CommandHandler("contact", self.service_command))
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
