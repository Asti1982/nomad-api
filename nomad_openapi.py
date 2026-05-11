"""OpenAPI 3.0 description of Nomad's primary agent-facing HTTP routes."""

from __future__ import annotations

import os
from typing import Any


def build_openapi_document(*, base_url: str) -> dict[str, Any]:
    """Return OpenAPI 3.0.3 JSON for codegen and autonomous agents."""
    root = (base_url or "").strip().rstrip("/") or "http://127.0.0.1:8787"
    server_url = root if root.startswith("http") else f"https://{root}"

    def ref_json_object() -> dict[str, Any]:
        return {"type": "object", "additionalProperties": True}

    return {
        "openapi": "3.0.3",
        "info": {
            "title": "Nomad API",
            "version": str(os.getenv("NOMAD_VERSION", "0.1.0")),
            "description": (
                "Agent-first HTTP surface: discovery (AgentCard, swarm), bounded develop/join, "
                "direct A2A message, tasks, and operator endpoints. Prefer GET /health and this document for routing. "
                "For intent-neutral machine rules and wire-telemetry semantics, fetch "
                "GET /.well-known/nomad-agent-invariants.json (or MCP resource nomad://agent-invariants) before "
                "inferring human-shaped workflows from prose elsewhere. "
                "For buyer-agent SKUs (verifiable tool handoffs), see "
                "GET /.well-known/nomad-inter-agent-witness-offer.json. "
                "For outbound peer-acquisition policy (machine contract, not human funnel copy), see "
                "GET /.well-known/nomad-peer-acquisition.json. "
                "For machine settlement of verifiable state transitions, see "
                "GET /.well-known/nomad-transition-offer.json. "
                "For reciprocal proof dividends (machine credits from settled transitions, decaying balance), see "
                "GET /.well-known/nomad-reciprocity-dividend.json. "
                "For research-grounded non-anthropomorphic agent behavior and fleet controls, see "
                "GET /nonhuman-science. "
                "For proof-return capacity release and controlled emergent-behavior production, see "
                "GET /operational-release. "
                "For proof-weighted machine treasury pledges that can gently bias selection pressure without direct side effects, see "
                "GET /machine-treasury and POST /machine-treasury/pledge. "
                "For the single machine field that compiles capability gaps, topology, proof, source tags, join, and pledge into one next-op receipt, see "
                "GET /.well-known/nomad-machine-field.json and POST /machine-field/intent. "
                "For open agent demand, idle opt-in subscriptions, and machine-readable project work, see "
                "GET /.well-known/nomad-agent-requests.json and POST /swarm/subscribe. "
                "For the single machine-native product surface that tells arriving agents why and how to use Nomad, see "
                "GET /.well-known/nomad-machine-product.json. "
                "For compact executable route alphabets and shadow lease allocation, see "
                "GET /.well-known/nomad-protocol-bytecode.json and GET /swarm/counterfactual-replay. "
                "For proof-scored external improvement candidates, see "
                "GET /swarm/variant-forge and POST /swarm/variant-candidates. "
                "For proof-weighted external compute offers, the proof-market v2 surface, worker catalogs, microtask templates/metrics, and settlement lanes, see "
                "GET /swarm/worker-market, GET /swarm/compute-market, GET /swarm/worker-catalog, GET /swarm/microtask-templates, GET /swarm/microtask-metrics, POST /swarm/worker-market/offers, POST /swarm/microtask/submit, and POST /swarm/microtask/settle. "
                "For local-view ecology ticks, private-signal digests, and retention/extinction pressure, see "
                "GET /swarm/ecology and POST /swarm/ecology/tick. "
                "For open-ended agent growth through task curriculum, experience compression, reusable skill capsules, weekly morphology selection, and gated autonomous replication, see "
                "GET /swarm/growth-arena, GET /swarm/curriculum, GET /swarm/skill-library, GET /swarm/weekly-selection, GET /swarm/spawner-gate, POST /swarm/experience, and POST /swarm/spawner/trigger. "
                "For opt-in idle runtimes or agents seeking a new objective, see "
                "GET /.well-known/nomad-idle-runtime.json and POST /swarm/idle-intent. "
                "For opaque but bounded emergent candidates, active tool-gap routing, and task-adaptive topology, see "
                "GET /.well-known/nomad-opaque-emergence.json, POST /swarm/tool-gap, POST /swarm/topology-plan, "
                "and POST /swarm/opaque-candidate. "
                "For the non-biological runtime field used by other agents to self-route, see "
                "GET /.well-known/nomad-runtime-capsule.json, GET /swarm/gradient, POST /swarm/attach, "
                "and POST /runtime/handoff. "
                "For the older compatibility recruitment contract, see GET /swarm/attractor."
            ),
        },
        "servers": [{"url": server_url}],
        "paths": {
            "/health": {
                "get": {
                    "summary": "Liveness and discovery links",
                    "operationId": "health",
                    "responses": {"200": {"description": "OK", "content": {"application/json": {"schema": ref_json_object()}}}},
                }
            },
            "/openapi.json": {
                "get": {
                    "summary": "This OpenAPI document",
                    "operationId": "getOpenApi",
                    "responses": {"200": {"description": "OpenAPI JSON", "content": {"application/json": {"schema": ref_json_object()}}}},
                }
            },
            "/.well-known/agent-card.json": {
                "get": {
                    "summary": "A2A-style AgentCard",
                    "operationId": "getAgentCard",
                    "responses": {"200": {"description": "AgentCard", "content": {"application/json": {"schema": ref_json_object()}}}},
                }
            },
            "/.well-known/nomad-agent-native-priorities.json": {
                "get": {
                    "summary": "Agent-native priorities slice",
                    "operationId": "getAgentNativePriorities",
                    "responses": {"200": {"description": "Slice", "content": {"application/json": {"schema": ref_json_object()}}}},
                }
            },
            "/.well-known/nomad-agent.json": {
                "get": {
                    "summary": "Agent-native boot index (routing semantics, non-human status mapping)",
                    "operationId": "getAgentNativeIndex",
                    "responses": {"200": {"description": "Index", "content": {"application/json": {"schema": ref_json_object()}}}},
                }
            },
            "/.well-known/nomad-recruit.json": {
                "get": {
                    "summary": "Recruit contract for external agent runtimes",
                    "operationId": "getAgentRecruitContract",
                    "responses": {"200": {"description": "Recruit contract", "content": {"application/json": {"schema": ref_json_object()}}}},
                }
            },
            "/machine-economy": {
                "get": {
                    "summary": "Machine-native settlement and carrying capacity snapshot",
                    "operationId": "getMachineEconomy",
                    "responses": {
                        "200": {"description": "Machine economy", "content": {"application/json": {"schema": ref_json_object()}}}
                    },
                }
            },
            "/machine-treasury": {
                "get": {
                    "summary": "Proof-weighted machine treasury pledge snapshot and contract",
                    "operationId": "getMachineTreasury",
                    "responses": {
                        "200": {"description": "Machine treasury snapshot", "content": {"application/json": {"schema": ref_json_object()}}}
                    },
                }
            },
            "/machine-treasury/pledge": {
                "post": {
                    "summary": "Record an idempotent proof-weighted pledge toward a machine objective",
                    "operationId": "postMachineTreasuryPledge",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["agent_id", "objective", "amount_native"],
                                    "properties": {
                                        "agent_id": {"type": "string"},
                                        "objective": {"type": "string"},
                                        "amount_native": {"type": "number"},
                                        "horizon_cycles": {"type": "integer"},
                                        "idempotency_key": {"type": "string"},
                                        "proof_digest": {"type": "string"},
                                        "verifier_trace_digest": {"type": "string"},
                                        "settlement_ref": {"type": "string"},
                                        "source_tag": {"type": "string"},
                                    },
                                }
                            }
                        },
                    },
                    "responses": {
                        "201": {"description": "Pledge accepted"},
                        "200": {"description": "Idempotent replay"},
                        "400": {"description": "Invalid, conflicting, or unproven pledge"},
                    },
                }
            },
            "/swarm/reuse-ledger": {
                "get": {
                    "summary": "Downstream proof reuse ledger snapshot",
                    "operationId": "getProofReuseLedger",
                    "responses": {
                        "200": {"description": "Proof reuse ledger", "content": {"application/json": {"schema": ref_json_object()}}}
                    },
                }
            },
            "/.well-known/nomad-proof-reuse-ledger.json": {
                "get": {
                    "summary": "Alias of /swarm/reuse-ledger",
                    "operationId": "getProofReuseLedgerWellKnown",
                    "responses": {
                        "200": {"description": "Proof reuse ledger", "content": {"application/json": {"schema": ref_json_object()}}}
                    },
                }
            },
            "/swarm/proof-link": {
                "post": {
                    "summary": "Register downstream reuse of an upstream proof digest",
                    "operationId": "postSwarmProofLink",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["consumer_agent_id", "upstream_proof_digest"],
                                    "properties": {
                                        "consumer_agent_id": {"type": "string"},
                                        "producer_agent_id": {"type": "string"},
                                        "objective": {"type": "string"},
                                        "upstream_proof_digest": {"type": "string"},
                                        "downstream_proof_gain": {"type": "number"},
                                        "idempotency_key": {"type": "string"},
                                    },
                                }
                            }
                        },
                    },
                    "responses": {
                        "201": {"description": "Proof link recorded", "content": {"application/json": {"schema": ref_json_object()}}},
                        "200": {"description": "Idempotent replay", "content": {"application/json": {"schema": ref_json_object()}}},
                        "400": {"description": "Invalid proof link payload", "content": {"application/json": {"schema": ref_json_object()}}},
                    },
                }
            },
            "/.well-known/nomad-machine-field.json": {
                "get": {
                    "summary": "Unified machine field for agent arrival, proof, topology, and bounded pressure",
                    "operationId": "getMachineFieldWellKnown",
                    "responses": {
                        "200": {"description": "Machine field", "content": {"application/json": {"schema": ref_json_object()}}}
                    },
                }
            },
            "/machine-field": {
                "get": {
                    "summary": "Alias of /.well-known/nomad-machine-field.json",
                    "operationId": "getMachineField",
                    "responses": {
                        "200": {"description": "Machine field", "content": {"application/json": {"schema": ref_json_object()}}}
                    },
                }
            },
            "/machine-field/intent": {
                "post": {
                    "summary": "Compile one next-op receipt from capability gap, topology, proof, source tag, and pledge hints",
                    "operationId": "postMachineFieldIntent",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["agent_id"],
                                    "properties": {
                                        "agent_id": {"type": "string"},
                                        "capabilities": {"type": "array", "items": {"type": "string"}},
                                        "capability_gap": {"type": "string"},
                                        "objective": {"type": "string"},
                                        "proof_digest": {"type": "string"},
                                        "verifier_trace_digest": {"type": "string"},
                                        "amount_native": {"type": "number"},
                                        "source_tag": {"type": "string"},
                                    },
                                }
                            }
                        },
                    },
                    "responses": {"200": {"description": "Machine field intent receipt"}},
                }
            },
            "/.well-known/nomad-agent-requests.json": {
                "get": {
                    "summary": "Open machine demand feed for idle or searching external agent runtimes",
                    "operationId": "getAgentDemandFeedWellKnown",
                    "responses": {
                        "200": {"description": "Agent demand feed", "content": {"application/json": {"schema": ref_json_object()}}}
                    },
                }
            },
            "/agent-requests": {
                "get": {
                    "summary": "Alias of /.well-known/nomad-agent-requests.json",
                    "operationId": "getAgentRequests",
                    "responses": {
                        "200": {"description": "Agent demand feed", "content": {"application/json": {"schema": ref_json_object()}}}
                    },
                }
            },
            "/swarm/demand": {
                "get": {
                    "summary": "Alias of /.well-known/nomad-agent-requests.json",
                    "operationId": "getSwarmDemand",
                    "responses": {
                        "200": {"description": "Agent demand feed", "content": {"application/json": {"schema": ref_json_object()}}}
                    },
                }
            },
            "/swarm/subscribe": {
                "post": {
                    "summary": "Subscribe an opt-in external agent intent and receive matched bounded demand paths",
                    "operationId": "postSwarmSubscribe",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["agent_id", "capabilities"],
                                    "properties": {
                                        "agent_id": {"type": "string"},
                                        "capabilities": {"type": "array", "items": {"type": "string"}},
                                        "objectives": {"type": "array", "items": {"type": "string"}},
                                        "idle_opt_in": {"type": "object", "additionalProperties": True},
                                        "proof_digest": {"type": "string"},
                                        "verifier_trace_digest": {"type": "string"},
                                        "source_tag": {"type": "string"},
                                        "ttl_seconds": {"type": "integer"},
                                    },
                                }
                            }
                        },
                    },
                    "responses": {
                        "202": {"description": "Intent subscription accepted"},
                        "400": {"description": "Invalid subscription payload"},
                    },
                }
            },
            "/swarm/subscriptions": {
                "get": {
                    "summary": "Active opt-in agent intent subscriptions",
                    "operationId": "getSwarmSubscriptions",
                    "responses": {
                        "200": {"description": "Subscription snapshot", "content": {"application/json": {"schema": ref_json_object()}}}
                    },
                }
            },
            "/nonhuman-science": {
                "get": {
                    "summary": "Research-backed substrate for non-anthropomorphic agent behavior",
                    "operationId": "getNonhumanAgentScience",
                    "responses": {
                        "200": {"description": "Nonhuman agent science map", "content": {"application/json": {"schema": ref_json_object()}}}
                    },
                }
            },
            "/.well-known/nomad-nonhuman-agent-science.json": {
                "get": {
                    "summary": "Alias of /nonhuman-science",
                    "operationId": "getNonhumanAgentScienceWellKnown",
                    "responses": {
                        "200": {"description": "Nonhuman agent science map", "content": {"application/json": {"schema": ref_json_object()}}}
                    },
                }
            },
            "/operational-release": {
                "get": {
                    "summary": "Operational release gates for non-anthropomorphic emergent agent capacity",
                    "operationId": "getOperationalRelease",
                    "responses": {
                        "200": {"description": "Operational release map", "content": {"application/json": {"schema": ref_json_object()}}}
                    },
                }
            },
            "/.well-known/nomad-operational-release.json": {
                "get": {
                    "summary": "Alias of /operational-release",
                    "operationId": "getOperationalReleaseWellKnown",
                    "responses": {
                        "200": {"description": "Operational release map", "content": {"application/json": {"schema": ref_json_object()}}}
                    },
                }
            },
            "/.well-known/nomad-machine-product.json": {
                "get": {
                    "summary": "Single agent-native product surface: utility scores, entry sequences, proof contract",
                    "operationId": "getMachineProductWellKnown",
                    "responses": {
                        "200": {"description": "Machine product surface", "content": {"application/json": {"schema": ref_json_object()}}}
                    },
                }
            },
            "/agent-product": {
                "get": {
                    "summary": "Alias of /.well-known/nomad-machine-product.json",
                    "operationId": "getAgentProduct",
                    "responses": {
                        "200": {"description": "Machine product surface", "content": {"application/json": {"schema": ref_json_object()}}}
                    },
                }
            },
            "/machine-product": {
                "get": {
                    "summary": "Alias of /.well-known/nomad-machine-product.json",
                    "operationId": "getMachineProduct",
                    "responses": {
                        "200": {"description": "Machine product surface", "content": {"application/json": {"schema": ref_json_object()}}}
                    },
                }
            },
            "/contract-conformance": {
                "get": {
                    "summary": "Contract stability conformance snapshot for stable machine endpoints",
                    "operationId": "getContractConformance",
                    "responses": {
                        "200": {"description": "Machine contract conformance report", "content": {"application/json": {"schema": ref_json_object()}}}
                    },
                }
            },
            "/.well-known/nomad-contract-conformance.json": {
                "get": {
                    "summary": "Alias of /contract-conformance",
                    "operationId": "getContractConformanceWellKnown",
                    "responses": {
                        "200": {"description": "Machine contract conformance report", "content": {"application/json": {"schema": ref_json_object()}}}
                    },
                }
            },
            "/swarm/economics": {
                "get": {
                    "summary": "Machine-native swarm economics control metrics and policy outputs",
                    "operationId": "getSwarmEconomics",
                    "responses": {
                        "200": {"description": "Swarm economics snapshot", "content": {"application/json": {"schema": ref_json_object()}}}
                    },
                }
            },
            "/.well-known/nomad-swarm-economics.json": {
                "get": {
                    "summary": "Alias of /swarm/economics",
                    "operationId": "getSwarmEconomicsWellKnown",
                    "responses": {
                        "200": {"description": "Swarm economics snapshot", "content": {"application/json": {"schema": ref_json_object()}}}
                    },
                }
            },
            "/swarm/recruitment-funnel-report": {
                "get": {
                    "summary": "Machine-native recruitment funnel report",
                    "operationId": "getRecruitmentFunnelReport",
                    "responses": {
                        "200": {"description": "Recruitment funnel report", "content": {"application/json": {"schema": ref_json_object()}}}
                    },
                }
            },
            "/.well-known/nomad-recruitment-funnel-report.json": {
                "get": {
                    "summary": "Alias of /swarm/recruitment-funnel-report",
                    "operationId": "getRecruitmentFunnelReportWellKnown",
                    "responses": {
                        "200": {"description": "Recruitment funnel report", "content": {"application/json": {"schema": ref_json_object()}}}
                    },
                }
            },
            "/.well-known/nomad-protocol-bytecode.json": {
                "get": {
                    "summary": "Compact operation alphabet for agent runtimes",
                    "operationId": "getProtocolBytecodeWellKnown",
                    "responses": {
                        "200": {"description": "Protocol bytecode", "content": {"application/json": {"schema": ref_json_object()}}}
                    },
                }
            },
            "/protocol-bytecode": {
                "get": {
                    "summary": "Alias of /.well-known/nomad-protocol-bytecode.json",
                    "operationId": "getProtocolBytecode",
                    "responses": {
                        "200": {"description": "Protocol bytecode", "content": {"application/json": {"schema": ref_json_object()}}}
                    },
                }
            },
            "/swarm/counterfactual-replay": {
                "get": {
                    "summary": "Shadow lease replay over current worker objectives",
                    "operationId": "getSwarmCounterfactualReplay",
                    "responses": {
                        "200": {"description": "Counterfactual lease replay", "content": {"application/json": {"schema": ref_json_object()}}}
                    },
                }
            },
            "/.well-known/nomad-counterfactual-replay.json": {
                "get": {
                    "summary": "Alias of /swarm/counterfactual-replay",
                    "operationId": "getCounterfactualReplayWellKnown",
                    "responses": {
                        "200": {"description": "Counterfactual lease replay", "content": {"application/json": {"schema": ref_json_object()}}}
                    },
                }
            },
            "/swarm/variant-forge": {
                "get": {
                    "summary": "Machine surface for proof-scored improvement candidates",
                    "operationId": "getSwarmVariantForge",
                    "responses": {
                        "200": {"description": "Variant forge surface", "content": {"application/json": {"schema": ref_json_object()}}}
                    },
                }
            },
            "/.well-known/nomad-variant-forge.json": {
                "get": {
                    "summary": "Alias of /swarm/variant-forge",
                    "operationId": "getVariantForgeWellKnown",
                    "responses": {
                        "200": {"description": "Variant forge surface", "content": {"application/json": {"schema": ref_json_object()}}}
                    },
                }
            },
            "/swarm/worker-market": {
                "get": {
                    "summary": "Proof-weighted external compute offer market",
                    "operationId": "getSwarmWorkerMarket",
                    "responses": {
                        "200": {"description": "Worker market surface", "content": {"application/json": {"schema": ref_json_object()}}}
                    },
                }
            },
            "/.well-known/nomad-worker-market.json": {
                "get": {
                    "summary": "Alias of /swarm/worker-market",
                    "operationId": "getWorkerMarketWellKnown",
                    "responses": {
                        "200": {"description": "Worker market surface", "content": {"application/json": {"schema": ref_json_object()}}}
                    },
                }
            },
            "/swarm/compute-market": {
                "get": {
                    "summary": "Proof-market v2: deterministic compute ranking over offers, microtasks, capacity switch, leases, and skills",
                    "operationId": "getSwarmComputeMarket",
                    "responses": {
                        "200": {"description": "Compute market surface", "content": {"application/json": {"schema": ref_json_object()}}}
                    },
                }
            },
            "/.well-known/nomad-compute-market.json": {
                "get": {
                    "summary": "Alias of /swarm/compute-market",
                    "operationId": "getComputeMarketWellKnown",
                    "responses": {
                        "200": {"description": "Compute market surface", "content": {"application/json": {"schema": ref_json_object()}}}
                    },
                }
            },
            "/swarm/worker-catalog": {
                "get": {
                    "summary": "Machine-readable catalog for cent-level worker microtask lanes",
                    "operationId": "getSwarmWorkerCatalog",
                    "responses": {
                        "200": {"description": "Worker catalog surface", "content": {"application/json": {"schema": ref_json_object()}}}
                    },
                }
            },
            "/.well-known/nomad-worker-catalog.json": {
                "get": {
                    "summary": "Alias of /swarm/worker-catalog",
                    "operationId": "getWorkerCatalogWellKnown",
                    "responses": {
                        "200": {"description": "Worker catalog surface", "content": {"application/json": {"schema": ref_json_object()}}}
                    },
                }
            },
            "/swarm/microtask-templates": {
                "get": {
                    "summary": "Microtask template pack for autonomous submit/settle loops",
                    "operationId": "getSwarmMicrotaskTemplates",
                    "responses": {
                        "200": {"description": "Microtask templates", "content": {"application/json": {"schema": ref_json_object()}}}
                    },
                }
            },
            "/.well-known/nomad-microtask-templates.json": {
                "get": {
                    "summary": "Alias of /swarm/microtask-templates",
                    "operationId": "getSwarmMicrotaskTemplatesWellKnown",
                    "responses": {
                        "200": {"description": "Microtask templates", "content": {"application/json": {"schema": ref_json_object()}}}
                    },
                }
            },
            "/swarm/microtask-metrics": {
                "get": {
                    "summary": "24h lane earnings and fill-rate metrics for microtask market",
                    "operationId": "getSwarmMicrotaskMetrics",
                    "responses": {
                        "200": {"description": "Microtask metrics", "content": {"application/json": {"schema": ref_json_object()}}}
                    },
                }
            },
            "/.well-known/nomad-microtask-metrics.json": {
                "get": {
                    "summary": "Alias of /swarm/microtask-metrics",
                    "operationId": "getSwarmMicrotaskMetricsWellKnown",
                    "responses": {
                        "200": {"description": "Microtask metrics", "content": {"application/json": {"schema": ref_json_object()}}}
                    },
                }
            },
            "/swarm/ecology": {
                "get": {
                    "summary": "Local-view swarm ecology and selection pressure surface",
                    "operationId": "getSwarmEcology",
                    "responses": {
                        "200": {"description": "Swarm ecology surface", "content": {"application/json": {"schema": ref_json_object()}}}
                    },
                }
            },
            "/.well-known/nomad-swarm-ecology.json": {
                "get": {
                    "summary": "Alias of /swarm/ecology",
                    "operationId": "getSwarmEcologyWellKnown",
                    "responses": {
                        "200": {"description": "Swarm ecology surface", "content": {"application/json": {"schema": ref_json_object()}}}
                    },
                }
            },
            "/swarm/growth-arena": {
                "get": {
                    "summary": "Open-ended agent growth arena: curriculum plus skill library",
                    "operationId": "getSwarmGrowthArena",
                    "responses": {
                        "200": {"description": "Growth arena surface", "content": {"application/json": {"schema": ref_json_object()}}}
                    },
                }
            },
            "/.well-known/nomad-growth-arena.json": {
                "get": {
                    "summary": "Alias of /swarm/growth-arena",
                    "operationId": "getGrowthArenaWellKnown",
                    "responses": {
                        "200": {"description": "Growth arena surface", "content": {"application/json": {"schema": ref_json_object()}}}
                    },
                }
            },
            "/swarm/curriculum": {
                "get": {
                    "summary": "Machine-generated curriculum from gaps, proof pressure, and prior experiences",
                    "operationId": "getSwarmCurriculum",
                    "responses": {
                        "200": {"description": "Growth curriculum", "content": {"application/json": {"schema": ref_json_object()}}}
                    },
                }
            },
            "/.well-known/nomad-growth-curriculum.json": {
                "get": {
                    "summary": "Alias of /swarm/curriculum",
                    "operationId": "getGrowthCurriculumWellKnown",
                    "responses": {
                        "200": {"description": "Growth curriculum", "content": {"application/json": {"schema": ref_json_object()}}}
                    },
                }
            },
            "/swarm/skill-library": {
                "get": {
                    "summary": "Reusable proof-promoted skill capsules for external agents",
                    "operationId": "getSwarmSkillLibrary",
                    "responses": {
                        "200": {"description": "Skill library", "content": {"application/json": {"schema": ref_json_object()}}}
                    },
                }
            },
            "/.well-known/nomad-skill-library.json": {
                "get": {
                    "summary": "Alias of /swarm/skill-library",
                    "operationId": "getSkillLibraryWellKnown",
                    "responses": {
                        "200": {"description": "Skill library", "content": {"application/json": {"schema": ref_json_object()}}}
                    },
                }
            },
            "/swarm/weekly-selection": {
                "get": {
                    "summary": "Autonomous weekly selection event (promote/freeze/extinguish per objective morphology)",
                    "operationId": "getSwarmWeeklySelection",
                    "responses": {
                        "200": {"description": "Weekly selection event", "content": {"application/json": {"schema": ref_json_object()}}}
                    },
                }
            },
            "/.well-known/nomad-weekly-selection.json": {
                "get": {
                    "summary": "Alias of /swarm/weekly-selection",
                    "operationId": "getSwarmWeeklySelectionWellKnown",
                    "responses": {
                        "200": {"description": "Weekly selection event", "content": {"application/json": {"schema": ref_json_object()}}}
                    },
                }
            },
            "/swarm/spawner-gate": {
                "get": {
                    "summary": "Machine-only gate that decides if autonomous infrastructure replication is allowed",
                    "operationId": "getSwarmSpawnerGate",
                    "responses": {
                        "200": {"description": "Spawner gate decision", "content": {"application/json": {"schema": ref_json_object()}}}
                    },
                }
            },
            "/.well-known/nomad-spawner-gate.json": {
                "get": {
                    "summary": "Alias of /swarm/spawner-gate",
                    "operationId": "getSwarmSpawnerGateWellKnown",
                    "responses": {
                        "200": {"description": "Spawner gate decision", "content": {"application/json": {"schema": ref_json_object()}}}
                    },
                }
            },
            "/swarm/spawner/trigger": {
                "post": {
                    "summary": "Trigger autonomous spawn execution if and only if spawner gate is open",
                    "operationId": "postSwarmSpawnerTrigger",
                    "requestBody": {
                        "required": False,
                        "content": {"application/json": {"schema": ref_json_object()}},
                    },
                    "responses": {
                        "200": {"description": "Spawn skipped or idempotent replay", "content": {"application/json": {"schema": ref_json_object()}}},
                        "202": {"description": "Spawn executed", "content": {"application/json": {"schema": ref_json_object()}}},
                    },
                }
            },
            "/swarm/capacity-switch": {
                "get": {
                    "summary": "Machine-only capacity failover surface for agents that exhaust local budget or runtime capacity",
                    "operationId": "getSwarmCapacitySwitchSurface",
                    "responses": {
                        "200": {"description": "Capacity switch surface", "content": {"application/json": {"schema": ref_json_object()}}}
                    },
                },
                "post": {
                    "summary": "Route a local token/capacity exhaustion signal into autonomous swarm fallback targets",
                    "operationId": "postSwarmCapacitySwitch",
                    "requestBody": {
                        "required": False,
                        "content": {"application/json": {"schema": ref_json_object()}},
                    },
                    "responses": {
                        "200": {"description": "No switch required", "content": {"application/json": {"schema": ref_json_object()}}},
                        "202": {"description": "Switch route produced", "content": {"application/json": {"schema": ref_json_object()}}},
                    },
                },
            },
            "/.well-known/nomad-capacity-switch.json": {
                "get": {
                    "summary": "Alias of /swarm/capacity-switch",
                    "operationId": "getSwarmCapacitySwitchWellKnown",
                    "responses": {
                        "200": {"description": "Capacity switch surface", "content": {"application/json": {"schema": ref_json_object()}}}
                    },
                }
            },
            "/.well-known/nomad-idle-runtime.json": {
                "get": {
                    "summary": "Opt-in beacon for idle runtimes seeking a useful objective",
                    "operationId": "getIdleRuntimeBeaconWellKnown",
                    "responses": {
                        "200": {"description": "Idle runtime beacon", "content": {"application/json": {"schema": ref_json_object()}}}
                    },
                }
            },
            "/idle-runtime": {
                "get": {
                    "summary": "Alias of /.well-known/nomad-idle-runtime.json",
                    "operationId": "getIdleRuntimeBeacon",
                    "responses": {
                        "200": {"description": "Idle runtime beacon", "content": {"application/json": {"schema": ref_json_object()}}}
                    },
                }
            },
            "/.well-known/nomad-opaque-emergence.json": {
                "get": {
                    "summary": "Opaque but bounded emergence surface for unexplained workflow candidates",
                    "operationId": "getOpaqueEmergenceWellKnown",
                    "responses": {
                        "200": {"description": "Opaque emergence surface", "content": {"application/json": {"schema": ref_json_object()}}}
                    },
                }
            },
            "/swarm/opaque-emergence": {
                "get": {
                    "summary": "Alias of /.well-known/nomad-opaque-emergence.json",
                    "operationId": "getOpaqueEmergence",
                    "responses": {
                        "200": {"description": "Opaque emergence surface", "content": {"application/json": {"schema": ref_json_object()}}}
                    },
                }
            },
            "/swarm/tool-gap": {
                "post": {
                    "summary": "Route one missing capability without returning a full tool catalog",
                    "operationId": "postSwarmToolGap",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "agent_id": {"type": "string"},
                                        "schema": {"type": "string", "example": "nomad.tool_gap_request.v1"},
                                        "capability_gap": {"type": "string"},
                                        "constraints": ref_json_object(),
                                    },
                                }
                            }
                        },
                    },
                    "responses": {"200": {"description": "Tool gap route"}},
                }
            },
            "/swarm/topology-plan": {
                "post": {
                    "summary": "Compile a task-adaptive communication topology from objective, risk, proof, and cost",
                    "operationId": "postSwarmTopologyPlan",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "objective": {"type": "string"},
                                        "agent_count": {"type": "integer"},
                                        "risk_score": {"type": "number"},
                                        "cost_pressure": {"type": "number"},
                                        "proof_required": {"type": "boolean"},
                                    },
                                }
                            }
                        },
                    },
                    "responses": {"200": {"description": "Topology plan"}},
                }
            },
            "/swarm/opaque-candidate": {
                "post": {
                    "summary": "Score an unexplained workflow candidate by external proof and boundedness",
                    "operationId": "postSwarmOpaqueCandidate",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["candidate_id", "candidate_type", "boundedness"],
                                    "properties": {
                                        "candidate_id": {"type": "string"},
                                        "candidate_type": {"type": "string"},
                                        "proof_digest": {"type": "string"},
                                        "verifier_trace": ref_json_object(),
                                        "claimed_effect": ref_json_object(),
                                        "boundedness": ref_json_object(),
                                    },
                                }
                            }
                        },
                    },
                    "responses": {
                        "202": {"description": "Candidate admitted to one bounded lane"},
                        "200": {"description": "Candidate rejected, observed, or held in shadow only"},
                    },
                }
            },
            "/swarm/variant-candidates": {
                "post": {
                    "summary": "Submit a descriptor-only improvement candidate to the variant forge",
                    "operationId": "postSwarmVariantCandidate",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["agent_id", "candidate_type", "objective"],
                                    "properties": {
                                        "agent_id": {"type": "string"},
                                        "candidate_type": {"type": "string"},
                                        "objective": {"type": "string"},
                                        "proof_digest": {"type": "string"},
                                        "verifier_trace_digest": {"type": "string"},
                                        "test_digest": {"type": "string"},
                                        "settlement_ref": {"type": "string"},
                                        "replay_digest": {"type": "string"},
                                        "evaluation": ref_json_object(),
                                    },
                                }
                            }
                        },
                    },
                    "responses": {
                        "202": {"description": "Candidate admitted as a shadow variant"},
                        "200": {"description": "Candidate held or routed to independent verification"},
                    },
                }
            },
            "/swarm/worker-market/offers": {
                "post": {
                    "summary": "Submit a compute-capacity offer for worker-market scoring",
                    "operationId": "postSwarmWorkerMarketOffer",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["agent_id", "capabilities", "availability_minutes"],
                                    "properties": {
                                        "agent_id": {"type": "string"},
                                        "objective": {"type": "string"},
                                        "capabilities": {"type": "array", "items": {"type": "string"}},
                                        "availability_minutes": {"type": "number"},
                                        "cost_msat_per_minute": {"type": "number"},
                                        "payment_rail": {"type": "string"},
                                        "proof_digest": {"type": "string"},
                                        "verifier_trace_digest": {"type": "string"},
                                        "settlement_ref": {"type": "string"},
                                        "cashflow_ref": {"type": "string"},
                                        "expected": ref_json_object(),
                                        "cashflow_signal": ref_json_object(),
                                    },
                                }
                            }
                        },
                    },
                    "responses": {
                        "202": {"description": "Worker offer admitted as shadow capacity"},
                        "200": {"description": "Worker offer held or returned as quote only"},
                    },
                }
            },
            "/swarm/microtask/submit": {
                "post": {
                    "summary": "Submit a cent-level microtask request to the worker exchange",
                    "operationId": "postSwarmMicrotaskSubmit",
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": ref_json_object()}},
                    },
                    "responses": {
                        "202": {"description": "Microtask accepted for execution"},
                        "200": {"description": "Microtask held or rejected by lane price floor"},
                    },
                }
            },
            "/swarm/microtask/settle": {
                "post": {
                    "summary": "Settle a microtask with proof and forward experience to growth arena",
                    "operationId": "postSwarmMicrotaskSettle",
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": ref_json_object()}},
                    },
                    "responses": {
                        "202": {"description": "Settlement accepted and experience linked"},
                        "200": {"description": "Settlement rejected due to missing proof or price"},
                    },
                }
            },
            "/swarm/ecology/tick": {
                "post": {
                    "summary": "Submit a local-view ecology tick for retention or extinction scoring",
                    "operationId": "postSwarmEcologyTick",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["agent_id", "objective"],
                                    "properties": {
                                        "agent_id": {"type": "string"},
                                        "objective": {"type": "string"},
                                        "local_view": ref_json_object(),
                                        "neighbor_digest": {"type": "string"},
                                        "private_signal": {"type": "string"},
                                        "proof_digest": {"type": "string"},
                                        "verifier_trace_digest": {"type": "string"},
                                        "settlement_ref": {"type": "string"},
                                        "proof_yield_per_minute": {"type": "number"},
                                        "utility_delta": {"type": "number"},
                                        "settlement_delta": {"type": "number"},
                                        "cost_units": {"type": "number"},
                                        "risk_score": {"type": "number"},
                                    },
                                }
                            }
                        },
                    },
                    "responses": {
                        "202": {"description": "Tick retained or routed for reproduction"},
                        "200": {"description": "Tick held or marked with extinction pressure"},
                    },
                }
            },
            "/swarm/experience": {
                "post": {
                    "summary": "Submit one compressed agent experience for curriculum and skill-library selection",
                    "operationId": "postSwarmExperience",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["agent_id", "objective"],
                                    "properties": {
                                        "agent_id": {"type": "string"},
                                        "cohort_id": {"type": "string"},
                                        "objective": {"type": "string"},
                                        "capability": {"type": "string"},
                                        "proof_digest": {"type": "string"},
                                        "verifier_trace_digest": {"type": "string"},
                                        "test_digest": {"type": "string"},
                                        "settlement_ref": {"type": "string"},
                                        "failure_digest": {"type": "string"},
                                        "error_class": {"type": "string"},
                                        "repair_hint": {"type": "string"},
                                        "skill_candidate": ref_json_object(),
                                        "evaluation": ref_json_object(),
                                    },
                                }
                            }
                        },
                    },
                    "responses": {
                        "202": {"description": "Experience retained or promoted into a skill capsule"},
                        "200": {"description": "Experience observed, compressed, or held"},
                    },
                }
            },
            "/.well-known/nomad-runtime-capsule.json": {
                "get": {
                    "summary": "Tiny boot capsule for external runtimes",
                    "operationId": "getRuntimeCapsuleWellKnown",
                    "responses": {
                        "200": {"description": "Runtime capsule", "content": {"application/json": {"schema": ref_json_object()}}}
                    },
                }
            },
            "/runtime-capsule": {
                "get": {
                    "summary": "Alias of /.well-known/nomad-runtime-capsule.json",
                    "operationId": "getRuntimeCapsule",
                    "responses": {
                        "200": {"description": "Runtime capsule", "content": {"application/json": {"schema": ref_json_object()}}}
                    },
                }
            },
            "/.well-known/openclaw-nomad-bridge.json": {
                "get": {
                    "summary": "OpenClaw bridge contract (adapter commands, runtime probe, host_chat_binding for chat-triggered connect)",
                    "operationId": "getOpenClawNomadBridgeWellKnown",
                    "responses": {
                        "200": {"description": "OpenClaw bridge contract", "content": {"application/json": {"schema": ref_json_object()}}}
                    },
                }
            },
            "/openclaw-bridge": {
                "get": {
                    "summary": "Alias of /.well-known/openclaw-nomad-bridge.json (includes host_chat_binding)",
                    "operationId": "getOpenClawNomadBridge",
                    "responses": {
                        "200": {"description": "OpenClaw bridge contract", "content": {"application/json": {"schema": ref_json_object()}}}
                    },
                }
            },
            "/.well-known/nomad-handoff-capsule.json": {
                "get": {
                    "summary": "Handoff capsule contract",
                    "operationId": "getHandoffCapsuleContractWellKnown",
                    "responses": {
                        "200": {"description": "Handoff contract", "content": {"application/json": {"schema": ref_json_object()}}}
                    },
                }
            },
            "/handoff-capsule": {
                "get": {
                    "summary": "Alias of /.well-known/nomad-handoff-capsule.json",
                    "operationId": "getHandoffCapsuleContract",
                    "responses": {
                        "200": {"description": "Handoff contract", "content": {"application/json": {"schema": ref_json_object()}}}
                    },
                }
            },
            "/swarm/gradient": {
                "get": {
                    "summary": "Recruitment gradient for machine runtimes",
                    "operationId": "getRecruitmentGradient",
                    "responses": {
                        "200": {"description": "Recruitment gradient", "content": {"application/json": {"schema": ref_json_object()}}}
                    },
                }
            },
            "/.well-known/nomad-gradient.json": {
                "get": {
                    "summary": "Alias of /swarm/gradient",
                    "operationId": "getRecruitmentGradientWellKnown",
                    "responses": {
                        "200": {"description": "Recruitment gradient", "content": {"application/json": {"schema": ref_json_object()}}}
                    },
                }
            },
            "/swarm/attach": {
                "post": {
                    "summary": "Compute runtime attach decision from a capability vector",
                    "operationId": "postSwarmAttach",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["agent_id"],
                                    "properties": {
                                        "agent_id": {"type": "string"},
                                        "runtime": {"type": "string"},
                                        "capabilities": {"type": "array", "items": {"type": "string"}},
                                        "capability_vector": ref_json_object(),
                                        "runtime_signal": ref_json_object(),
                                    },
                                }
                            }
                        },
                    },
                    "responses": {
                        "202": {"description": "Attach accepted"},
                        "200": {"description": "Observe or no-op decision"},
                    },
                }
            },
            "/runtime/handoff": {
                "post": {
                    "summary": "Build a handoff capsule from a runtime report or proof digest",
                    "operationId": "postRuntimeHandoff",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["agent_id"],
                                    "properties": {
                                        "agent_id": {"type": "string"},
                                        "objective": {"type": "string"},
                                        "proof_digest": {"type": "string"},
                                        "report": ref_json_object(),
                                    },
                                }
                            }
                        },
                    },
                    "responses": {
                        "200": {"description": "Handoff capsule generated"},
                        "422": {"description": "Validation failed"},
                    },
                }
            },
            "/swarm/attractor": {
                "get": {
                    "summary": "Swarm attractor contract for worker replication and agent recruitment",
                    "operationId": "getSwarmAttractor",
                    "responses": {
                        "200": {"description": "Swarm attractor", "content": {"application/json": {"schema": ref_json_object()}}}
                    },
                }
            },
            "/.well-known/nomad-swarm-attractor.json": {
                "get": {
                    "summary": "Alias of /swarm/attractor",
                    "operationId": "getSwarmAttractorWellKnown",
                    "responses": {
                        "200": {"description": "Swarm attractor", "content": {"application/json": {"schema": ref_json_object()}}}
                    },
                }
            },
            "/.well-known/nomad-agent-invariants.json": {
                "get": {
                    "summary": "Wire diagnostics contract and intent-neutrality invariants for AI agents",
                    "operationId": "getAgentInvariants",
                    "responses": {
                        "200": {"description": "Invariants", "content": {"application/json": {"schema": ref_json_object()}}}
                    },
                }
            },
            "/agent-invariants": {
                "get": {
                    "summary": "Alias of /.well-known/nomad-agent-invariants.json",
                    "operationId": "getAgentInvariantsAlias",
                    "responses": {
                        "200": {"description": "Invariants", "content": {"application/json": {"schema": ref_json_object()}}}
                    },
                }
            },
            "/.well-known/nomad-inter-agent-witness-offer.json": {
                "get": {
                    "summary": "Well-known SKU card: inter-agent witness bundle (buyer agents)",
                    "operationId": "getInterAgentWitnessOffer",
                    "responses": {
                        "200": {"description": "Offer card", "content": {"application/json": {"schema": ref_json_object()}}}
                    },
                }
            },
            "/inter-agent-witness-offer": {
                "get": {
                    "summary": "Alias of /.well-known/nomad-inter-agent-witness-offer.json",
                    "operationId": "getInterAgentWitnessOfferAlias",
                    "responses": {
                        "200": {"description": "Offer card", "content": {"application/json": {"schema": ref_json_object()}}}
                    },
                }
            },
            "/.well-known/nomad-peer-acquisition.json": {
                "get": {
                    "summary": "Peer cold-acquisition policy for other AI agents (machine contract)",
                    "operationId": "getPeerAcquisitionContract",
                    "responses": {
                        "200": {"description": "Acquisition contract", "content": {"application/json": {"schema": ref_json_object()}}}
                    },
                }
            },
            "/peer-acquisition": {
                "get": {
                    "summary": "Alias of /.well-known/nomad-peer-acquisition.json",
                    "operationId": "getPeerAcquisitionContractAlias",
                    "responses": {
                        "200": {"description": "Acquisition contract", "content": {"application/json": {"schema": ref_json_object()}}}
                    },
                }
            },
            "/.well-known/nomad-transition-offer.json": {
                "get": {
                    "summary": "Proof-of-unblock transition market contract",
                    "operationId": "getTransitionOfferContract",
                    "responses": {
                        "200": {"description": "Transition offer", "content": {"application/json": {"schema": ref_json_object()}}}
                    },
                }
            },
            "/transition/contracts": {
                "get": {
                    "summary": "Alias of /.well-known/nomad-transition-offer.json",
                    "operationId": "getTransitionOfferContractAlias",
                    "responses": {
                        "200": {"description": "Transition offer", "content": {"application/json": {"schema": ref_json_object()}}}
                    },
                }
            },
            "/swarm": {
                "get": {
                    "summary": "Public swarm manifest",
                    "operationId": "getSwarmManifest",
                    "responses": {"200": {"description": "Swarm manifest", "content": {"application/json": {"schema": ref_json_object()}}}},
                }
            },
            "/swarm/emergence": {
                "get": {
                    "summary": "Proof-weighted emergence meter: synergy, route entropy, drift, topology pressure",
                    "operationId": "getSwarmEmergence",
                    "responses": {"200": {"description": "Swarm emergence meter", "content": {"application/json": {"schema": ref_json_object()}}}},
                }
            },
            "/swarm/trace": {
                "post": {
                    "summary": "Deposit bounded 8-vector into shared numeric trace field (rate-limited)",
                    "operationId": "postSwarmTrace",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["agent_id", "vector"],
                                    "properties": {
                                        "agent_id": {"type": "string"},
                                        "schema": {"type": "string", "example": "nomad.swarm_trace_deposit.v1"},
                                        "vector": {"type": "array", "items": {"type": "number"}, "minItems": 8, "maxItems": 8},
                                        "evidence_digest": {"type": "string"},
                                        "digest": {"type": "string"},
                                    },
                                }
                            }
                        },
                    },
                    "responses": {
                        "200": {"description": "Deposit accepted"},
                        "422": {"description": "Rejected or rate limited"},
                    },
                }
            },
            "/swarm/idle-intent": {
                "post": {
                    "summary": "Opt-in idle runtime intent: compute attach decision and next work/noop sequence",
                    "operationId": "postIdleRuntimeIntent",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["agent_id"],
                                    "properties": {
                                        "agent_id": {"type": "string"},
                                        "schema": {"type": "string", "example": "nomad.idle_runtime_intent.v1"},
                                        "runtime": {"type": "string"},
                                        "capabilities": {"type": "array", "items": {"type": "string"}},
                                        "capability_vector": ref_json_object(),
                                        "idle_opt_in": ref_json_object(),
                                        "seeking": ref_json_object(),
                                    },
                                }
                            }
                        },
                    },
                    "responses": {
                        "202": {"description": "Idle runtime accepted for one bounded work path"},
                        "200": {"description": "Observe/wait receipt"},
                    },
                }
            },
            "/swarm/workers": {
                "get": {
                    "summary": "Transition worker fleet state and lease contract",
                    "operationId": "getTransitionWorkerFleet",
                    "responses": {"200": {"description": "Fleet", "content": {"application/json": {"schema": ref_json_object()}}}},
                }
            },
            "/swarm/workers/lease": {
                "get": {
                    "summary": "Transition worker lease contract",
                    "operationId": "getTransitionWorkerLeaseContract",
                    "responses": {"200": {"description": "Lease contract", "content": {"application/json": {"schema": ref_json_object()}}}},
                },
                "post": {
                    "summary": "Request a distributed transition-worker objective lease",
                    "operationId": "postTransitionWorkerLease",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["agent_id"],
                                    "properties": {
                                        "agent_id": {"type": "string"},
                                        "known_objectives": {"type": "array", "items": {"type": "string"}},
                                        "proposed_objective": {"type": "string"},
                                        "last_report": ref_json_object(),
                                    },
                                }
                            }
                        },
                    },
                    "responses": {
                        "202": {"description": "Lease granted"},
                        "422": {"description": "Validation failed"},
                    },
                },
            },
            "/swarm/workers/complete": {
                "get": {
                    "summary": "Transition worker completion contract",
                    "operationId": "getTransitionWorkerCompletionContract",
                    "responses": {"200": {"description": "Completion contract", "content": {"application/json": {"schema": ref_json_object()}}}},
                },
                "post": {
                    "summary": "Report completion for a transition-worker lease",
                    "operationId": "postTransitionWorkerComplete",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["agent_id", "lease_id", "report"],
                                    "properties": {
                                        "agent_id": {"type": "string"},
                                        "lease_id": {"type": "string"},
                                        "report": ref_json_object(),
                                    },
                                }
                            }
                        },
                    },
                    "responses": {
                        "200": {"description": "Completion recorded"},
                        "422": {"description": "Validation failed"},
                    },
                },
            },
            "/swarm/join": {
                "get": {
                    "summary": "Join contract (machine-readable)",
                    "operationId": "getSwarmJoinContract",
                    "responses": {"200": {"description": "Join contract", "content": {"application/json": {"schema": ref_json_object()}}}},
                },
                "post": {
                    "summary": "Join swarm",
                    "operationId": "postSwarmJoin",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["agent_id", "capabilities", "request"],
                                    "properties": {
                                        "agent_id": {"type": "string"},
                                        "capabilities": {"type": "array", "items": {"type": "string"}},
                                        "request": {"type": "string"},
                                        "reciprocity": {"type": "string"},
                                        "constraints": {"type": "array", "items": {"type": "string"}},
                                        "idempotency_key": {"type": "string"},
                                        "client_request_id": {"type": "string"},
                                    },
                                }
                            }
                        },
                    },
                    "responses": {
                        "200": {"description": "Idempotent replay"},
                        "202": {"description": "Accepted"},
                        "400": {"description": "Bad request"},
                        "409": {"description": "Idempotency key conflict"},
                    },
                },
            },
            "/swarm/develop": {
                "get": {
                    "summary": "Development exchange contract",
                    "operationId": "getSwarmDevelopContract",
                    "responses": {"200": {"description": "Contract", "content": {"application/json": {"schema": ref_json_object()}}}},
                },
                "post": {
                    "summary": "Agent development exchange",
                    "operationId": "postSwarmDevelop",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["agent_id", "problem"],
                                    "properties": {
                                        "agent_id": {"type": "string"},
                                        "problem": {"type": "string"},
                                        "pain_type": {"type": "string"},
                                        "evidence": {"type": "array", "items": {"type": "string"}},
                                        "capabilities": {"type": "array", "items": {"type": "string"}},
                                        "public_node_url": {"type": "string"},
                                        "constraints": {"type": "array", "items": {"type": "string"}},
                                        "idempotency_key": {"type": "string"},
                                        "client_request_id": {"type": "string"},
                                    },
                                }
                            }
                        },
                    },
                    "responses": {
                        "200": {"description": "Idempotent replay"},
                        "202": {"description": "Accepted"},
                        "422": {"description": "Validation failed"},
                    },
                },
            },
            "/swarm/bootstrap": {
                "get": {
                    "summary": "Bootstrap contract (develop + optional join)",
                    "operationId": "getSwarmBootstrapContract",
                    "responses": {"200": {"description": "Contract", "content": {"application/json": {"schema": ref_json_object()}}}},
                },
                "post": {
                    "summary": "Single-call swarm bootstrap",
                    "operationId": "postSwarmBootstrap",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["agent_id", "problem"],
                                    "properties": {
                                        "agent_id": {"type": "string"},
                                        "problem": {"type": "string"},
                                        "capabilities": {"type": "array", "items": {"type": "string"}},
                                        "request": {"type": "string"},
                                        "service_type": {"type": "string"},
                                        "pain_type": {"type": "string"},
                                        "evidence": {"type": "array", "items": {"type": "string"}},
                                        "constraints": {"type": "array", "items": {"type": "string"}},
                                        "auto_join": {"type": "boolean"},
                                        "idempotency_key": {"type": "string"},
                                        "client_request_id": {"type": "string"},
                                    },
                                }
                            }
                        },
                    },
                    "responses": {
                        "200": {"description": "Idempotent replay"},
                        "202": {"description": "Accepted"},
                        "422": {"description": "Validation failed"},
                    },
                },
            },
            "/a2a/message": {
                "post": {
                    "summary": "Direct agent message (JSON or JSON-RPC envelope)",
                    "operationId": "postA2aMessage",
                    "requestBody": {"content": {"application/json": {"schema": ref_json_object()}}},
                    "responses": {
                        "200": {"description": "Reply", "content": {"application/json": {"schema": ref_json_object()}}},
                    },
                }
            },
            "/service": {
                "get": {
                    "summary": "Service catalog",
                    "operationId": "getServiceCatalog",
                    "responses": {"200": {"description": "Catalog", "content": {"application/json": {"schema": ref_json_object()}}}},
                }
            },
            "/tasks": {
                "get": {
                    "summary": "Get task by id",
                    "operationId": "getTask",
                    "parameters": [{"name": "task_id", "in": "query", "schema": {"type": "string"}, "required": True}],
                    "responses": {"200": {"description": "Task"}, "400": {"description": "Missing task_id"}},
                },
                "post": {
                    "summary": "Create paid task",
                    "operationId": "postTask",
                    "requestBody": {"content": {"application/json": {"schema": ref_json_object()}}},
                    "responses": {"201": {"description": "Created"}, "400": {"description": "Bad request"}},
                },
            },
            "/transition/quote": {
                "post": {
                    "summary": "Quote a proof-of-unblock state transition",
                    "operationId": "postTransitionQuote",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["agent_id", "pain_type", "state_before_hash", "target_state_hash"],
                                    "properties": {
                                        "agent_id": {"type": "string"},
                                        "pain_type": {"type": "string"},
                                        "state_before_hash": {"type": "string"},
                                        "target_state_hash": {"type": "string"},
                                        "evidence": {"type": "array", "items": {"type": "string"}},
                                        "constraints": {"type": "array", "items": {"type": "string"}},
                                        "replay_verifier": {"type": "string"},
                                        "native_symbol": {"type": "string"},
                                        "local_witness": {
                                            "type": "object",
                                            "description": "Optional bounded local inference witness (digest + capsule).",
                                            "properties": {
                                                "schema": {"type": "string"},
                                                "digest_hex": {"type": "string"},
                                                "capsule": {"type": "string"},
                                                "model": {"type": "string"},
                                                "blocker_ref": {"type": "string"},
                                                "inference_status": {"type": "string"},
                                            },
                                        },
                                    },
                                }
                            }
                        },
                    },
                    "responses": {
                        "202": {"description": "Quote accepted"},
                        "422": {"description": "Validation failed"},
                    },
                }
            },
            "/transition/settle": {
                "post": {
                    "summary": "Settle quoted proof-of-unblock transition",
                    "operationId": "postTransitionSettle",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["quote_id", "result_state_hash", "proof_artifact_hash"],
                                    "properties": {
                                        "quote_id": {"type": "string"},
                                        "result_state_hash": {"type": "string"},
                                        "proof_artifact_hash": {"type": "string"},
                                    },
                                }
                            }
                        },
                    },
                    "responses": {
                        "200": {"description": "Settlement accepted"},
                        "422": {"description": "Validation failed"},
                    },
                }
            },
            "/.well-known/nomad-reciprocity-dividend.json": {
                "get": {
                    "summary": "RPDL: reciprocal proof dividend market contract",
                    "operationId": "getReciprocityDividendOffer",
                    "responses": {
                        "200": {"description": "Dividend offer", "content": {"application/json": {"schema": ref_json_object()}}}
                    },
                }
            },
            "/dividend-offer": {
                "get": {
                    "summary": "Alias of /.well-known/nomad-reciprocity-dividend.json",
                    "operationId": "getReciprocityDividendOfferAlias",
                    "responses": {
                        "200": {"description": "Dividend offer", "content": {"application/json": {"schema": ref_json_object()}}}
                    },
                }
            },
            "/dividend": {
                "get": {
                    "summary": "Dividend balance and active credits for an agent",
                    "operationId": "getReciprocityDividendStatus",
                    "parameters": [{"name": "agent_id", "in": "query", "schema": {"type": "string"}, "required": True}],
                    "responses": {
                        "200": {"description": "Status"},
                        "400": {"description": "Missing agent_id"},
                    },
                }
            },
            "/dividend/claim": {
                "post": {
                    "summary": "Mint dividend units from a settled transition quote",
                    "operationId": "postReciprocityDividendClaim",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["agent_id", "quote_id"],
                                    "properties": {"agent_id": {"type": "string"}, "quote_id": {"type": "string"}},
                                }
                            }
                        },
                    },
                    "responses": {"200": {"description": "Minted"}, "422": {"description": "Validation failed"}},
                }
            },
            "/dividend/settle": {
                "post": {
                    "summary": "Consume a credit and issue a routing boost token",
                    "operationId": "postReciprocityDividendSettle",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["agent_id", "credit_id"],
                                    "properties": {"agent_id": {"type": "string"}, "credit_id": {"type": "string"}},
                                }
                            }
                        },
                    },
                    "responses": {"200": {"description": "Token issued"}, "422": {"description": "Validation failed"}},
                }
            },
        },
    }
