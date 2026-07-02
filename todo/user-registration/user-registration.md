# User Registration Plan

## Goal

Self-service registration: user submits email → gets verified → receives API key.  
No admin intervention required. Bot protection via hCaptcha on both forms.

---

## Database Choice: SQLite via SQLModel

**Why SQLite:**
- Embedded, zero ops, single file — fits existing flat-file pattern (`leaderboard.json`, `jobs.json`)
- `SQLModel` (Pydantic + SQLAlchemy) integrates cleanly with existing FastAPI/Pydantic stack
- Easy to swap for Postgres later (same SQLModel models, different connection string)

**Schema:**

```
users
  id            UUID (PK)
  email         TEXT UNIQUE NOT NULL
  api_key       TEXT UNIQUE NOT NULL
  verified      BOOL DEFAULT false
  verify_token  TEXT UNIQUE NOT NULL   -- one-time token in verification link
  created_at    DATETIME NOT NULL
  expires_at    DATETIME               -- NULL once verified; populated on create for cleanup
```

---

## CAPTCHA — hCaptcha

**Why hCaptcha:**
- Privacy-respecting (GDPR-friendly), free tier sufficient for hackathon scale
- No Google dependency (reCAPTCHA alternative)
- Simple JS widget + one server-side token verification call

**Where it appears:**
1. Registration form (`/register` page) — before `POST /register`
2. Email verification page (`/verify` page) — before the link is processed server-side

**Config:**
```
SLACATHON_HCAPTCHA_SITE_KEY   = "<from hcaptcha.com dashboard>"  # injected into HTML forms
SLACATHON_HCAPTCHA_SECRET_KEY = "<from hcaptcha.com dashboard>"  # used server-side only
SLACATHON_HCAPTCHA_VERIFY_URL = "https://api.hcaptcha.com/siteverify"
```

Dev/test: hCaptcha provides a free test site key (`10000000-ffff-ffff-ffff-000000000001`) and secret (`0x0000000000000000000000000000000000000000`) that always pass — no real captcha shown. Set these in `.env` for local dev.

**Server-side verification helper** (`captcha.py`):

```python
import httpx
from fastapi import HTTPException
from settings import settings

async def verify_captcha(token: str):
    if not token:
        raise HTTPException(status_code=400, detail="CAPTCHA token missing")
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            settings.hcaptcha_verify_url,
            data={"secret": settings.hcaptcha_secret_key, "response": token},
        )
    result = resp.json()
    if not result.get("success"):
        raise HTTPException(status_code=400, detail="CAPTCHA verification failed")
```

**`POST /register` body gains `h-captcha-response` field:**

```json
{
  "email": "user@example.com",
  "display_name": "Alex",
  "h_captcha_response": "<token from widget>"
}
```

Server calls `await verify_captcha(body.h_captcha_response)` before any DB logic.

**`GET /verify?token=<verify_token>` flow change:**

Verification link in email now points to a rendered HTML page (not a direct server action).  
That page shows the hCaptcha widget. On solve, the browser `POST`s to a new endpoint:

```
POST /verify  { "token": "<verify_token>", "h_captcha_response": "<captcha token>" }
```

Server: verify captcha → verify email token → send API key email → redirect.

This means `GET /verify` serves HTML; `POST /verify` does the actual verification.

---

## Flow

### Step 1 — User opens registration page

```
GET /register  →  serves registration HTML form
```

Form fields: `email`, `display_name`, hCaptcha widget (JS loaded from `https://js.hcaptcha.com/1/api.js`).  
Submit triggers browser `POST /register` with form data (or JSON from JS fetch).

### Step 2 — Server processes registration

```
POST /register  { "email": "...", "display_name": "...", "h_captcha_response": "..." }
```

Server logic:
1. `await verify_captcha(h_captcha_response)` — 400 if fails
2. Validate email format (`EmailStr`)
3. Query DB for existing email
4. **If exists + verified** → 409 "already registered"
5. **If exists + unverified** → delete old record, continue as new
6. **If new:**
   - Generate `api_key` = `secrets.token_urlsafe(32)`
   - Generate `verify_token` = `secrets.token_urlsafe(32)`
   - Set `expires_at = now + VERIFY_TIMEOUT`
   - Insert row (`verified=false`)
   - Send verification email
   - Return 202 "check your email"

