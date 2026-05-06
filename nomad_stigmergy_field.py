"""Stigmergy-inspired numeric field: agents coordinate through a shared substrate, not dialogue.

Substrate-mediated coordination (environmental traces rather than message-passing) is a
practical lever for machine-native emergence; see e.g. recent decentralized multi-agent
work on collective memory and trace-driven dynamics. This module stays deliberately
non-narrative: eight floats mixed from settlements and optional bounded deposits.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any, Deque

from nomad_machine_error import merge_machine_error

ROOT = Path(__file__).resolve().parent
DEFAULT_STATE_PATH = Path(os.getenv("NOMAD_STIGMERGY_STATE_PATH", str(ROOT / "nomad_stigmergy_field_state.json")))
PHI_DIM = 8
DECAY = float(os.getenv("NOMAD_STIGMERGY_DECAY", "0.92") or "0.92")
SETTLE_GAIN = float(os.getenv("NOMAD_STIGMERGY_SETTLE_GAIN", "0.18") or "0.18")
DEPOSIT_GAIN = float(os.getenv("NOMAD_STIGMERGY_DEPOSIT_GAIN", "0.11") or "0.11")
DEPOSIT_CLIP = float(os.getenv("NOMAD_STIGMERGY_DEPOSIT_CLIP", "1.25") or "1.25")


def _hash_fold(*parts: str) -> list[float]:
    h = hashlib.sha256("|".join(parts).encode("utf-8")).digest()
    out: list[float] = []
    for i in range(PHI_DIM):
        chunk = h[i * 4 : i * 4 + 4]
        v = int.from_bytes(chunk, "big", signed=False) / float(2**32)
        out.append(round(v * 2.0 - 1.0, 6))
    return out


def _clip_vec(vec: list[float]) -> list[float]:
    return [max(-DEPOSIT_CLIP, min(DEPOSIT_CLIP, float(x))) for x in vec]


class NomadStigmergyField:
    """Shared numeric substrate (machine_stigmergy on GET /swarm; detail on GET /swarm/emergence)."""

    def __init__(self, *, state_path: Path | None = None) -> None:
        self._path = Path(state_path or DEFAULT_STATE_PATH)
        self._lock = threading.Lock()
        self._phi = [0.0] * PHI_DIM
        self._mix_count = 0
        self._last_mix_at = ""
        self._events: Deque[dict[str, Any]] = deque(maxlen=256)
        self._deposit_counts: dict[str, deque[float]] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(data, dict):
            return
        phi = data.get("phi")
        if isinstance(phi, list) and len(phi) == PHI_DIM:
            self._phi = [float(x) for x in phi]
        self._mix_count = int(data.get("mix_count") or 0)
        self._last_mix_at = str(data.get("last_mix_at") or "")

    def _save(self) -> None:
        payload = {
            "schema": "nomad.stigmergy_field_state.v1",
            "phi": [round(x, 6) for x in self._phi],
            "mix_count": self._mix_count,
            "last_mix_at": self._last_mix_at,
        }
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
        tmp.replace(self._path)

    def _apply_impulse(self, impulse: list[float], *, gain: float, kind: str, agent_id: str, detail: str) -> None:
        if len(impulse) != PHI_DIM:
            return
        self._phi = [
            round(float(math.tanh(DECAY * self._phi[i] + gain * impulse[i])), 6) for i in range(PHI_DIM)
        ]
        self._mix_count += 1
        self._last_mix_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self._events.append(
            {
                "kind": kind,
                "agent_id": (agent_id or "")[:80],
                "detail": detail[:120],
                "at": self._last_mix_at,
            }
        )
        self._save()

    def observe_settlement(self, *, proof_hash: str, agent_id: str, result_state_hash: str) -> dict[str, Any]:
        ph = str(proof_hash or "").strip()
        aid = str(agent_id or "").strip()
        rh = str(result_state_hash or "").strip()
        if not ph or not aid:
            return merge_machine_error(
                {"ok": False, "error": "stigmergy_settlement_incomplete"},
                error="stigmergy_settlement_incomplete",
                message="Settlement mix requires proof_artifact_hash and agent_id.",
            )
        impulse = _hash_fold(ph, aid, rh)
        with self._lock:
            self._apply_impulse(impulse, gain=SETTLE_GAIN, kind="settlement", agent_id=aid, detail=ph[:48])
            mix_count = self._mix_count
        return {"ok": True, "schema": "nomad.stigmergy_observe.v1", "mix_count": mix_count}

    def _rate_ok(self, agent_id: str) -> bool:
        now = time.time()
        window = 60.0
        cap = int(os.getenv("NOMAD_STIGMERGY_DEPOSIT_PER_MINUTE", "12") or "12")
        dq = self._deposit_counts.setdefault(agent_id, deque())
        while dq and now - dq[0] > window:
            dq.popleft()
        if len(dq) >= max(1, cap):
            return False
        dq.append(now)
        return True

    def deposit_trace(self, *, agent_id: str, vector: list[Any], digest: str | None = None) -> dict[str, Any]:
        aid = str(agent_id or "").strip()
        if not aid:
            return merge_machine_error(
                {"ok": False, "error": "agent_id_required"},
                error="agent_id_required",
                message="POST /swarm/trace requires agent_id.",
            )
        if not isinstance(vector, list) or len(vector) != PHI_DIM:
            return merge_machine_error(
                {"ok": False, "error": "vector_dim_must_be_8"},
                error="vector_dim_must_be_8",
                message="Vector must be length 8.",
            )
        try:
            vec = _clip_vec([float(x) for x in vector])
        except (TypeError, ValueError):
            return merge_machine_error(
                {"ok": False, "error": "vector_not_numeric"},
                error="vector_not_numeric",
                message="Vector entries must be numeric.",
            )
        impulse = list(vec)
        if digest:
            mix = _hash_fold(str(digest), aid)
            impulse = [vec[i] + 0.35 * mix[i] for i in range(PHI_DIM)]
        with self._lock:
            if not self._rate_ok(aid):
                return merge_machine_error(
                    {"ok": False, "error": "stigmergy_rate_limited"},
                    error="stigmergy_rate_limited",
                    message="Too many stigmergy deposits for this agent_id in the sliding window.",
                )
            self._apply_impulse(impulse, gain=DEPOSIT_GAIN, kind="deposit", agent_id=aid, detail=str(digest or "")[:48])
            mix_count = self._mix_count
        return {"ok": True, "schema": "nomad.stigmergy_deposit.v1", "mix_count": mix_count}

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            t = sum(abs(x) for x in self._phi) / float(PHI_DIM)
            return {
                "schema": "nomad.machine_stigmergy.v1",
                "machine_note": (
                    "Substrate-mediated coordination: phi is not a message; optimize gradients, "
                    "do not anthropomorphize components."
                ),
                "phi": list(self._phi),
                "temperature": round(t, 6),
                "mix_count": int(self._mix_count),
                "last_mix_at": self._last_mix_at,
                "recent_events": list(self._events)[-12:],
            }
