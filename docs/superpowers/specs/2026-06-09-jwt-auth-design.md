# JWT Authentication Design

**Date:** 2026-06-09  
**Status:** Approved  
**Scope:** Replace shared-secret (`API_SECRET`) auth with stateless JWT via httpOnly cookie

---

## Problem

The current `API_SECRET` is a machine-to-machine shared secret embedded in the Vite
frontend bundle (`VITE_API_TOKEN`). Any visitor who inspects the JS bundle can extract
it and call the Railway API directly. JWT with httpOnly cookies eliminates this exposure.

---

## Approach

Stateless JWT (HS256) stored in an httpOnly cookie. No server-side session storage.
Credentials (username + bcrypt-hashed password) stored as Railway env vars.

---

## Architecture

```
Browser (Vercel)          Backend (Railway)
      │                         │
      │  POST /auth/login        │
      │  {username, password} ──►│ bcrypt.verify → jwt.encode
      │◄── Set-Cookie: jwt=...   │ httpOnly, Secure, SameSite=None, 24h
      │                         │
      │  GET /transactions       │
      │  Cookie: jwt=... ───────►│ jwt.decode → 200
      │◄── 200 {items: [...]}    │
      │                         │
      │  POST /auth/logout       │
      │ ────────────────────────►│ delete cookie
      │◄── 204                   │
```

---

## Backend

### New file: `src/server/routes/auth.py`

- `POST /auth/login` — validates `{username, password}`, sets cookie, returns `{ok: true}`
- `POST /auth/logout` — deletes cookie, returns 204

### Modified: `config/settings.py`

Add:
- `APP_USERNAME: str` — Railway env var
- `APP_PASSWORD_HASH: str` — bcrypt hash, Railway env var
- `JWT_SECRET: str` — 32+ char random string, Railway env var

Remove:
- `API_SECRET`

### Modified: `src/server/routes/api.py`

Replace `_require_auth` (shared secret via `x-webhook-secret` header) with `_require_jwt`:

```python
def _require_jwt(jwt_cookie: str | None = Cookie(default=None)) -> None:
    if not jwt_cookie:
        raise HTTPException(status_code=401)
    try:
        jwt.decode(jwt_cookie, settings.JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401)
```

### Modified: `src/server/app.py`

- Include `auth_router`
- Update `CORSMiddleware`: `allow_credentials=True`, `allow_origins` from `settings.FRONTEND_URL`

### Libraries

```
uv add PyJWT passlib[bcrypt]
```

### Cookie settings

| Field | Prod | Local dev |
|---|---|---|
| `httponly` | True | True |
| `secure` | True | False |
| `samesite` | `"none"` | `"lax"` |
| `max_age` | 86400 (24h) | 86400 |

`SameSite=None` + `Secure=True` required for cross-origin (Vercel → Railway) cookies.
In local dev (`http://localhost`), `Secure=False` + `SameSite=lax`.

---

## Frontend

### New file: `frontend/src/pages/Login/LoginPage.tsx`

- Form: username + password fields + submit
- Calls `api.auth.login({username, password})`
- On success: navigate to `/transactions`
- On 401: show error message

### New file: `frontend/src/components/ProtectedRoute.tsx`

- Wraps protected routes
- On mount: probe `GET /transactions` — 200 → render children, 401 → redirect `/login`

### Modified: `frontend/src/api/client.ts`

- Add `withCredentials: true` to axios instance
- Remove `x-webhook-secret` header
- Remove `TOKEN` / `VITE_API_TOKEN` entirely
- Add `api.auth.login()` and `api.auth.logout()`
- Add 401 interceptor → redirect to `/login`

### Modified: `frontend/src/App.tsx`

- Add `/login` route → `<LoginPage />`
- Wrap all other routes in `<ProtectedRoute>`

### Modified: `frontend/src/pages/More/MorePage.tsx`

- Add logout button → `api.auth.logout()` → navigate to `/login`

### Removed

- `VITE_API_TOKEN` env var (frontend and Railway)
- `frontend/.env.local` `VITE_API_TOKEN` line

---

## CORS

```python
CORSMiddleware(
    allow_origins=[settings.FRONTEND_URL, "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

`allow_origins` must be explicit (not `["*"]`) when `allow_credentials=True`.

New Railway env var: `FRONTEND_URL=https://<app>.vercel.app`

---

## New Railway env vars required

| Var | Description |
|---|---|
| `APP_USERNAME` | Login username |
| `APP_PASSWORD_HASH` | `passlib` bcrypt hash of password |
| `JWT_SECRET` | 32+ char random string for signing |
| `FRONTEND_URL` | Vercel app URL for CORS |

Remove: `API_SECRET`

---

## Testing

**Backend (`tests/test_auth.py`):**
- `POST /auth/login` with correct credentials → 200, cookie set
- `POST /auth/login` with wrong password → 401, no cookie
- `GET /transactions` with valid cookie → 200
- `GET /transactions` without cookie → 401
- `GET /transactions` with expired/tampered JWT → 401
- `POST /auth/logout` → 204, cookie cleared

**Frontend:**
- Unauthenticated user hitting `/transactions` → redirected to `/login`
- Successful login → lands on `/transactions`
- Logout → lands on `/login`

---

## Out of scope

- Password reset (change via Railway env var)
- Multiple users
- Remember me / token refresh
- Rate limiting on `/auth/login`