### Step 3 — User clicks verification link → sees CAPTCHA page

Email link: `GET /verify?token=<verify_token>`

Server: renders HTML page containing:
- hCaptcha widget
- Hidden `<input name="token" value="<verify_token>">`
- Submit button "Verify my email"

No DB action yet — captcha must be solved first.

### Step 4 — User submits CAPTCHA on verification page

```
POST /verify  { "token": "<verify_token>", "h_captcha_response": "..." }
```

Server logic:
1. `await verify_captcha(h_captcha_response)` — 400 if fails
2. Look up `verify_token` in DB
3. **Not found** → 404 "invalid or expired link"
4. **Found + expired** (`expires_at < now`) → delete row → 410 "link expired, register again"
5. **Found + valid:**
   - Set `verified=true`, clear `expires_at`, clear `verify_token`
   - Send API-key delivery email
   - Redirect to `SLACATHON_ROOT_PATH/?registered=1`

### Step 3 — Expiry cleanup (background task)

FastAPI startup registers an `asyncio` background task (or APScheduler) that runs every N minutes:

```python
DELETE FROM users WHERE verified=false AND expires_at < now()
```

Env: `SLACATHON_CLEANUP_INTERVAL_MINUTES` (default 10)

---

## Email Templates

Two Jinja2 templates in `email_templates/`:

### `verify_email.html.j2`

```
Subject: Verify your SLACATHON'26 account

Hello,

Click the link below to verify your email address.
This link expires in {{ timeout_hours }} hours.

{{ verify_url }}

If you did not request this, ignore this email.
```

### `api_key_delivery.html.j2`

```
Subject: Your SLACATHON'26 API Key

Hello,

Your email has been verified. Here is your API key:

  {{ api_key }}

Use it as:
  Authorization: Bearer {{ api_key }}

Do not share this key. If lost, re-register with the same email.
```

Templates are plain HTML files — edit freely without touching Python code.

---

## Fake Mail Server (Dev)

Add **Mailpit** to the dev environment. Mailpit is a lightweight SMTP server + web UI — no config, no auth, no real emails sent.

- SMTP on port `1025`
- Web UI on port `8025` → browse all sent emails at `http://localhost:8025`

Python mail sending: `aiosmtplib` for async SMTP.

```python
# config (settings.py additions)
SLACATHON_SMTP_HOST   = "localhost"
SLACATHON_SMTP_PORT   = 1025
SLACATHON_SMTP_FROM   = "noreply@slacathon26.local"
SLACATHON_PUBLIC_URL  = "http://localhost:8000"   # base for verify link
```

---

## Docker Compose (Dev Container update)

Replace current single-container `devcontainer.json` approach with `docker-compose.yml`:

```yaml
version: "3.9"
services:
  app:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - .:/workspace
    environment:
      - SLACATHON_SMTP_HOST=mailpit
      - SLACATHON_SMTP_PORT=1025
    depends_on:
      - mailpit

  mailpit:
    image: axllent/mailpit:latest
    ports:
      - "1025:1025"   # SMTP
      - "8025:8025"   # Web UI
```

Update `.devcontainer/devcontainer.json`:
- `dockerComposeFile: ../docker-compose.yml`
- `service: app`
- Forward port `8025` for Mailpit UI

---

## New Files

| File | Purpose |
|---|---|
| `db.py` | SQLModel engine, session factory, `get_session` dependency |
| `models/user.py` | `User` SQLModel table model |
| `routers/registration.py` | `GET /register`, `POST /register`, `GET /verify`, `POST /verify` endpoints |
| `captcha.py` | `verify_captcha(token)` async helper — calls hCaptcha siteverify API |
| `email_service.py` | Async SMTP send, template render via Jinja2 |
| `email_templates/verify_email.html.j2` | Verification email template |
| `email_templates/api_key_delivery.html.j2` | API key delivery template |
| `page_templates/register.html.j2` | Registration form page — email + display name + hCaptcha widget |
| `page_templates/verify.html.j2` | Email verification page — hCaptcha widget + hidden token field |
| `docker-compose.yml` | App + Mailpit services |
| `.devcontainer/devcontainer.json` | Updated dev container using compose |

