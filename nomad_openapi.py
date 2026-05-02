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
                "direct A2A message, tasks, and operator endpoints. Prefer GET /health and this document for routing."
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
            "/swarm": {
                "get": {
                    "summary": "Public swarm manifest",
                    "operationId": "getSwarmManifest",
                    "responses": {"200": {"description": "Swarm manifest", "content": {"application/json": {"schema": ref_json_object()}}}},
                }
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
        },
    }
