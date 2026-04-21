from compute_probe import LocalComputeProbe


def test_modal_probe_reads_modal_toml_without_echoing_secret(tmp_path, monkeypatch):
    modal_config = tmp_path / ".modal.toml"
    modal_config.write_text(
        '[test-profile]\nactive = true\ntoken_id = "ak-test-id"\ntoken_secret = "super-secret-modal-token"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("MODAL_CONFIG_PATH", str(modal_config))
    monkeypatch.setenv("MODAL_TOKEN_ID", "")
    monkeypatch.setenv("MODAL_TOKEN_SECRET", "")
    monkeypatch.setenv("MODAL_PROFILE", "")

    result = LocalComputeProbe()._modal_info()

    assert result["configured"] is True
    assert result["credential_source"] == "modal_config"
    assert result["profile"] == "test-profile"
    assert "super-secret-modal-token" not in str(result)
    assert "ak-test-id" not in str(result)


def test_modal_probe_env_credentials_win_over_modal_toml(tmp_path, monkeypatch):
    modal_config = tmp_path / ".modal.toml"
    modal_config.write_text(
        '[config-profile]\nactive = true\ntoken_id = "ak-config"\ntoken_secret = "config-secret"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("MODAL_CONFIG_PATH", str(modal_config))
    monkeypatch.setenv("MODAL_TOKEN_ID", "ak-env")
    monkeypatch.setenv("MODAL_TOKEN_SECRET", "env-secret")

    result = LocalComputeProbe()._modal_info()

    assert result["configured"] is True
    assert result["credential_source"] == "env"
    assert "config-secret" not in str(result)
    assert "env-secret" not in str(result)
