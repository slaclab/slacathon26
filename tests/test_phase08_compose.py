"""
Phase 08 — docker-compose and devcontainer config structure tests.
These are static/structural checks — no Docker daemon required.
"""
import pytest
import yaml
import json
from pathlib import Path


def test_docker_compose_exists():
    assert Path("docker-compose.yml").exists()


def test_docker_compose_services():
    with open("docker-compose.yml") as f:
        cfg = yaml.safe_load(f)
    services = cfg.get("services", {})
    assert "app" in services
    assert "mailpit" in services


def test_docker_compose_mailpit_ports():
    with open("docker-compose.yml") as f:
        cfg = yaml.safe_load(f)
    ports = cfg["services"]["mailpit"]["ports"]
    port_strs = [str(p) for p in ports]
    assert any("8025" in p for p in port_strs)
    assert any("1025" in p for p in port_strs)


def test_docker_compose_app_depends_on_mailpit():
    with open("docker-compose.yml") as f:
        cfg = yaml.safe_load(f)
    depends = cfg["services"]["app"].get("depends_on", [])
    assert "mailpit" in depends


def test_devcontainer_uses_compose():
    path = Path(".devcontainer/devcontainer.json")
    assert path.exists()
    with open(path) as f:
        cfg = json.load(f)
    assert "dockerComposeFile" in cfg
    assert cfg.get("service") == "app"


def test_devcontainer_forwards_mailpit_port():
    with open(".devcontainer/devcontainer.json") as f:
        cfg = json.load(f)
    ports = cfg.get("forwardPorts", [])
    assert 8025 in ports


def test_env_example_has_new_vars():
    path = Path(".env.example")
    assert path.exists()
    content = path.read_text()
    for var in ["SLACATHON_SMTP_HOST", "SLACATHON_PUBLIC_URL",
                "SLACATHON_ALTCHA_HMAC_KEY", "SLACATHON_VERIFY_TIMEOUT_HOURS"]:
        assert var in content, f"{var} missing from .env.example"
