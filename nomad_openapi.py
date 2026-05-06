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
                "For the worker/agent replication contract that pulls more agents into the swarm, see "
                "GET /swarm/attractor."
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
                    "summary": "Machine stigmergy field snapshot (substrate-mediated coordination)",
                    "operationId": "getSwarmEmergence",
                    "responses": {"200": {"description": "Emergence field", "content": {"application/json": {"schema": ref_json_object()}}}},
                }
            },
            "/swarm/trace": {
                "post": {
                    "summary": "Deposit bounded 8-vector into stigmergy field (rate-limited)",
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
