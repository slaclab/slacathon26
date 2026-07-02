# Phase 04 — Page Templates (Register & Verify)

## Scope
Create Jinja2 HTML page templates for the register and verify flows.
Static files only — no Python changes. App still boots identically.

## Prereq
None (pure HTML/Jinja2 files).

## Files Created
| File | Purpose |
|---|---|
| `app/page_templates/_base_crt.html.j2` | Shared CRT terminal CSS base |
| `app/page_templates/register.html.j2` | Registration form |
| `app/page_templates/verify.html.j2` | Email verification CAPTCHA page |

> `app/page_templates/` is separate from `app/templates/pages/` (existing Jinja2 dir).
> Phase 05 wires the router to load from this directory.

---

## `app/page_templates/_base_crt.html.j2`

Shared shell. Child templates use `{% extends "_base_crt.html.j2" %}` and fill:
- `{% block title %}` — page title suffix
- `{% block content %}` — body content inside `.container`

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>SLACATHON 2026 :: {% block title %}{% endblock %}</title>
  {% block head_extra %}{% endblock %}
  <style>
    body {
      margin: 0; padding: 0;
      font-family: 'Courier New', monospace;
      color: #00ff00; background: #000000;
      min-height: 100vh; overflow-x: hidden; position: relative;
    }
    body::after {
      content: '';
      position: absolute; top: 0; left: 0; width: 100%; height: 100%;
      background: repeating-linear-gradient(
        to bottom, transparent 0px, transparent 2px,
        rgba(0,255,0,0.035) 2px, rgba(0,255,0,0.035) 3px
      );
      background-size: 100% 4px;
      animation: scan 1.6s linear infinite;
      z-index: -1; pointer-events: none;
    }
    @keyframes scan { 0% { background-position: 0 0; } 100% { background-position: 0 4px; } }
    .container {
      max-width: 520px; margin: 60px auto; padding: 32px 36px;
      background: #000; border: 2px solid #00ff00;
      box-shadow: 0 0 18px rgba(0,255,0,0.45), inset 0 0 18px rgba(0,255,0,0.06);
    }
    .title {
      font-size: 1.3em; letter-spacing: 3px; color: #00ff00;
      text-shadow: 0 0 8px #00ff00, 0 0 16px #00cc88; margin-bottom: 4px;
    }
    .subtitle {
      font-size: 0.82em; color: #00aaff; letter-spacing: 1.4px;
      text-shadow: 0 0 4px #00aaff; margin-bottom: 28px;
    }
    label { display: block; font-size: 0.78em; color: #00cc88; letter-spacing: 1px; margin-bottom: 4px; }
    input[type="email"], input[type="text"] {
      width: 100%; box-sizing: border-box;
      background: #000; border: 1px solid #00aa00;
      color: #00ff00; font-family: 'Courier New', monospace;
      font-size: 0.95em; padding: 8px 10px; margin-bottom: 20px; outline: none;
    }
    input:focus { border-color: #00ff00; box-shadow: 0 0 6px rgba(0,255,0,0.4); }
    button[type="submit"] {
      width: 100%; padding: 10px;
      background: transparent; border: 1px solid #00ff00;
      color: #00ff00; font-family: 'Courier New', monospace;
      font-size: 0.9em; letter-spacing: 2px; cursor: pointer;
      transition: all 0.2s; margin-top: 18px;
    }
    button:hover { background: rgba(0,255,0,0.08); box-shadow: 0 0 10px rgba(0,255,0,0.4); }
    .msg { font-size: 0.82em; margin-top: 16px; }
    .msg.error { color: #ff4444; text-shadow: 0 0 4px #ff4444; }
    .msg.ok    { color: #00ffcc; text-shadow: 0 0 4px #00ffcc; }
    a.back { display: inline-block; margin-bottom: 20px; color: #00aaff; text-decoration: none;
             text-shadow: 0 0 4px #00aaff; font-size: 0.82em; }
    a.back:hover { color: #00ffff; }
    .h-captcha { margin-bottom: 4px; }
    .instructions { font-size: 0.84em; color: #88bb88; margin-bottom: 22px; line-height: 1.5; }
  </style>
</head>
<body>
  <div class="container">
    {% block content %}{% endblock %}
  </div>
</body>
</html>
```

---

## `app/page_templates/register.html.j2`

```html
{% extends "_base_crt.html.j2" %}

{% block title %}REGISTER{% endblock %}

{% block head_extra %}
<script src="https://js.hcaptcha.com/1/api.js" async defer></script>
{% endblock %}

{% block content %}
<a href="{{ root_path }}/" class="back">← Return to Landing</a>
<div class="title">SLACATHON 2026</div>
<div class="subtitle">Create Account — get your API key</div>

<form id="reg-form">
  <label for="email">EMAIL ADDRESS</label>
  <input type="email" id="email" name="email" placeholder="you@example.com" required autocomplete="email">

  <label for="display_name">DISPLAY NAME (shown on leaderboard)</label>
  <input type="text" id="display_name" name="display_name" placeholder="YourHandle" required maxlength="40">

  <div class="h-captcha" data-sitekey="{{ site_key }}"></div>

  <button type="submit">[ REQUEST API KEY ]</button>
</form>

<div id="msg" class="msg"></div>

<script>
document.getElementById('reg-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const msg = document.getElementById('msg');
  msg.textContent = '';

  const captchaToken = document.querySelector('[name="h-captcha-response"]')?.value || '';
  if (!captchaToken) {
    msg.className = 'msg error';
    msg.textContent = 'ERROR: Complete the CAPTCHA first.';
    return;
  }

  const payload = {
    email: document.getElementById('email').value.trim(),
    display_name: document.getElementById('display_name').value.trim(),
    h_captcha_response: captchaToken,
  };

  try {
    const res = await fetch('{{ root_path }}/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (res.ok) {
      msg.className = 'msg ok';
      msg.textContent = '> Check your email — verification link sent.';
      document.getElementById('reg-form').style.display = 'none';
    } else {
      msg.className = 'msg error';
      msg.textContent = 'ERROR: ' + (data.detail || res.status);
      if (window.hcaptcha) window.hcaptcha.reset();
    }
  } catch (err) {
    msg.className = 'msg error';
    msg.textContent = 'NETWORK ERROR — try again.';
    if (window.hcaptcha) window.hcaptcha.reset();
  }
});
</script>
{% endblock %}
```

---

## `app/page_templates/verify.html.j2`

```html
{% extends "_base_crt.html.j2" %}

{% block title %}VERIFY EMAIL{% endblock %}

{% block head_extra %}
<script src="https://js.hcaptcha.com/1/api.js" async defer></script>
{% endblock %}

{% block content %}
<div class="title">SLACATHON 2026</div>
<div class="subtitle">Email Verification</div>

{% if error %}
<div class="msg error">ERROR: {{ error }}</div>
{% else %}
<p class="instructions">
  Solve the challenge below to confirm your email address.<br>
  Your API key will be sent immediately after.
</p>

<form id="verify-form">
  <input type="hidden" name="token" value="{{ token }}">
  <div class="h-captcha" data-sitekey="{{ site_key }}"></div>
  <button type="submit">[ VERIFY MY EMAIL ]</button>
</form>

<div id="msg" class="msg"></div>

<script>
const form = document.getElementById('verify-form');
if (form) {
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const msg = document.getElementById('msg');
    msg.textContent = '';

    const captchaToken = document.querySelector('[name="h-captcha-response"]')?.value || '';
    if (!captchaToken) {
      msg.className = 'msg error';
      msg.textContent = 'ERROR: Complete the CAPTCHA first.';
      return;
    }

    const payload = {
      token: document.querySelector('[name="token"]').value,
      h_captcha_response: captchaToken,
    };

    try {
      const res = await fetch('{{ root_path }}/verify', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (res.redirected) { window.location.href = res.url; return; }
      const data = await res.json();
      if (res.ok) {
        msg.className = 'msg ok';
        msg.textContent = '> Email verified! API key sent to your inbox.';
        form.style.display = 'none';
      } else {
        msg.className = 'msg error';
        msg.textContent = 'ERROR: ' + (data.detail || res.status);
        if (window.hcaptcha) window.hcaptcha.reset();
      }
    } catch (err) {
      msg.className = 'msg error';
      msg.textContent = 'NETWORK ERROR — try again.';
      if (window.hcaptcha) window.hcaptcha.reset();
    }
  });
}
</script>
{% endif %}
{% endblock %}
```

---

## Acceptance Criteria
- All 3 files parse as valid Jinja2 with no syntax errors
- `register.html.j2` renders with `site_key` and `root_path` context vars
- `verify.html.j2` renders with `token`, `site_key`, `root_path`, `error=None`
- `verify.html.j2` renders with `error="link expired"` — shows error div, hides form

---

## Test Suite: `tests/test_phase04_templates.py`

```python
"""Phase 04 — Jinja2 page template rendering."""
import pytest
from jinja2 import Environment, FileSystemLoader
from pathlib import Path


@pytest.fixture(scope="module")
def env():
    return Environment(loader=FileSystemLoader(str(Path("app/page_templates"))))


def test_register_renders(env):
    tmpl = env.get_template("register.html.j2")
    html = tmpl.render(site_key="test-site-key", root_path="/slacathon26")
    assert "test-site-key" in html
    assert "/slacathon26/register" in html
    assert "EMAIL ADDRESS" in html
    assert "DISPLAY NAME" in html


def test_verify_renders_no_error(env):
    tmpl = env.get_template("verify.html.j2")
    html = tmpl.render(token="tok-abc", site_key="test-site-key", root_path="/slacathon26", error=None)
    assert "tok-abc" in html
    assert "test-site-key" in html
    assert "VERIFY MY EMAIL" in html
    assert "ERROR:" not in html


def test_verify_renders_with_error(env):
    tmpl = env.get_template("verify.html.j2")
    html = tmpl.render(token="", site_key="test-site-key", root_path="/slacathon26", error="link expired")
    assert "link expired" in html
    assert "verify-form" not in html


def test_base_extends_no_error(env):
    # register and verify both extend _base_crt — rendering them confirms inheritance works
    for name in ("register.html.j2", "verify.html.j2"):
        tmpl = env.get_template(name)
        html = tmpl.render(site_key="k", root_path="/x", token="t", error=None)
        assert "SLACATHON 2026" in html
        assert "scan" in html  # animation keyframe from base CSS
```
