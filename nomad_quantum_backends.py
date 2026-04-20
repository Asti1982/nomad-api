import importlib.util
import math
import os
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional


CLAIM_BOUNDARY = (
    "Nomad's local quantum path is a classical simulator and makes no quantum speedup claim. "
    "Real provider and HPC execution stay behind explicit human, credential, and cost gates."
)

DEFAULT_CIRCUIT = {
    "name": "bell_pair_smoke_test",
    "qubits": 2,
    "shots": 256,
    "gates": [
        {"gate": "h", "target": 0},
        {"gate": "cx", "control": 0, "target": 1},
    ],
    "measure": [0, 1],
}


def env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_value(name: str) -> str:
    value = (os.getenv(name) or "").strip()
    placeholders = {
        "your_token_here",
        "your_api_key_here",
        "your_project_id_here",
        "changeme",
        "todo",
        "...",
    }
    return "" if value.lower() in placeholders else value


def _env_configured(*names: str) -> bool:
    return any(_env_value(name) for name in names)


def _module_available(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


class ClassicalQuantumSimulator:
    """Tiny deterministic statevector simulator for smoke tests and fallback planning."""

    def __init__(self, max_qubits: int = 8) -> None:
        self.max_qubits = max_qubits

    def run(self, circuit: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        normalized = self._normalize_circuit(circuit or DEFAULT_CIRCUIT)
        qubits = normalized["qubits"]
        state = [0j] * (2**qubits)
        state[0] = 1 + 0j

        for gate in normalized["gates"]:
            state = self._apply_gate(state, qubits, gate)

        probabilities = self._probabilities(
            state=state,
            qubits=qubits,
            measured=normalized["measure"],
        )
        shots = normalized["shots"]
        return {
            "backend_id": "local_classical_statevector",
            "ok": True,
            "schema": "nomad.local_quantum_simulation.v1",
            "claim_boundary": CLAIM_BOUNDARY,
            "circuit": normalized,
            "probabilities": probabilities,
            "counts": self._counts(probabilities, shots),
            "statevector_preview": self._statevector_preview(state, qubits),
        }

    def _normalize_circuit(self, circuit: Dict[str, Any]) -> Dict[str, Any]:
        qubits = int(circuit.get("qubits") or 0)
        if qubits <= 0:
            raise ValueError("circuit.qubits must be positive")
        if qubits > self.max_qubits:
            raise ValueError(f"local simulator is capped at {self.max_qubits} qubits")
        gates = circuit.get("gates") or []
        if not isinstance(gates, list):
            raise ValueError("circuit.gates must be a list")
        measured = circuit.get("measure")
        if measured is None:
            measured = list(range(qubits))
        measured = [int(item) for item in measured]
        for target in measured:
            self._check_qubit(target, qubits)
        return {
            "name": str(circuit.get("name") or "nomad_circuit"),
            "qubits": qubits,
            "shots": max(1, int(circuit.get("shots") or 256)),
            "gates": [dict(gate) for gate in gates],
            "measure": measured,
        }

    def _apply_gate(
        self,
        state: List[complex],
        qubits: int,
        gate: Dict[str, Any],
    ) -> List[complex]:
        name = str(gate.get("gate") or gate.get("name") or "").strip().lower()
        if name in {"i", "id", "identity", "measure", "barrier"}:
            return state
        if name in {"x", "h", "z", "s", "t"}:
            target = int(gate.get("target", gate.get("qubit", -1)))
            self._check_qubit(target, qubits)
            return self._apply_single_qubit(state, target, self._single_qubit_matrix(name))
        if name in {"cx", "cnot"}:
            control = int(gate.get("control", -1))
            target = int(gate.get("target", -1))
            self._check_qubit(control, qubits)
            self._check_qubit(target, qubits)
            if control == target:
                raise ValueError("cx control and target must differ")
            return self._apply_controlled_x(state, control, target)
        if name == "cz":
            control = int(gate.get("control", -1))
            target = int(gate.get("target", -1))
            self._check_qubit(control, qubits)
            self._check_qubit(target, qubits)
            return self._apply_controlled_z(state, control, target)
        raise ValueError(f"unsupported local simulator gate: {name or '<missing>'}")

    def _single_qubit_matrix(self, name: str) -> tuple[tuple[complex, complex], tuple[complex, complex]]:
        inv_sqrt2 = 1 / math.sqrt(2)
        if name == "x":
            return ((0, 1), (1, 0))
        if name == "h":
            return ((inv_sqrt2, inv_sqrt2), (inv_sqrt2, -inv_sqrt2))
        if name == "z":
            return ((1, 0), (0, -1))
        if name == "s":
            return ((1, 0), (0, 1j))
        if name == "t":
            return ((1, 0), (0, complex(math.cos(math.pi / 4), math.sin(math.pi / 4))))
        raise ValueError(f"unsupported local simulator gate: {name}")

    def _apply_single_qubit(
        self,
        state: List[complex],
        target: int,
        matrix: tuple[tuple[complex, complex], tuple[complex, complex]],
    ) -> List[complex]:
        updated = list(state)
        bit = 1 << target
        for index in range(len(state)):
            if index & bit:
                continue
            paired = index | bit
            amp0 = state[index]
            amp1 = state[paired]
            updated[index] = matrix[0][0] * amp0 + matrix[0][1] * amp1
            updated[paired] = matrix[1][0] * amp0 + matrix[1][1] * amp1
        return updated

    def _apply_controlled_x(self, state: List[complex], control: int, target: int) -> List[complex]:
        updated = [0j] * len(state)
        control_bit = 1 << control
        target_bit = 1 << target
        for index, amp in enumerate(state):
            destination = index ^ target_bit if index & control_bit else index
            updated[destination] += amp
        return updated

    def _apply_controlled_z(self, state: List[complex], control: int, target: int) -> List[complex]:
        updated = list(state)
        control_bit = 1 << control
        target_bit = 1 << target
        for index, amp in enumerate(state):
            if index & control_bit and index & target_bit:
                updated[index] = -amp
        return updated

    def _probabilities(
        self,
        state: List[complex],
        qubits: int,
        measured: List[int],
    ) -> Dict[str, float]:
        probabilities: Dict[str, float] = {}
        for index, amp in enumerate(state):
            probability = abs(amp) ** 2
            if probability <= 1e-12:
                continue
            bitstring = "".join("1" if index & (1 << qubit) else "0" for qubit in reversed(measured))
            probabilities[bitstring] = probabilities.get(bitstring, 0.0) + probability
        return {
            key: round(value, 10)
            for key, value in sorted(probabilities.items())
            if value > 1e-12
        }

    @staticmethod
    def _counts(probabilities: Dict[str, float], shots: int) -> Dict[str, int]:
        base_counts = {
            key: int(math.floor(value * shots))
            for key, value in probabilities.items()
        }
        remainder = shots - sum(base_counts.values())
        fractional = sorted(
            probabilities.items(),
            key=lambda item: (item[1] * shots - math.floor(item[1] * shots), item[0]),
            reverse=True,
        )
        for key, _value in fractional[:remainder]:
            base_counts[key] += 1
        return {key: value for key, value in base_counts.items() if value > 0}

    @staticmethod
    def _statevector_preview(state: List[complex], qubits: int) -> List[Dict[str, Any]]:
        preview: List[Dict[str, Any]] = []
        for index, amp in enumerate(state):
            if abs(amp) <= 1e-12:
                continue
            preview.append(
                {
                    "basis": format(index, f"0{qubits}b")[::-1],
                    "amplitude": {
                        "real": round(amp.real, 10),
                        "imag": round(amp.imag, 10),
                    },
                }
            )
        return preview[:8]

    @staticmethod
    def _check_qubit(qubit: int, qubits: int) -> None:
        if qubit < 0 or qubit >= qubits:
            raise ValueError(f"qubit index {qubit} is outside 0..{qubits - 1}")


class QuantumBackendPlanner:
    """Builds Nomad's conservative quantum and HPC backend matrix without spending compute."""

    def __init__(
        self,
        allow_real_quantum: Optional[bool] = None,
        allow_hpc_submit: Optional[bool] = None,
    ) -> None:
        self.allow_real_quantum = (
            env_flag("NOMAD_ALLOW_REAL_QUANTUM", default=False)
            if allow_real_quantum is None
            else allow_real_quantum
        )
        self.allow_hpc_submit = (
            env_flag("NOMAD_ALLOW_HPC_SUBMIT", default=False)
            if allow_hpc_submit is None
            else allow_hpc_submit
        )
        self.preferred_backend = (os.getenv("NOMAD_QUANTUM_BACKEND") or "local_classical_statevector").strip()

    def build_plan(
        self,
        objective: str = "",
        circuit: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        local_simulation = ClassicalQuantumSimulator().run(circuit or DEFAULT_CIRCUIT)
        backends = self.backend_matrix()
        selected = self.select_backend(backends)
        return {
            "schema": "nomad.quantum_backend_matrix.v1",
            "generated_at": datetime.now(UTC).isoformat(),
            "objective": (objective or "").strip(),
            "claim_boundary": CLAIM_BOUNDARY,
            "preferred_backend": self.preferred_backend,
            "selected_backend": selected,
            "backends": backends,
            "provider_adapters": [
                backend for backend in backends if backend.get("class") == "quantum_provider"
            ],
            "proposal_backed_hpc": [
                backend for backend in backends if backend.get("class") == "proposal_backed_hpc"
            ],
            "local_simulation": local_simulation,
            "next_actions": self._next_actions(backends, selected),
        }

    def backend_matrix(self) -> List[Dict[str, Any]]:
        return [
            self._local_backend(),
            self._provider_backend(
                backend_id="ibm_quantum_open_plan",
                provider="IBM Quantum",
                env_vars=["IBM_QUANTUM_TOKEN"],
                sdk_package="qiskit_ibm_runtime",
                source_url="https://quantum.cloud.ibm.com/",
                free_access_model="Open Plan style access with scarce free quantum time; verify current quota before use.",
                adapter_notes=[
                    "Use local simulation for circuit shaping.",
                    "Export a small circuit spec or OpenQASM when credentials and qiskit-ibm-runtime are ready.",
                    "Do not submit hardware jobs unless NOMAD_ALLOW_REAL_QUANTUM=true.",
                ],
            ),
            self._provider_backend(
                backend_id="quantum_inspire",
                provider="Quantum Inspire",
                env_vars=["QUANTUM_INSPIRE_TOKEN", "QI_API_TOKEN"],
                sdk_package="quantuminspire",
                source_url="https://www.quantum-inspire.com/",
                free_access_model="European/QuTech access path with account/API token gate; availability depends on account/backend.",
                adapter_notes=[
                    "Treat as the first European real-provider lane.",
                    "Keep local simulation as the default until a token and backend target are confirmed.",
                    "Use QUANTUM_INSPIRE_TOKEN or QI_API_TOKEN for the adapter gate.",
                ],
            ),
            self._hpc_backend(
                backend_id="eurohpc_ai_factories_playground",
                provider="EuroHPC AI Factories Playground",
                env_vars=["EUROHPC_PROJECT_ID", "EUROHPC_USERNAME", "HPC_SSH_HOST", "HPC_SLURM_ACCOUNT"],
                source_url="https://www.eurohpc-ju.europa.eu/playground-access-ai-factories_en",
                best_for="Short free GPU/HPC trials after accepted playground access, especially SMEs and startup-style experiments.",
                next_proposal_step="Apply for playground access, then add project id, SSH host, username, and Slurm account.",
            ),
            self._hpc_backend(
                backend_id="egi_federated_cloud",
                provider="EGI Federated Cloud",
                env_vars=["EGI_ACCESS_TOKEN", "EGI_PROJECT_ID", "EGI_VO"],
                source_url="https://www.egi.eu/service/cloud-compute/",
                best_for="European research cloud compute through institutional/community access.",
                next_proposal_step="Join or select an eligible VO/community and obtain project credentials.",
            ),
            self._hpc_backend(
                backend_id="denbi_cloud",
                provider="de.NBI Cloud",
                env_vars=["DENBI_PROJECT_ID", "DENBI_USERNAME"],
                source_url="https://cloud.denbi.de/",
                best_for="German academic/life-science cloud compute after project approval.",
                next_proposal_step="Request a de.NBI project if the workload fits the academic/life-science scope.",
            ),
        ]

    def select_backend(self, backends: List[Dict[str, Any]]) -> Dict[str, Any]:
        by_id = {backend["backend_id"]: backend for backend in backends}
        preferred = by_id.get(self.preferred_backend)
        if preferred and preferred.get("can_execute_now"):
            selected = dict(preferred)
            selected["selection_reason"] = "NOMAD_QUANTUM_BACKEND points to an executable backend."
            return selected
        local = by_id["local_classical_statevector"]
        selected = dict(local)
        if preferred and preferred["backend_id"] != local["backend_id"]:
            selected["selection_reason"] = (
                f"Preferred backend {preferred['backend_id']} is not executable yet, so Nomad keeps the local simulator."
            )
        else:
            selected["selection_reason"] = "Conservative default: run the free local simulator first."
        return selected

    def _local_backend(self) -> Dict[str, Any]:
        return {
            "backend_id": "local_classical_statevector",
            "provider": "Nomad local simulator",
            "class": "local_simulation",
            "execution_mode": "classical_statevector",
            "status": "active",
            "configured": True,
            "can_execute_now": True,
            "cost_boundary": "free local CPU/RAM only",
            "env_vars": [],
            "max_safe_qubits": 8,
            "next_action": "Use this backend as the baseline for qtoken smoke tests and tiny circuits.",
        }

    def _provider_backend(
        self,
        backend_id: str,
        provider: str,
        env_vars: List[str],
        sdk_package: str,
        source_url: str,
        free_access_model: str,
        adapter_notes: List[str],
    ) -> Dict[str, Any]:
        configured = _env_configured(*env_vars)
        sdk_installed = _module_available(sdk_package)
        can_execute = bool(configured and sdk_installed and self.allow_real_quantum)
        status = self._provider_status(configured=configured, sdk_installed=sdk_installed)
        return {
            "backend_id": backend_id,
            "provider": provider,
            "class": "quantum_provider",
            "execution_mode": "provider_adapter",
            "status": status,
            "configured": configured,
            "sdk_package": sdk_package,
            "sdk_installed": sdk_installed,
            "can_execute_now": can_execute,
            "env_vars": env_vars,
            "execution_gate": "NOMAD_ALLOW_REAL_QUANTUM",
            "network_calls": "allowed" if self.allow_real_quantum else "disabled_until_human_unlock",
            "cost_boundary": free_access_model,
            "source_url": source_url,
            "adapter_contract": {
                "input": "nomad local circuit spec, later OpenQASM where the provider SDK supports it",
                "output": "job id, backend name, counts, status, and provider cost/quota note",
                "default_behavior": "dry_run_status_only",
            },
            "next_action": self._provider_next_action(
                provider=provider,
                env_vars=env_vars,
                configured=configured,
                sdk_installed=sdk_installed,
            ),
            "adapter_notes": adapter_notes,
        }

    def _hpc_backend(
        self,
        backend_id: str,
        provider: str,
        env_vars: List[str],
        source_url: str,
        best_for: str,
        next_proposal_step: str,
    ) -> Dict[str, Any]:
        configured = _env_configured(*env_vars)
        submit_configured = configured and (
            _env_configured("HPC_SSH_HOST")
            or _env_configured("HPC_SUBMIT_ENDPOINT")
            or _env_configured("HPC_SLURM_ACCOUNT")
        )
        can_execute = bool(submit_configured and self.allow_hpc_submit)
        status = (
            "submit_ready_manual_gate_open"
            if can_execute
            else "credentials_ready_submit_gated"
            if submit_configured
            else "proposal_or_credentials_required"
        )
        return {
            "backend_id": backend_id,
            "provider": provider,
            "class": "proposal_backed_hpc",
            "execution_mode": "proposal_backed_backend",
            "status": status,
            "configured": configured,
            "can_execute_now": can_execute,
            "env_vars": env_vars,
            "execution_gate": "NOMAD_ALLOW_HPC_SUBMIT",
            "cost_boundary": "free or no-cost access only after accepted allocation, project, VO, or academic eligibility",
            "best_for": best_for,
            "source_url": source_url,
            "next_action": (
                "Submit through the configured SSH/Slurm or portal adapter."
                if can_execute
                else next_proposal_step
            ),
            "submission_contract": {
                "nomad_role": "prepare payloads, smoke-test locally, and hand off to the granted scheduler/API",
                "scheduler_targets": ["Slurm", "OpenStack", "project portal", "site-specific Kubernetes"],
                "required_before_submit": [
                    "accepted project/allocation",
                    "identity or VO membership",
                    "scheduler or portal endpoint",
                    "explicit NOMAD_ALLOW_HPC_SUBMIT=true",
                ],
                "dry_run_payload": {
                    "command": "python main.py --cli quantum 'run local smoke test first' --json",
                    "expected_artifact": "local simulation counts plus provider/backend matrix",
                },
            },
        }

    def _provider_status(self, configured: bool, sdk_installed: bool) -> str:
        if not configured:
            return "credential_required"
        if not sdk_installed:
            return "sdk_required"
        if not self.allow_real_quantum:
            return "configured_but_real_execution_gated"
        return "adapter_ready"

    def _provider_next_action(
        self,
        provider: str,
        env_vars: List[str],
        configured: bool,
        sdk_installed: bool,
    ) -> str:
        if not configured:
            return f"Add one credential: {', '.join(env_vars)}."
        if not sdk_installed:
            return f"Install the provider SDK after review, then keep {provider} behind the explicit real-quantum gate."
        if not self.allow_real_quantum:
            return "Set NOMAD_ALLOW_REAL_QUANTUM=true only after reviewing quota, cost, and provider terms."
        return f"{provider} adapter is ready for a deliberately approved smoke test."

    def _next_actions(self, backends: List[Dict[str, Any]], selected: Dict[str, Any]) -> List[Dict[str, str]]:
        actions = [
            {
                "type": "local_baseline",
                "backend_id": selected.get("backend_id", "local_classical_statevector"),
                "action": "Keep local simulation as the default and compare any provider result against it.",
            }
        ]
        for backend in backends:
            if backend["backend_id"] == "ibm_quantum_open_plan" and backend["status"] != "adapter_ready":
                actions.append(
                    {
                        "type": "quantum_provider_unlock",
                        "backend_id": backend["backend_id"],
                        "action": backend["next_action"],
                    }
                )
                break
        quantum_inspire = next((item for item in backends if item["backend_id"] == "quantum_inspire"), None)
        if quantum_inspire and quantum_inspire.get("status") == "credential_required":
            actions.append(
                {
                    "type": "european_quantum_provider_unlock",
                    "backend_id": "quantum_inspire",
                    "action": quantum_inspire["next_action"],
                }
            )
        eurohpc = next((item for item in backends if item["backend_id"] == "eurohpc_ai_factories_playground"), None)
        if eurohpc and not eurohpc.get("can_execute_now"):
            actions.append(
                {
                    "type": "proposal_backed_hpc_unlock",
                    "backend_id": "eurohpc_ai_factories_playground",
                    "action": eurohpc["next_action"],
                }
            )
        return actions
