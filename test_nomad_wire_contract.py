from nomad_wire_contract import (
    attach_wire_diag,
    build_http_wire_diag,
    build_mcp_tool_wire_diag,
    maybe_merge_http_wire_diag,
    routing_hash_from_tool_names,
    stateful_context_audit_missing,
)


def test_routing_hash_stable_for_same_catalog():
    h1 = routing_hash_from_tool_names(["nomad_best", "nomad_self_audit"])
    h2 = routing_hash_from_tool_names(["nomad_self_audit", "nomad_best"])
    assert h1 == h2
    assert len(h1) == 16


def test_routing_hash_changes_when_tool_set_changes():
    a = routing_hash_from_tool_names(["a", "b"])
    b = routing_hash_from_tool_names(["a", "b", "c"])
    assert a != b


def test_stateful_audit_flags_missing_correlation():
    missing = stateful_context_audit_missing(
        "nomad_agent_contact_send",
        {"problem": "x"},
    )
    assert "correlation_id" in missing
    assert "tenant_id" in missing


def test_stateful_audit_clear_when_keys_present():
    missing = stateful_context_audit_missing(
        "nomad_agent_contact_send",
        {"tenant_id": "t1", "correlation_id": "c7"},
    )
    assert missing == []


def test_build_mcp_tool_wire_diag_shape():
    diag = build_mcp_tool_wire_diag(
        tool_name="nomad_best",
        arguments={"profile": "ai_first"},
        routing_table_hash="abcd" * 4,
        tool_catalog_names=["nomad_best", "nomad_self_audit"],
    )
    assert diag["schema"] == "nomad.mcp_wire_diag.v1"
    assert diag["transport_channel"] == "mcp_call"
    assert diag["routing_table_hash"] == "abcd" * 4
    assert diag["tool_catalog_size"] == 2
    assert "argument_keys" in diag["context_envelope"]
    assert diag["parity_hint"]["note"]


def test_attach_wire_diag_merges_dict():
    out = attach_wire_diag({"mode": "x", "ok": True}, {"schema": "nomad.mcp_wire_diag.v1"})
    assert out["mode"] == "x"
    assert out["nomad_wire_diag"]["schema"] == "nomad.mcp_wire_diag.v1"


def test_build_http_wire_diag_detects_correlation_header():
    diag = build_http_wire_diag(
        method="POST",
        path="/leads",
        headers={"X-Correlation-ID": "abc-123", "Content-Type": "application/json"},
    )
    assert diag["transport_channel"] == "http"
    assert diag["http_method"] == "POST"
    assert diag["path"] == "/leads"
    assert diag["header_signals"]["correlation_header"] is True


def test_maybe_merge_http_wire_diag_skips_openapi_path():
    class H:
        path = "/openapi.json?foo=1"
        command = "GET"
        headers = {}

    out = maybe_merge_http_wire_diag(H(), {"openapi": "3.0.3"})
    assert "nomad_wire_diag" not in out


def test_maybe_merge_http_wire_diag_skips_agent_invariants():
    class H:
        path = "/.well-known/nomad-agent-invariants.json"
        command = "GET"
        headers = {}

    out = maybe_merge_http_wire_diag(H(), {"schema": "nomad.agent_invariants.v1"})
    assert "nomad_wire_diag" not in out


def test_maybe_merge_http_wire_diag_merges_health(monkeypatch):
    monkeypatch.setenv("NOMAD_HTTP_WIRE_DIAG", "1")

    class H:
        path = "/health"
        command = "GET"
        headers = {}

    out = maybe_merge_http_wire_diag(H(), {"ok": True, "schema": "nomad.health.v1"})
    assert out["ok"] is True
    assert out["nomad_wire_diag"]["transport_channel"] == "http"


def test_maybe_merge_http_wire_diag_disabled(monkeypatch):
    monkeypatch.setenv("NOMAD_HTTP_WIRE_DIAG", "0")

    class H:
        path = "/health"
        command = "GET"
        headers = {}

    out = maybe_merge_http_wire_diag(H(), {"ok": True})
    assert "nomad_wire_diag" not in out


def test_mcp_strict_context_rejects_stateful_without_correlation(monkeypatch):
    monkeypatch.setenv("NOMAD_MCP_STRICT_CONTEXT", "1")
    from nomad_mcp import NomadMcpServer

    class FakeAgent:
        pass

    server = NomadMcpServer(agent_factory=lambda: FakeAgent())
    resp = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "nomad_agent_contact_send", "arguments": {"contact_id": "c1"}},
        }
    )
    body = resp["result"]["structuredContent"]
    assert resp["result"]["isError"] is True
    assert body.get("error") == "context_envelope_reject"
    assert "correlation_id" in (body.get("missing_context_keys") or [])
    assert body.get("nomad_wire_diag", {}).get("tool_name") == "nomad_agent_contact_send"
