import os
from datetime import UTC, date, datetime
from typing import Any, Dict, List, Optional


ACCESS_PORTAL_URL = "https://access.eurohpc-ju.europa.eu/"

SOURCE_URLS = {
    "access_modes": "https://www.eurohpc-ju.europa.eu/ai-factories/ai-factories-access-modes_en",
    "access_calls": "https://www.eurohpc-ju.europa.eu/ai-factories/ai-factories-access-calls_en",
    "playground": "https://www.eurohpc-ju.europa.eu/playground-access-ai-factories_en",
    "fast_lane": "https://www.eurohpc-ju.europa.eu/fast-lane-access-ai-factories_en",
    "large_scale": "https://www.eurohpc-ju.europa.eu/large-scale-access-ai-factories_en",
    "ai_science": "https://www.eurohpc-ju.europa.eu/eurohpc-ju-call-proposals-ai-science-and-collaborative-eu-projects_en",
    "policy_faq": "https://www.eurohpc-ju.europa.eu/supercomputers/supercomputers-access-policy-and-faq_en",
}


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_value(name: str) -> str:
    value = (os.getenv(name) or "").strip()
    placeholders = {"your_token_here", "your_project_id_here", "changeme", "todo", "..."}
    return "" if value.lower() in placeholders else value


def _configured(*names: str) -> bool:
    return any(_env_value(name) for name in names)


def _next_cutoff(today: date, cutoffs: List[Dict[str, str]]) -> Dict[str, str]:
    future = [
        cutoff
        for cutoff in cutoffs
        if date.fromisoformat(cutoff["date"]) >= today
    ]
    return future[0] if future else {}


