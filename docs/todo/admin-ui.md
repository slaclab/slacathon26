# Admin UI

## Context

Need an admin UI that lets privileged users authenticate with their API key and perform admin operations.
Only admin operation currently needed: **delete leaderboard entries**.
A root key (set in config) is the super-admin: it can see all users and grant/revoke admin status to other verified users.
Regular admins can only access the leaderboard with delete buttons visible.

No session tokens/cookies — API key stored in `sessionStorage` after login, sent as `X-API-Key` header on admin API calls.

---

## Changes

### 1. `src/slacathon/settings.py`
Add one field:
```python
root_key: str = Field(default="", description="Super-admin API key; empty disables admin UI")
```
Env var: `SLACATHON_ROOT_KEY`.

---

### 2. `src/slacathon/db.py`

**Schema:** Add `is_admin INTEGER DEFAULT 0` column to `users` table (idempotent ALTER, same pattern as existing `email`/`verified` alters in `init_db()`).

**New functions:**
```python
def delete_leaderboard_entry(entry_id: int) -> bool
    # DELETE FROM leaderboard WHERE id = ?; return rowcount > 0

def set_user_admin(api_key: str, is_admin: bool) -> None
    # UPDATE users SET is_admin = ? WHERE api_key = ?

def get_all_verified_users() -> list[dict]
    # SELECT api_key, display_name, is_admin FROM users WHERE verified = 1

def is_admin_user(api_key: str) -> bool
    # SELECT is_admin FROM users WHERE api_key = ? AND verified = 1
```

---

### 3. `src/slacathon/middleware.py`

Add two new FastAPI dependency functions:

```python
async def verify_admin(x_api_key: str = Header(...)) -> str:
    """Accept root_key OR any user with is_admin=1."""
    if x_api_key == settings.root_key and settings.root_key:
        return x_api_key
    if x_api_key in db_get_valid_api_keys() and is_admin_user(x_api_key):
        return x_api_key
    raise HTTPException(status_code=403, detail="Admin access required")

async def verify_root(x_api_key: str = Header(...)) -> str:
    """Accept root_key only."""
    if not settings.root_key or x_api_key != settings.root_key:
        raise HTTPException(status_code=403, detail="Root access required")
    return x_api_key
```

Also modify `get_leaderboard()` to include `"id": e["id"]` in each returned dict (needed for delete calls from UI).

---

### 4. `src/slacathon/main.py`

Add new routes:

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/admin` | None | Serve `web/admin.html` |
| POST | `/admin/auth` | None | Validate key → `{valid, role: "root"\|"admin"\|null}` |
| GET | `/admin/users` | root only | Return all verified users with `is_admin` flag |
| POST | `/admin/users/{api_key}/toggle-admin` | root only | Toggle `is_admin` for user |
| DELETE | `/leaderboard/{entry_id}` | admin or root | Delete one leaderboard entry by id |

`POST /admin/auth` checks manually (no dependency):
```python
if key == settings.root_key and settings.root_key: return {"valid": True, "role": "root"}
if key in db_get_valid_api_keys() and is_admin_user(key): return {"valid": True, "role": "admin"}
return {"valid": False, "role": None}
```

Load `admin.html` at startup same as `leaderboard_page_html`.

---

### 5. `web/admin.html` (new file)

Matches existing CRT terminal aesthetic (green-on-black, monospace, same CSS as `leaderboard.html`).

**Flow:**
1. **Login screen** — API key input + AUTHENTICATE button
   - POST to `{root_path}/admin/auth`
   - Fail → show `ACCESS DENIED`
   - Success → store key in `sessionStorage.adminKey`, store role, show admin panel
2. **Admin panel:**
   - Role banner: `[ ROOT ]` or `[ ADMIN ]`
   - Button: **VIEW LEADERBOARD** → navigates to `/board`
   - Root only: **User Management** section
     - Fetches `GET /admin/users` with `X-API-Key`
     - Table: display_name | api_key (truncated) | GRANT/REVOKE ADMIN button
     - Toggle: `POST /admin/users/{api_key}/toggle-admin`

---

### 6. `web/leaderboard.html` (modify existing)

On load check `sessionStorage.getItem('adminKey')`. If present:
- Add `[ ADMIN MODE ]` badge + `[ LOGOUT ]` button top-right (logout clears key, reloads)
- Each leaderboard row gets a `[DELETE]` button
- Delete click: `DELETE /leaderboard/{entry.id}` with `X-API-Key: adminKey` → remove row on 200

---

## Files Modified

| File | Change |
|------|--------|
| `src/slacathon/settings.py` | add `root_key` field |
| `src/slacathon/db.py` | `is_admin` column alter + 4 new functions |
| `src/slacathon/middleware.py` | `verify_admin`, `verify_root`, `id` in `get_leaderboard()` |
| `src/slacathon/main.py` | 5 new routes, load `admin.html` |
| `web/leaderboard.html` | admin mode overlay (delete buttons, logout) |
| `web/admin.html` | new — login + admin panel |

---

## Verification

1. Set `SLACATHON_ROOT_KEY=test-root-key` in `.env`
2. `python -m uvicorn slacathon.main:app --reload`
3. `GET /admin` → login with root key → see `[ ROOT ]` panel
4. Grant admin to test user → login with that key → see `[ ADMIN ]` panel, no user management
5. Click VIEW LEADERBOARD → `[ ADMIN MODE ]` badge visible
6. Delete entry → row gone, `DELETE /leaderboard/{id}` returns 200
7. Logout → delete buttons gone
8. `DELETE /leaderboard/{id}` with non-admin key → 403
9. `pytest tests/ -q` passes
