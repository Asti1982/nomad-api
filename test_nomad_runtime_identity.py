from nomad_runtime_identity import NodeIdentity


def test_node_identity_signs_and_verifies_bundle():
    bundle = {
        "schema": "nomad.roaas_bundle.v1",
        "task_type": "self_improvement_review",
        "total_patterns": 1,
        "patterns": [],
    }
    signer = NodeIdentity(node_name="node-a", shared_secret="shared-secret", public_base_url="http://node-a.local")
    verifier = NodeIdentity(node_name="node-b", shared_secret="shared-secret", public_base_url="http://node-b.local")

    envelope = signer.sign_bundle(bundle)
    verification = verifier.verify_envelope(envelope)

    assert envelope["signature"]
    assert verification["signature_valid"] is True
    assert verification["reason"] == "signature_verified"
    assert verification["trust_score"] >= 0.75