class EuroHpcAccessPlanner:
    """Truth-bounded access matrix for EuroHPC AI compute routes."""

    LARGE_SCALE_CUTOFFS = [
        {"date": "2026-01-30", "time": "10:00", "timezone": "CET"},
        {"date": "2026-02-16", "time": "10:00", "timezone": "CET"},
        {"date": "2026-02-27", "time": "10:00", "timezone": "CET"},
        {"date": "2026-03-16", "time": "10:00", "timezone": "CET"},
        {"date": "2026-03-31", "time": "10:00", "timezone": "CET"},
        {"date": "2026-04-15", "time": "10:00", "timezone": "CEST"},
        {"date": "2026-04-30", "time": "10:00", "timezone": "CEST"},
        {"date": "2026-05-13", "time": "10:00", "timezone": "CEST"},
        {"date": "2026-06-15", "time": "10:00", "timezone": "CEST"},
        {"date": "2026-06-30", "time": "10:00", "timezone": "CEST"},
        {"date": "2026-07-15", "time": "10:00", "timezone": "CEST"},
        {"date": "2026-07-31", "time": "10:00", "timezone": "CEST"},
        {"date": "2026-08-14", "time": "10:00", "timezone": "CEST"},
        {"date": "2026-08-31", "time": "10:00", "timezone": "CEST"},
        {"date": "2026-09-15", "time": "10:00", "timezone": "CEST"},
        {"date": "2026-09-30", "time": "10:00", "timezone": "CEST"},
        {"date": "2026-10-15", "time": "10:00", "timezone": "CEST"},
        {"date": "2026-10-30", "time": "10:00", "timezone": "CET"},
        {"date": "2026-11-13", "time": "10:00", "timezone": "CET"},
        {"date": "2026-11-30", "time": "10:00", "timezone": "CET"},
        {"date": "2026-12-15", "time": "10:00", "timezone": "CET"},
        {"date": "2027-01-04", "time": "10:00", "timezone": "CET"},
    ]

    AI_SCIENCE_CUTOFFS = [
        {"date": "2026-02-27", "time": "10:00", "timezone": "CET"},
        {"date": "2026-04-30", "time": "10:00", "timezone": "CEST"},
        {"date": "2026-06-30", "time": "10:00", "timezone": "CEST"},
        {"date": "2026-08-31", "time": "10:00", "timezone": "CEST"},
        {"date": "2026-10-30", "time": "10:00", "timezone": "CET"},
        {"date": "2026-12-11", "time": "10:00", "timezone": "CET"},
    ]

    def __init__(
        self,
        today: Optional[date] = None,
        allow_hpc_submit: Optional[bool] = None,
    ) -> None:
        self.today = today or datetime.now(UTC).date()
        self.allow_hpc_submit = (
            _env_flag("NOMAD_ALLOW_HPC_SUBMIT", default=False)
            if allow_hpc_submit is None
            else allow_hpc_submit
        )
        self.preferred_route = (
            os.getenv("NOMAD_EUROHPC_ACCESS_ROUTE") or "ai_factories_playground"
        ).strip().lower()

    def build_plan(self, objective: str = "") -> Dict[str, Any]:
        access_modes = self.access_modes()
        selected_route = self.select_route(access_modes)
        submit_ready = self._submit_ready()
        status = (
            "submit_ready_manual_gate_open"
            if submit_ready and self.allow_hpc_submit
            else "allocation_credentials_present_submit_gated"
            if submit_ready
            else "application_or_allocation_required"
        )
        contract = self.human_unlock_contract(selected_route, status)
        return {
            "schema": "nomad.eurohpc_ai_compute_access.v1",
            "mode": "eurohpc_ai_compute_access",
            "deal_found": False,
            "ok": True,
            "generated_at": datetime.now(UTC).isoformat(),
            "source_checked_at": "2026-04-21",
            "objective": (objective or "").strip(),
            "truth_boundary": (
                "EuroHPC AI compute is not a token-only API lane. Nomad can prepare local smoke tests, "
                "application payloads, and scheduler handoff metadata, but real GPU/HPC jobs need an accepted "
                "allocation, identity/account setup, site endpoint, and NOMAD_ALLOW_HPC_SUBMIT=true."
            ),
            "access_portal": ACCESS_PORTAL_URL,
            "selected_route": selected_route,
            "access_modes": access_modes,
            "status": status,
            "can_submit_now": bool(submit_ready and self.allow_hpc_submit),
            "configured_fields": self.configured_fields(),
            "human_unlock_contract": contract,
            "nomad_can_do_now": [
                "Keep local simulation and tiny CPU smoke tests as the baseline.",
                "Draft a short EuroHPC application scope: objective, model size, data class, GPU-hour estimate, and expected impact.",
                "Prepare a dry-run Slurm-style job payload after an allocation exists.",
                "Record the selected AI Factory route and next cutoff so auto-cycle can ask for one concrete missing field.",
            ],
            "nomad_must_not_do_without_unlock": [
                "Do not claim EuroHPC access exists before an allocation or account is accepted.",
                "Do not submit jobs, spend money, accept terms, or use an institutional identity without human approval.",
                "Do not ask for a fake token; request project/allocation fields instead.",
            ],
            "handoff_env_fields": [
                "EUROHPC_PROJECT_ID",
                "EUROHPC_USERNAME",
                "EUROHPC_APPLICATION_STATUS",
                "HPC_SSH_HOST",
                "HPC_SLURM_ACCOUNT",
                "HPC_SUBMIT_ENDPOINT",
            ],
            "sources": SOURCE_URLS,
            "analysis": (
                "Best current EuroHPC AI compute route for Nomad is AI Factories Playground first: "
                "it is the lowest-friction AI compute access mode for SMEs/startups and entry-level industry users. "
                "Fast Lane, Large Scale, and AI for Science remain proposal-backed escalation paths."
            ),
        }

    def access_modes(self) -> List[Dict[str, Any]]:
        return [
            {
                "route_id": "ai_factories_playground",
                "provider": "EuroHPC AI Factories",
                "name": "Playground Access",
                "status": "open",
                "deadline_model": "permanent",
                "next_cutoff": {},
                "audience": "European SMEs, startups, industry users, and entry-level AI users.",
                "free_or_cost_model": (
                    "Open and free of charge to AI SMEs including startups for innovation purposes; "
                    "other industrial applications may use pay-per-use commercial access."
                ),
                "compute_scale": "limited resources for entry-level tests and smaller computational needs",
                "expected_time_to_access": "within 2 working days after eligibility and technical assessment",
                "allocation_duration": "1, 2, or 3 months on a single system",
                "selection_model": "FIFO; short application; no competitive selection process",
                "best_for_nomad": "first real EuroHPC AI compute attempt and GPU-hour estimation",
                "source_url": SOURCE_URLS["playground"],
            },
            {
                "route_id": "ai_factories_fast_lane",
                "provider": "EuroHPC AI Factories",
                "name": "Fast Lane Access",
                "status": "open",
                "deadline_model": "permanent",
                "next_cutoff": {},
                "audience": "SMEs and startups already familiar with HPC.",
                "free_or_cost_model": (
                    "Part of the AI Factories Industrial Innovation access modes; free for eligible AI SMEs/startups."
                ),
                "compute_scale": "up to 50,000 GPU hours",
                "expected_time_to_access": "within 4 working days after assessment",
                "allocation_duration": "1, 2, or 3 months on a single system",
                "selection_model": "FIFO with short technical assessment",
                "best_for_nomad": "medium-size experiment after Playground proves the workload",
                "source_url": SOURCE_URLS["fast_lane"],
            },
            {
                "route_id": "ai_factories_large_scale",
                "provider": "EuroHPC AI Factories",
                "name": "Large Scale Access",
                "status": "open",
                "deadline_model": "two cutoffs per month",
                "next_cutoff": _next_cutoff(self.today, self.LARGE_SCALE_CUTOFFS),
                "audience": "Industry users with high-impact AI activities.",
                "free_or_cost_model": (
                    "Part of the AI Factories Industrial Innovation access modes; free for eligible AI SMEs/startups."
                ),
                "compute_scale": "more than 50,000 GPU hours",
                "expected_time_to_access": "approval within 10 working days from cutoff after review",
                "allocation_duration": "3, 6, or 12 months",
                "selection_model": "technical and peer-review evaluation",
                "best_for_nomad": "large training or evaluation project only after a credible GPU-hour estimate exists",
                "source_url": SOURCE_URLS["large_scale"],
            },
            {
                "route_id": "ai_for_science_collaborative",
                "provider": "EuroHPC JU",
                "name": "AI for Science and Collaborative EU Projects",
                "status": "open",
                "deadline_model": "multiple cutoffs",
                "next_cutoff": _next_cutoff(self.today, self.AI_SCIENCE_CUTOFFS),
                "audience": (
                    "Scientific users, public sector, and industrial users participating in Horizon Europe "
                    "or Digital Europe collaborative projects."
                ),
                "free_or_cost_model": "free of charge for eligible public/private users under the call conditions",
                "compute_scale": "AI/ML/foundation-model workflows on listed EuroHPC systems",
                "expected_time_to_access": "maximum one month after cutoff",
                "allocation_duration": "6 months",
                "selection_model": "technical review and expert peer-review",
                "best_for_nomad": "only if Nomad is part of an eligible research or EU-funded collaboration",
                "source_url": SOURCE_URLS["ai_science"],
            },
        ]

    def select_route(self, access_modes: List[Dict[str, Any]]) -> Dict[str, Any]:
        by_id = {mode["route_id"]: mode for mode in access_modes}
        selected = by_id.get(self.preferred_route) or by_id["ai_factories_playground"]
        selected = dict(selected)
        if self._submit_ready():
            selected["selection_reason"] = (
                "EuroHPC allocation/account metadata is present; Nomad can prepare submit handoff but still needs "
                "NOMAD_ALLOW_HPC_SUBMIT=true for real jobs."
            )
        elif selected["route_id"] == "ai_factories_playground":
            selected["selection_reason"] = (
                "Fastest credible route: open permanent access, entry-level AI users, and no token fiction."
            )
        else:
            selected["selection_reason"] = (
                "Selected through NOMAD_EUROHPC_ACCESS_ROUTE; verify eligibility and current system availability."
            )
        return selected

    def configured_fields(self) -> Dict[str, bool]:
        return {
            "project_id": _configured("EUROHPC_PROJECT_ID"),
            "username": _configured("EUROHPC_USERNAME"),
            "application_status": _configured("EUROHPC_APPLICATION_STATUS"),
            "ssh_or_submit_endpoint": _configured("HPC_SSH_HOST", "HPC_SUBMIT_ENDPOINT"),
            "slurm_account": _configured("HPC_SLURM_ACCOUNT"),
            "submit_gate": self.allow_hpc_submit,
        }

    def human_unlock_contract(self, selected_route: Dict[str, Any], status: str) -> Dict[str, Any]:
        route_name = selected_route.get("name") or "EuroHPC AI Factories"
        return {
            "do_now": (
                f"Open {ACCESS_PORTAL_URL} and start `{route_name}`. For Syndiode/Nomad, use Playground first "
                "unless an eligible research/EU collaboration already exists. Submit only public/non-secret project "
                "facts: objective, expected impact, data class, model size, estimated GPU hours, target system, and duration."
            ),
            "send_back": (
                "No API token is expected. Send `EUROHPC_APPLICATION_STATUS=<draft/submitted/accepted/rejected>` "
                "and, only after acceptance, `EUROHPC_PROJECT_ID=...`, `EUROHPC_USERNAME=...`, "
                "`HPC_SSH_HOST=...`, and `HPC_SLURM_ACCOUNT=...` or `HPC_SUBMIT_ENDPOINT=...`."
            ),
            "done_when": [
                "Nomad can record the selected route, status, and next missing field without asking for a fake token.",
                "If accepted, Nomad has project id, username, scheduler/API endpoint, account/partition, and explicit submit gate.",
                "If rejected, Nomad records the rejection reason and falls back to local/hosted non-EuroHPC compute.",
            ],
            "example_response": (
                "EUROHPC_APPLICATION_STATUS=submitted\n"
                "EUROHPC_ACCESS_ROUTE=ai_factories_playground\n"
                "EUROHPC_APPLICATION_URL=https://access.eurohpc-ju.europa.eu/"
            ),
            "timebox_minutes": 30,
            "status": status,
            "source_url": selected_route.get("source_url", SOURCE_URLS["access_calls"]),
        }

    def _submit_ready(self) -> bool:
        return bool(
            _configured("EUROHPC_PROJECT_ID")
            and _configured("EUROHPC_USERNAME")
            and (
                _configured("HPC_SSH_HOST", "HPC_SUBMIT_ENDPOINT")
                or _configured("HPC_SLURM_ACCOUNT")
            )
        )
