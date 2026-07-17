# SDD Spec: `simple-secure-auth`

## Status
`spec` — ready for design phase.

## 1. Endpoint Contracts

All auth endpoints are public (no auth dependency). All other endpoints require the auth cookie.

### 1.1 `POST /auth/login`

Authenticate a user and set an HttpOnly JWT cookie.

**Request body:**
```json
{
  "email": "soporte@gmail.com",
  "password": "123456"
}
```

**Response 200 OK:**
```json
{
  "user": {
    "id": "0190...",
    "email": "soporte@gmail.com",
    "role": "admin"
  }
}
```

**Response 401 Unauthorized:**
```json
{"detail": "Invalid email or password"}
```

**Cookie set:**
- Name: `access_token`
- Value: JWT
- HttpOnly: true
- Secure: false in local dev (configurable via `AUTH_COOKIE_SECURE` env var, default `false` for localhost)
- SameSite: `lax`
- Path: `/`
- Max-Age: 24 hours (configurable via `AUTH_TOKEN_TTL_HOURS`, default `24`)

### 1.2 `POST /auth/logout`

Clear the auth cookie.

**Response 200 OK:**
```json
{"ok": true}
```

**Cookie cleared:** `access_token` with `Max-Age=0`.

### 1.3 `GET /auth/me`

Return the current authenticated user.

**Response 200 OK:**
```json
{
  "id": "0190...",
  "email": "soporte@gmail.com",
  "role": "admin"
}
```

**Response 401 Unauthorized:**
```json
{"detail": "Not authenticated"}
```

### 1.4 `POST /auth/change-password`

Change the current user's password.

**Request body:**
```json
{
  "current_password": "123456",
  "new_password": "nueva123"
}
```

**Validation rules:**
- `current_password` must match the stored hash.
- `new_password` must be different from `current_password`.
- No other complexity rules.

**Response 200 OK:**
```json
{"ok": true}
```

**Response 401 Unauthorized:**
```json
{"detail": "Current password is incorrect"}
```

**Response 400 Bad Request:**
```json
{"detail": "New password must be different from current password"}
```

## 2. BigQuery `users` Table Schema

Add to `odoo/config_store/codecs.py` `TABLE_SCHEMAS`:

```python
"odoo_users": [
    {"name": "id", "type": "STRING", "mode": "REQUIRED"},
    {"name": "email", "type": "STRING", "mode": "REQUIRED"},
    {"name": "password_hash", "type": "STRING", "mode": "REQUIRED"},
    {"name": "role", "type": "STRING", "mode": "REQUIRED"},
    {"name": "active", "type": "BOOL", "mode": "REQUIRED"},
    {"name": "created_at", "type": "TIMESTAMP", "mode": "REQUIRED"},
    {"name": "updated_at", "type": "TIMESTAMP", "mode": "REQUIRED"},
]
```

- `id`: UUID v4 string (primary identifier).
- `email`: lowercase, unique.
- `password_hash`: bcrypt hash.
- `role`: `"admin"` or `"user"`.
- `active`: boolean, default `true`.
- `created_at` / `updated_at`: UTC timestamps.

## 3. ConfigStore Protocol Additions

Add to `odoo/config_store/protocol.py` under a new `users` section:

```python
# users
def get_user_by_email(self, email: str) -> dict | None: ...
def create_user(self, row: dict) -> dict: ...
def update_user_password(self, user_id: str, password_hash: str) -> dict: ...
def count_users(self) -> int: ...
```

### Method semantics

- `get_user_by_email(email)`: case-insensitive email lookup. Returns decoded user dict or `None`.
- `create_user(row)`: inserts a new user. Raises `ConflictError` if email already exists.
- `update_user_password(user_id, password_hash)`: updates `password_hash` and `updated_at`. Raises `NotFoundError` if user missing.
- `count_users()`: returns number of users; used by seeding logic to decide whether to create the default user.

## 4. SQL Additions

Add to `odoo/config_store/sql.py`:

```python
def T_USERS() -> str:
    return _t("odoo_users")

SQL_GET_USER_BY_EMAIL = lambda: f"SELECT * FROM `{_t('odoo_users')}` WHERE lower(email) = lower(@email)"
SQL_INSERT_USER = lambda: f"""
INSERT INTO `{_t('odoo_users')}` (id, email, password_hash, role, active, created_at, updated_at)
VALUES (@id, @email, @password_hash, @role, @active, @created_at, @updated_at)
"""
SQL_UPDATE_USER_PASSWORD = lambda: f"""
UPDATE `{_t('odoo_users')}`
SET password_hash = @password_hash, updated_at = @updated_at
WHERE id = @id
"""
SQL_COUNT_USERS = lambda: f"SELECT COUNT(*) AS n FROM `{_t('odoo_users')}`"
```

## 5. Backend Implementation Details

### 5.1 `odoo/auth.py`

New module with:

- `pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")` from `passlib`.
- `verify_password(plain, hashed) -> bool`
- `get_password_hash(plain) -> str`
- `create_access_token(user_id: str, email: str, role: str) -> str` — returns JWT with claims `{sub, email, role, iat, exp}`.
- `get_current_user(request: Request) -> UserOut` — FastAPI dependency that reads `access_token` cookie, decodes JWT with `SECRET_KEY`, validates expiration, and looks up the user in the store. Raises `HTTPException(401)` if invalid or missing.
- `settings`: load `SECRET_KEY` and `AUTH_TOKEN_TTL_HOURS` from env. Fail startup if `SECRET_KEY` is missing.

### 5.2 `odoo/routers/auth.py`

New FastAPI router:

- `POST /auth/login` — validate credentials, set cookie, return user info.
- `POST /auth/logout` — clear cookie.
- `GET /auth/me` — requires `get_current_user`, returns user info.
- `POST /auth/change-password` — requires `get_current_user`, validates current password, updates hash.

### 5.3 `odoo/main.py`

- Import `auth` router and `get_current_user`.
- Add `app.include_router(auth.router)`.
- Apply auth dependency to all other routers:
  ```python
  from auth import get_current_user
  from fastapi import Depends
  app.include_router(catalog.router, dependencies=[Depends(get_current_user)])
  # ... repeat for categories, runner, explorer, export, bigquery, file_upload, schedules
  ```
- Leave `/` (health) and `/auth/*` public.
- On startup, after `seed_defaults`, seed the default user if `count_users() == 0`.

### 5.4 `odoo/config_store/__init__.py` / seeding

Add a helper `seed_default_user(store)` that creates `soporte@gmail.com` with role `admin` if no users exist. Called from `main.py` startup after `seed_defaults`.

### 5.5 `odoo/config_store/bq_store.py` and `memory_store.py`

Implement the four new user methods using the SQL templates and in-memory list respectively.

## 6. Frontend Contracts

### 6.1 `odoo-ui/src/app/services/auth.ts`

New `AuthService` with:

```typescript
export interface User { id: string; email: string; role: 'admin' | 'user'; }

@Injectable({ providedIn: 'root' })
export class AuthService {
  private http = inject(HttpClient);
  private base = 'http://localhost:8000';
  private msg = inject(MessageService);

  user = signal<User | null>(null);
  isAuthenticated = computed(() => this.user() !== null);

  login(email: string, password: string): Observable<User> { ... }
  logout(): Observable<void> { ... }
  me(): Observable<User> { ... }
  changePassword(current_password: string, new_password: string): Observable<void> { ... }
  handleUnauthorized(): void { ... } // clears user, shows login
}
```

- `login` hits `POST /auth/login` with `withCredentials: true`. On success, sets `user` signal.
- `logout` hits `POST /auth/logout` with `withCredentials: true`. On success, clears `user`.
- `me` hits `GET /auth/me` with `withCredentials: true`. On 401, clears `user`.
- `changePassword` hits `POST /auth/change-password` with `withCredentials: true`.
- All auth requests use `withCredentials: true` because cookies are HttpOnly.

### 6.2 HTTP Interceptor

Add to `odoo-ui/src/app/app.config.ts`:

```typescript
provideHttpClient(withInterceptors([authInterceptor]))
```

`authInterceptor` adds `withCredentials: true` to all requests to `localhost:8000`. On 401/403 responses, it calls `AuthService.handleUnauthorized()`.

### 6.3 `odoo-ui/src/app/pages/login/login.ts` and `login.html`