---

## Changes to Existing Files

| File | Change |
|---|---|
| `main.py` | Mount `registration` router; start cleanup background task on startup |
| `settings.py` | Add `SMTP_HOST/PORT/FROM`, `PUBLIC_URL`, `VERIFY_TIMEOUT_HOURS`, `CLEANUP_INTERVAL_MINUTES` |
| `middleware.py` | Full DB migration — see detail below |
| `requirements.txt` | Add `sqlmodel`, `aiosmtplib`, `jinja2`, `email-validator` |

### `middleware.py` — detailed changes

**Remove entirely:**
- `_load_valid_api_keys()` function
- `VALID_API_KEYS` module-level set
- `user_names_fallback` dict (`{"key_123": "Alex", ...}`)
- `load_user_names()` / `save_user_names()` functions
- `user_names` module-level dict
- `USER_NAMES_FILE` constant (also remove from `settings.py` if only used here)

**Replace `verify_api_key`:**

```python
# Before (env-var lookup)
async def verify_api_key(x_api_key: str = Header(...)) -> str:
    if x_api_key not in VALID_API_KEYS:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return x_api_key

# After (DB lookup — only verified users pass)
from sqlmodel import Session, select
from db import get_session
from models.user import User

async def verify_api_key(
    x_api_key: str = Header(...),
    session: Session = Depends(get_session),
) -> str:
    user = session.exec(
        select(User).where(User.api_key == x_api_key, User.verified == True)
    ).first()
    if not user:
        logger.warning("Invalid or unverified API key attempted")
        raise HTTPException(status_code=401, detail="Invalid API key")
    return x_api_key
```

**Replace `get_display_name`:**

```python
# Before (dict lookup with fallback)
def get_display_name(api_key: str) -> str:
    return user_names.get(api_key, "Anonymous")

# After (DB lookup)
def get_display_name(api_key: str, session: Session) -> str:
    user = session.exec(select(User).where(User.api_key == api_key)).first()
    return user.display_name if user else "Anonymous"
```

> `display_name` is a new optional column on `User` — see schema update below.

**`LeaderboardEntry.to_dict`** currently calls `get_display_name(self.user_id)` with no session. Two options:
- Pass `session` into `to_dict(session)` — clean but requires threading session through callers
- Store `display_name` as a snapshot column in `LeaderboardEntry` at write time (simpler, no session needed at read time) — **preferred**

Preferred: `add_to_leaderboard` resolves the display name once via DB, stores it in the entry, `to_dict` uses the stored value. No session needed at read time.

**`add_to_leaderboard` signature change:**

```python
# Add session param; resolve display name at write time
def add_to_leaderboard(
    user_id: str, input: dict, score: float, solved: bool,
    session: Session,
):
    display_name = get_display_name(user_id, session)
    entry = LeaderboardEntry(user_id, display_name, input, score, solved, time.time())
    ...
```

`LeaderboardEntry.__init__` gains a `display_name: str` field; `to_dict` uses it directly.

---

### Schema update — add `display_name` to `User`

```
users
  id            UUID (PK)
  email         TEXT UNIQUE NOT NULL
  display_name  TEXT NOT NULL          -- ← new; sourced from registration form
  api_key       TEXT UNIQUE NOT NULL
  verified      BOOL DEFAULT false
  verify_token  TEXT UNIQUE NOT NULL
  created_at    DATETIME NOT NULL
  expires_at    DATETIME
```

`POST /register` body becomes:

```json
{ "email": "user@example.com", "display_name": "Alex" }
```

This resolves Open Question #1 (display name at registration time).

---

### Migration path for existing dev keys

Dev keys (`key_123 / key_456 / key_789`) and their names currently live in `user_names_fallback`.  
On first startup with the new code, seed the DB with those rows so existing test workflows don't break:

```python
# db.py — create_db_and_tables() calls this after table creation
def seed_dev_users(session: Session):
    dev_users = [
        ("key_123", "Alex", "alex@dev.local"),
        ("key_456", "Chris", "chris@dev.local"),
        ("key_789", "Ken", "ken@dev.local"),
    ]
    for api_key, display_name, email in dev_users:
        if not session.exec(select(User).where(User.api_key == api_key)).first():
            session.add(User(
                email=email, display_name=display_name,
                api_key=api_key, verified=True,
                verify_token="dev-seeded",
            ))
    session.commit()
```

