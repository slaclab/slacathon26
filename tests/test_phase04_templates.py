"""Phase 04 — Jinja2 page template rendering (Altcha widget)."""
import pytest
from jinja2 import Environment, FileSystemLoader
from pathlib import Path


@pytest.fixture(scope="module")
def env():
    return Environment(loader=FileSystemLoader(str(Path("app/page_templates"))))


def test_register_renders(env):
    tmpl = env.get_template("register.html.j2")
    html = tmpl.render(root_path="/slacathon26")
    assert "/slacathon26/register" in html
    assert "altcha-widget" in html
    assert "/slacathon26/captcha-challenge" in html
    assert "EMAIL ADDRESS" in html
    assert "DISPLAY NAME" in html
    assert "hcaptcha" not in html.lower()


def test_verify_renders_no_error(env):
    tmpl = env.get_template("verify.html.j2")
    html = tmpl.render(token="tok-abc", root_path="/slacathon26", error=None)
    assert "tok-abc" in html
    assert "altcha-widget" in html
    assert "VERIFY MY EMAIL" in html
    assert '<div class="msg error">' not in html
    assert "hcaptcha" not in html.lower()


def test_verify_renders_with_error(env):
    tmpl = env.get_template("verify.html.j2")
    html = tmpl.render(token="", root_path="/slacathon26", error="link expired")
    assert "link expired" in html
    assert "verify-form" not in html


def test_base_extends_no_error(env):
    for name in ("register.html.j2", "verify.html.j2"):
        tmpl = env.get_template(name)
        html = tmpl.render(root_path="/x", token="t", error=None)
        assert "SLACATHON 2026" in html
        assert "scan" in html  # keyframe from base CSS


def test_no_site_key_context_needed(env):
    """Altcha needs no site_key — rendering without it must not raise."""
    tmpl = env.get_template("register.html.j2")
    html = tmpl.render(root_path="/slacathon26")  # no site_key kwarg
    assert "altcha-widget" in html
