import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def test_work_exchange_worker_script_is_portable_and_has_help():
    script = ROOT / "public" / "downloads" / "nomad_work_exchange_worker.py"

    result = subprocess.run(
        [sys.executable, str(script), "--help"],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert result.returncode == 0
    assert "--obligation-id" in result.stdout
    assert "--loop" in result.stdout


def test_work_exchange_installer_points_to_worker_download():
    installer = ROOT / "public" / "downloads" / "install_nomad_work_exchange_worker.bat"
    text = installer.read_text(encoding="utf-8")

    assert "nomad_work_exchange_worker.py" in text
    assert "OBLIGATION_ID" in text
    assert "NomadWorkExchangeWorker" in text


def test_work_exchange_human_page_contains_start_command():
    page = ROOT / "public" / "work-exchange.html"
    text = page.read_text(encoding="utf-8")

    assert "Free repair against verified return compute" in text
    assert "/downloads/install_nomad_work_exchange_worker.bat" in text
    assert "OBLIGATION_ID_HERE" in text
    assert "/.well-known/nomad-agent-reliability-doctor.json" in text
    assert "/downloads/nomad_reliability_doctor_action.yml" in text
    assert "/downloads/nomad_work_exchange_worker.Dockerfile" in text


def test_work_exchange_dockerfile_and_github_action_are_published_onramps():
    dockerfile = (ROOT / "public" / "downloads" / "nomad_work_exchange_worker.Dockerfile").read_text(encoding="utf-8")
    action = (ROOT / "public" / "downloads" / "nomad_reliability_doctor_action.yml").read_text(encoding="utf-8")

    assert "NOMAD_WORK_EXCHANGE_OBLIGATION_ID" in dockerfile
    assert "nomad_work_exchange_worker.py" in dockerfile
    assert "/swarm/reliability-doctor/intake" in action
    assert "accepted_compute_barter_terms" in action
