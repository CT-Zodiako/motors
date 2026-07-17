# SDD Tasks: `simple-secure-auth`

## Status
`tasks` — ready for apply.

## Review Workload Forecast

Estimated changed lines: **~900–1100** across backend and frontend. This exceeds the configured 400-line review budget, so the work should be split into **2 chained PRs** to protect the reviewer:

1. **PR-1 — Backend auth foundation** (~350–450 lines)
   - Users table + ConfigStore methods + seeding.
   - Auth utilities + login/logout/me/change-password endpoints.
   - Route protection in `main.py`.
   - Backend tests.
2. **PR-2 — Frontend auth integration** (~550–650 lines)
   - AuthService, HTTP interceptor, Login component, ChangePassword component.
   - App shell conditional rendering, sidebar menu updates.
   - Frontend tests.

For this SDD, the apply phase can implement both PRs sequentially in the same branch, but the commit/PR boundary should respect PR-1 and PR-2.

## Implementation Tasks

### PR-1: Backend auth foundation

- [ ] **1.1** Add Python dependencies
  - Add `passlib[bcrypt]`, `python-jose[cryptography]`, `python-multipart` to `odoo/requirements.txt` and install in `.venv`.
  - Verify imports work: `from passlib.context import CryptContext`, `from jose import jwt`.

- [ ] **1.2** Add `odoo_users` table schema
  - Edit `odoo/config_store/codecs.py`: add `odoo_users` to `TABLE_SCHEMAS`.
  - Columns: `id` STRING, `email` STRING, `password_hash` STRING, `role` STRING, `active` BOOL, `created_at` TIMESTAMP, `updated_at` TIMESTAMP.

- [ ] **1.3** Add user SQL templates
  - Edit `odoo/config_store/sql.py`: add `T_USERS()`, `SQL_GET_USER_BY_EMAIL`, `SQL_INSERT_USER`, `SQL_UPDATE_USER_PASSWORD`, `SQL_COUNT_USERS`.

- [ ] **1.4** Extend ConfigStore Protocol
  - Edit `odoo/config_store/protocol.py`: add `get_user_by_email`, `create_user`, `update_user_password`, `count_users` methods under a `users` section.

- [ ] **1.5** Implement user methods in BigQuery store
  - Edit `odoo/config_store/bq_store.py`: implement the four user methods using the SQL templates and `codecs.decode_row`.
  - Add `_cache.invalidate_users()` helper or use existing cache invalidation.

- [ ] **1.6** Implement user methods in memory store
  - Edit `odoo/config_store/memory_store.py`: implement the four user methods using `self._data["odoo_users"]`.
  - Enforce email uniqueness (case-insensitive) and raise `ConflictError` on duplicates.

- [ ] **1.7** Create `odoo/auth.py`
  - Implement `pwd_context` with bcrypt.
  - Implement `verify_password`, `get_password_hash`, `create_access_token`.
  - Implement `get_current_user(request: Request)` FastAPI dependency.
  - Load `SECRET_KEY`, `AUTH_TOKEN_TTL_HOURS`, `AUTH_COOKIE_SECURE` from environment at import time; raise `RuntimeError` if `SECRET_KEY` missing.

- [ ] **1.8** Create `odoo/routers/auth.py`
  - Implement Pydantic models: `LoginIn`, `ChangePasswordIn`, `UserOut`.
  - Implement `POST /auth/login`, `POST /auth/logout`, `GET /auth/me`, `POST /auth/change-password`.
  - Set/clear `access_token` HttpOnly cookie with correct attributes.

- [ ] **1.9** Wire auth router and protect routes in `odoo/main.py`
  - Import `auth` router and `get_current_user`.
  - Add `app.include_router(auth.router)`.
  - Add `dependencies=[Depends(get_current_user)]` to all other routers except health.
  - Add `seed_default_user(store)` call after `seed_defaults` in startup.

- [ ] **1.10** Create seed default user helper
  - Add `seed_default_user` function in `odoo/config_store/bootstrap.py` or `odoo/auth_seed.py`.
  - Seed `soporte@gmail.com` / `123456` with role `admin` if `count_users() == 0`.