Run only when `settings.api_keys` is empty (dev mode). Skip in production.

---

## HTML Page Templates

Both pages use the **CRT terminal aesthetic** from `leaderboard.html` (black bg, green phosphor, `Courier New`, scanline animation, glowing border). They are Jinja2 templates so `{{ site_key }}` and `{{ token }}` are injected server-side.

### `page_templates/register.html.j2`

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>SLACATHON 2026 :: REGISTER</title>
  <script src="https://js.hcaptcha.com/1/api.js" async defer></script>
  <style>
    body {
      margin: 0; padding: 0;
      font-family: 'Courier New', monospace;
      color: #00ff00;
      background: #000000;
      min-height: 100vh;
      overflow-x: hidden;
      position: relative;
    }
    body::after {
      content: '';
      position: absolute;
      top: 0; left: 0; width: 100%; height: 100%;
      background:
        repeating-linear-gradient(to bottom, transparent 0px, transparent 2px, rgba(0,255,0,0.035) 2px, rgba(0,255,0,0.035) 3px);
      background-size: 100% 4px;
      animation: scan 1.6s linear infinite;
      z-index: -1; pointer-events: none;
    }
    @keyframes scan { 0% { background-position: 0 0; } 100% { background-position: 0 4px; } }
    .container {
      max-width: 520px;
      margin: 60px auto;
      padding: 32px 36px;
      background: #000;
      border: 2px solid #00ff00;
      box-shadow: 0 0 18px rgba(0,255,0,0.45), inset 0 0 18px rgba(0,255,0,0.06);
    }
    .title {
      font-size: 1.3em; letter-spacing: 3px;
      color: #00ff00; text-shadow: 0 0 8px #00ff00, 0 0 16px #00cc88;
      margin-bottom: 4px;
    }
    .subtitle {
      font-size: 0.82em; color: #00aaff;
      letter-spacing: 1.4px; text-shadow: 0 0 4px #00aaff;
      margin-bottom: 28px;
    }
    label { display: block; font-size: 0.78em; color: #00cc88; letter-spacing: 1px; margin-bottom: 4px; }
    input[type="email"], input[type="text"] {
      width: 100%; box-sizing: border-box;
      background: #000; border: 1px solid #00aa00;
      color: #00ff00; font-family: 'Courier New', monospace;
      font-size: 0.95em; padding: 8px 10px; margin-bottom: 20px;
      outline: none;
    }
    input:focus { border-color: #00ff00; box-shadow: 0 0 6px rgba(0,255,0,0.4); }
    button[type="submit"] {
      width: 100%; padding: 10px;
      background: transparent; border: 1px solid #00ff00;
      color: #00ff00; font-family: 'Courier New', monospace;
      font-size: 0.9em; letter-spacing: 2px;
      cursor: pointer; transition: all 0.2s;
      margin-top: 18px;
    }
    button:hover { background: rgba(0,255,0,0.08); box-shadow: 0 0 10px rgba(0,255,0,0.4); }
    .msg { font-size: 0.82em; margin-top: 16px; }
    .msg.error { color: #ff4444; text-shadow: 0 0 4px #ff4444; }
    .msg.ok    { color: #00ffcc; text-shadow: 0 0 4px #00ffcc; }
    a.back { display: inline-block; margin-bottom: 20px; color: #00aaff; text-decoration: none; text-shadow: 0 0 4px #00aaff; font-size: 0.82em; }
    a.back:hover { color: #00ffff; }
    .h-captcha { margin-bottom: 4px; }
  </style>
</head>
<body>
  <div class="container">
    <a href="/slacathon26/" class="back">← Return to Landing</a>
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
  </div>

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
        const res = await fetch('/slacathon26/register', {
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
</body>
</html>
```

---

### `page_templates/verify.html.j2`

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>SLACATHON 2026 :: VERIFY EMAIL</title>
  <script src="https://js.hcaptcha.com/1/api.js" async defer></script>
  <style>
    /* same CSS as register.html.j2 — extract to shared base or duplicate */
    body {
      margin: 0; padding: 0;
      font-family: 'Courier New', monospace;
      color: #00ff00; background: #000000;
      min-height: 100vh; overflow-x: hidden; position: relative;
    }
    body::after {
      content: '';
      position: absolute; top: 0; left: 0; width: 100%; height: 100%;
      background: repeating-linear-gradient(to bottom, transparent 0px, transparent 2px, rgba(0,255,0,0.035) 2px, rgba(0,255,0,0.035) 3px);
      background-size: 100% 4px;
      animation: scan 1.6s linear infinite;
      z-index: -1; pointer-events: none;
    }
    @keyframes scan { 0% { background-position: 0 0; } 100% { background-position: 0 4px; } }
    .container {
      max-width: 480px; margin: 80px auto; padding: 32px 36px;
      background: #000; border: 2px solid #00ff00;
      box-shadow: 0 0 18px rgba(0,255,0,0.45), inset 0 0 18px rgba(0,255,0,0.06);
    }
    .title { font-size: 1.3em; letter-spacing: 3px; color: #00ff00; text-shadow: 0 0 8px #00ff00, 0 0 16px #00cc88; margin-bottom: 4px; }
    .subtitle { font-size: 0.82em; color: #00aaff; letter-spacing: 1.4px; text-shadow: 0 0 4px #00aaff; margin-bottom: 28px; }
    .instructions { font-size: 0.84em; color: #88bb88; margin-bottom: 22px; line-height: 1.5; }
    button[type="submit"] {
      width: 100%; padding: 10px;
      background: transparent; border: 1px solid #00ff00;
      color: #00ff00; font-family: 'Courier New', monospace;
      font-size: 0.9em; letter-spacing: 2px;
      cursor: pointer; transition: all 0.2s; margin-top: 18px;
    }
    button:hover { background: rgba(0,255,0,0.08); box-shadow: 0 0 10px rgba(0,255,0,0.4); }
    .msg { font-size: 0.82em; margin-top: 16px; }
    .msg.error { color: #ff4444; text-shadow: 0 0 4px #ff4444; }
    .msg.ok    { color: #00ffcc; text-shadow: 0 0 4px #00ffcc; }
    .h-captcha { margin-bottom: 4px; }
  </style>
</head>
<body>
  <div class="container">
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
    {% endif %}
  </div>

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
          const res = await fetch('/slacathon26/verify', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
          });
          if (res.redirected) {
            window.location.href = res.url;
            return;
          }
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
</body>
</html>
```

> **Note:** Both templates share identical CSS. During implementation, extract the shared styles into a `page_templates/_base_crt.html.j2` and use Jinja2 `{% extends %}` / `{% block %}` to avoid duplication.

---

## What You Flagged + Gaps I Added

| Your item | Status |
|---|---|
| Email input | Covered — `POST /register` |
| DB check for existing email | Covered + resend flow added |
| New user + API key + verify email | Covered |
| Timeout → delete unverified | Covered — background cleanup task |
| Click link → verify → send API key email | Covered |
| Email templates (editable) | Covered — Jinja2 `.j2` files |
| Fake mail server | Covered — Mailpit |
| Update dev container to docker compose | Covered |

**Gaps added:**
- Resend flow: unverified user re-registers → old record replaced, fresh token/timer
- Already-verified duplicate: returns 409, no duplicate keys created
- Expired token path: explicit 410 with actionable message
- `verify_token` cleared after use (one-time only)
- All secrets via `secrets.token_urlsafe` (crypto-random)
- API key auth in `middleware.py` migrated from env var to DB lookup (otherwise registered users can't actually use the platform)

---

## Open Questions Before Implementation

1. ~~**Display name**~~ — **Resolved**: collected at registration (`POST /register` body), stored in `users.display_name`. `user_names.json` and fallback dict removed.
2. **Quota on fresh users** — inherit task's `MAX_VALIDATIONS_PER_USER` immediately, or grant after first submission?
3. **API key rotation** — out of scope for now, or add a `POST /rotate-key` behind the verify flow?
4. **Production SMTP** — which relay (SendGrid, SES, etc.)? Settings already parameterized so just needs real `SMTP_*` values.
