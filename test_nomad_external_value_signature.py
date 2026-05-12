from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat, PublicFormat

from nomad_external_value_signature import sign_external_value_proof, verify_external_value_signed_proof


def _write_test_wallet(path):
    key = Ed25519PrivateKey.generate()
    private_bytes = key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
    public_bytes = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    path.write_text(
        (
            "{"
            '"private_key_storage":"test_plaintext_only",'
            f'"private_key_hex":"{private_bytes.hex()}",'
            f'"public_key_hex":"{public_bytes.hex()}"'
            "}"
        ),
        encoding="utf-8",
    )


def test_sign_and_verify_external_value_proof_with_test_wallet(tmp_path):
    wallet = tmp_path / "wallet.json"
    _write_test_wallet(wallet)

    out = sign_external_value_proof(
        agent_id="nomad-worker-codex",
        external_id="gh_review:owner/repo#1",
        stage="submitted",
        work_url="https://github.com/owner/repo/pull/1#pullrequestreview-1",
        proof_digest="sha256:abc",
        verifier_trace_digest="sha256:def",
        payout_ref="RTCaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        wallet_path=wallet,
    )

    assert out["schema"] == "nomad.external_value_signed_proof.v1"
    assert out["secret_material_present"] is False
    assert out["signature_hex"]
    assert verify_external_value_signed_proof(out)["ok"] is True


def test_cli_external_value_sign_proof(tmp_path):
    from nomad_cli import run_once

    wallet = tmp_path / "wallet.json"
    _write_test_wallet(wallet)

    out = run_once(
        [
            "external-value",
            "sign-proof",
            "--agent-id",
            "nomad-worker-codex",
            "--external-id",
            "gh_review:owner/repo#1",
            "--stage",
            "submitted",
            "--work-url",
            "https://github.com/owner/repo/pull/1#pullrequestreview-1",
            "--proof-digest",
            "sha256:abc",
            "--verifier-trace-digest",
            "sha256:def",
            "--payout-ref",
            "RTCaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "--wallet-path",
            str(wallet),
            "--json",
        ]
    )

    assert out["schema"] == "nomad.external_value_signed_proof.v1"
    assert out["verification"]["ok"] is True
