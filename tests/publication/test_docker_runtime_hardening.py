from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_dockerfile_exists() -> None:
    assert (ROOT / "Dockerfile").exists()


def test_dockerfile_sets_container_env() -> None:
    assert "RAGWARRANT_CONTAINER=1" in (ROOT / "Dockerfile").read_text(encoding="utf-8")


def test_dockerfile_has_entrypoint() -> None:
    assert 'ENTRYPOINT ["ragwarrant"]' in (ROOT / "Dockerfile").read_text(encoding="utf-8")


def test_dockerfile_uses_fixed_non_root_uid() -> None:
    text = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "--uid 10001" in text
    assert "USER ragwarrant" in text


def test_dockerfile_has_runtime_metadata_and_stopsignal() -> None:
    text = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "org.opencontainers.image.title" in text
    assert "STOPSIGNAL SIGTERM" in text


def test_dockerfile_supports_outputs_mount() -> None:
    assert "/outputs" in (ROOT / "Dockerfile").read_text(encoding="utf-8")


def test_dockerfile_does_not_copy_local_data() -> None:
    assert ".local_data" not in (ROOT / "Dockerfile").read_text(encoding="utf-8")


def test_docker_compose_public_mini_exists() -> None:
    assert (ROOT / "docker/compose.public-mini.yml").exists()
    assert (ROOT / "docker-compose.yml").exists()


def test_docker_compose_public_mini_is_hardened() -> None:
    text = (ROOT / "docker/compose.public-mini.yml").read_text(encoding="utf-8")
    for expected in [
        'network_mode: "none"',
        "read_only: true",
        "no-new-privileges:true",
        "cap_drop:",
        "ALL",
        "pids_limit:",
        "mem_limit:",
        "cpus:",
    ]:
        assert expected in text


def test_docker_helper_scripts_exist() -> None:
    for rel in ["docker/run_public_mini.sh", "docker/run_governance_job.sh", "docker/healthcheck.sh"]:
        assert (ROOT / rel).exists()


def test_docker_helper_scripts_are_executable() -> None:
    for rel in ["docker/run_public_mini.sh", "docker/run_governance_job.sh", "docker/healthcheck.sh"]:
        assert (ROOT / rel).stat().st_mode & 0o111


def test_makefile_docker_targets_exist() -> None:
    text = (ROOT / "Makefile").read_text(encoding="utf-8")
    for target in ["docker-build", "docker-validate", "docker-run-public-mini", "docker-compose-public-mini"]:
        assert target in text