- [ ] **1.11** Backend tests
  - Create `odoo/tests/test_auth.py`.
  - Tests: login success, invalid password, unknown email, `/me` authenticated/unauthenticated, logout clears cookie, change password success/wrong current/same as current, protected route requires auth, default user seeded.
  - Update `odoo/tests/conftest.py` to seed the default user and provide an auth override for existing tests if needed.

- [ ] **1.12** Verify backend
  - Run `cd odoo && .venv/bin/python -m pytest -q`.
  - All tests must pass (backend + new auth tests).

### PR-2: Frontend auth integration

- [ ] **2.1** Create `odoo-ui/src/app/services/auth.ts`
  - Define `User` interface.
  - Implement `AuthService` with signals (`user`, `isAuthenticated`, `isAdmin`).
  - Methods: `login`, `logout`, `me`, `changePassword`, `handleUnauthorized`.
  - All HTTP calls use `withCredentials: true`.

- [ ] **2.2** Create `odoo-ui/src/app/services/auth.interceptor.ts`
  - Implement `authInterceptor` as `HttpInterceptorFn`.
  - Add `withCredentials: true` to all requests to `localhost:8000`.
  - On 401/403, call `AuthService.handleUnauthorized()`.

- [ ] **2.3** Register interceptor in `odoo-ui/src/app/app.config.ts`
  - Replace `provideHttpClient()` with `provideHttpClient(withInterceptors([authInterceptor]))`.

- [ ] **2.4** Create `odoo-ui/src/app/pages/login/login.ts` and `login.html`
  - Standalone component with PrimeNG form (email, password, submit button, error message).
  - Calls `AuthService.login()`.
  - Style consistently with the app (use `styles.css` variables).

- [ ] **2.5** Create `odoo-ui/src/app/pages/login/login.css`
  - Centered login card, clean form styling, responsive.

- [ ] **2.6** Create `odoo-ui/src/app/pages/change-password/change-password.ts` and `change-password.html`
  - Standalone component with current password, new password, confirm password.
  - Validation: confirm matches new; new differs from current (also backend validated).
  - Calls `AuthService.changePassword()`.

- [ ] **2.7** Create `odoo-ui/src/app/pages/change-password/change-password.css`
  - Form styling consistent with other pages.

- [ ] **2.8** Update `odoo-ui/src/app/app.ts`
  - Inject `AuthService`.
  - Add `change-password` to `Tab` type and nav groups.
  - Call `AuthService.me()` in `ngOnInit` to check existing session.
  - Add `logout()` method.

- [ ] **2.9** Update `odoo-ui/src/app/app.html`
  - Wrap existing shell in `@if (auth.isAuthenticated()) { ... } @else { <app-login /> }`.
  - Add `change-password` tab rendering.
  - Add logout button in sidebar (replace removed security badge area or add as nav item).

- [ ] **2.10** Update `odoo-ui/src/app/app.css` or `styles.css` (optional)
  - Add login page styles if not in component CSS.

- [ ] **2.11** Frontend tests
  - Create `odoo-ui/src/app/services/auth.service.spec.ts`.
  - Create `odoo-ui/src/app/pages/login/login.spec.ts`.
  - Update `odoo-ui/src/app/app.spec.ts` for conditional shell rendering.

- [ ] **2.12** Verify frontend
  - Run `cd odoo-ui && npm run build`.
  - Run `cd odoo-ui && npm test -- --watch=false`.
  - All tests must pass.

### PR-2 / Final

- [ ] **2.13** End-to-end verification
  - Start backend: `cd odoo && .venv/bin/python -m main` or `uvicorn main:app --reload`.
  - Start frontend: `cd odoo-ui && npm start`.
  - Log in with `soporte@gmail.com` / `123456`.
  - Verify tabs are visible after login.
  - Verify change password works.
  - Verify logout returns to login.
  - Verify protected backend endpoints return 401 without cookie.

## Chained PR Recommendation

Because the total changed-line estimate exceeds 400, split into two reviewable PRs:

1. **PR-1: Backend auth foundation** — reviewable, testable, and does not touch frontend.
2. **PR-2: Frontend auth integration** — depends on PR-1; reviewable on its own.

The apply phase should implement PR-1 first, verify, then PR-2, verify.

## Next Recommended Phase

`sdd-apply` — implement the tasks, starting with PR-1 backend auth foundation.