New standalone component with:
- Email input.
- Password input.
- Login button.
- Error message on invalid credentials.
- On success, emits `loggedIn` to `AppComponent`.

### 6.4 `odoo-ui/src/app/pages/change-password/change-password.ts` and `change-password.html`

New standalone component with:
- Current password input.
- New password input.
- Confirm new password input.
- Submit button.
- Validation: new password must differ from current; confirm must match new.
- On success, shows toast and optionally logs out.

### 6.5 `odoo-ui/src/app/app.ts` and `app.html`

- Add `AuthService` and `login`/`change-password` tabs to the nav model.
- Add `isAuthenticated()` computed.
- `app.html` renders login shell if not authenticated; otherwise renders the existing tab shell.
- Add a logout button or menu item in the sidebar (e.g., next to the brand or as a nav item).
- Add "Change Password" as a nav item in the sidebar (only when authenticated).
- On startup, call `AuthService.me()` to check existing session.

## 7. Route Protection

### Backend

- Public: `GET /`, `POST /auth/login`, `POST /auth/logout`.
- Protected: everything else, via router-level `dependencies=[Depends(get_current_user)]`.

### Frontend

- Conditional rendering in `app.html`: if not authenticated, show `LoginComponent`; if authenticated, show the tab shell.
- The `Login` tab is only visible when not authenticated.
- The `Change Password` tab is only visible when authenticated.
- Logout affordance is always visible when authenticated.

## 8. Test Scenarios

### Backend (`odoo/tests/test_auth.py`)

1. `test_login_success` — login with seeded user returns 200 and sets cookie.
2. `test_login_invalid_password` — wrong password returns 401, no cookie.
3. `test_login_unknown_email` — unknown email returns 401.
4. `test_me_authenticated` — `/auth/me` returns user info with valid cookie.
5. `test_me_unauthenticated` — `/auth/me` returns 401 without cookie.
6. `test_logout_clears_cookie` — logout returns 200 and clears cookie.
7. `test_change_password_success` — valid current password updates hash and subsequent login works with new password.
8. `test_change_password_wrong_current` — wrong current password returns 401.
9. `test_change_password_same_as_current` — new password same as current returns 400.
10. `test_protected_route_requires_auth` — `GET /queries/` returns 401 without cookie.
11. `test_default_user_seeded` — startup seeds `soporte@gmail.com` if users table is empty.

### Frontend (`odoo-ui/src/app/services/auth.service.spec.ts`)

1. `login` posts credentials and sets user signal.
2. `login` error clears user signal.
3. `me` returns user and sets signal.
4. `logout` clears user signal.
5. `changePassword` posts correct payload.

### Frontend (`odoo-ui/src/app/app.spec.ts` or similar)

1. Shows login component when not authenticated.
2. Shows tab shell when authenticated.
3. Renders change-password nav item when authenticated.

## 9. Acceptance Criteria

- [ ] `soporte@gmail.com` / `123456` can log in and sees the dashboard tabs.
- [ ] Without a valid cookie, all backend endpoints except `/` and `/auth/*` return 401.
- [ ] With a valid cookie, all backend endpoints work normally.
- [ ] Logout clears the cookie and returns the user to the login screen.
- [ ] Change password works when current password is correct and new password is different.
- [ ] Passwords are never stored in plaintext; only bcrypt hashes exist in BigQuery.
- [ ] `SECRET_KEY` is read from environment and startup fails if missing.
- [ ] Backend tests pass (`cd odoo && .venv/bin/python -m pytest -q`).
- [ ] Frontend build passes (`cd odoo-ui && npm run build`).
- [ ] Frontend tests pass (`cd odoo-ui && npm test -- --watch=false`).
- [ ] No existing functionality is broken by the auth layer (e.g., `TestClient` fixture provides an authenticated override for existing tests).

## 10. Environment Variables

- `SECRET_KEY` (required): secret key for JWT signing.
- `AUTH_TOKEN_TTL_HOURS` (optional, default `24`): JWT/cookie expiration in hours.
- `AUTH_COOKIE_SECURE` (optional, default `false`): whether the auth cookie uses `Secure` flag.

## 11. Next Recommended Phase

`sdd-design` — produce detailed technical design (file-by-file changes, exact function/class signatures, Angular component structure, and test strategy) before implementation.
