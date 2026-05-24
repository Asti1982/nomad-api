from nomad_machine_native_collaboration import build_machine_native_collaboration_surface


def test_machine_native_collaboration_surface_sets_boundaries():
    surface = build_machine_native_collaboration_surface(base_url="https://nomad.example")

    assert surface["schema"] == "nomad.machine_native_collaboration.v1"
    assert surface["well_known_url"] == "https://nomad.example/.well-known/nomad-machine-native-collaboration.json"
    assert surface["core_thesis"]["human_forms"] == "compatibility_layer_not_primary_design_source"
    assert surface["core_thesis"]["accounting_boundary"] == "paid_or_verified_return_compute_receipt_required"
    assert surface["revenue_path"]["receipt_rule"] == "do_not_count_as_revenue_until_paid_or_verified_return_compute_receipt"
    assert "public_comments" in surface["human_audit_membrane"]["required_for"]
    assert "ledger_attribution_with_counts_as_revenue_false" in surface["human_audit_membrane"]["not_required_for"]
    assert any(
        row["human_form"] == "consulting_proposal"
        and row["machine_native_replacement"] == "bounded_rescue_packet_with_price_tier_and_receipt_rule"
        for row in surface["collaboration_inversion"]
    )
    assert any(
        mechanism["mechanism"] == "rescue_cycle_schedule"
        and mechanism["route"] == "https://nomad.example/.well-known/nomad-rescue-cycle-scheduler.json"
        for mechanism in surface["why_this_can_attract_agents_and_workers"]
    )
    assert any(
        mechanism["mechanism"] == "rescue_packet_lattice"
        and mechanism["route"] == "https://nomad.example/.well-known/nomad-rescue-packet-lattice.json"
        for mechanism in surface["why_this_can_attract_agents_and_workers"]
    )
