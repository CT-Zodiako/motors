# SDD Proposal: `simple-secure-auth`

## Status
`proposal` — ready for product/technical review.

## Executive Summary
Add a simple, secure authentication layer to the Motors Odoo Bridge so that only authenticated users can access backend functionality and the frontend shell. The solution uses **JWT access tokens stored in HttpOnly cookies**, a **BigQuery `users` table in the existing `config_store` schema**, and two roles (`admin`, `user`). The Angular tab-based shell will show a login form when the user is not authenticated and render the normal tabs after login. All backend routes except health and auth endpoints will require a valid token.

## Intent
The system currently exposes all backend routes and frontend features without authentication. This change introduces a lightweight identity layer to prevent unauthorized access while keeping the user experience simple and aligned with the existing FastAPI + BigQuery / Angular 21 + PrimeNG stack.

## Scope

### In Scope
- **Backend**
  - Create `users` table in the `config_store` schema.
  - Seed one user at startup: `soporte@gmail.com` / `123456` with role `admin`.
  - Implement password hashing (bcrypt).
  - Implement `/auth/login` and `/auth/logout` endpoints.
  - Issue JWT as an `HttpOnly`, `Secure`, `SameSite=Lax` cookie.
  - Add a FastAPI dependency to verify JWT on protected routes.
  - Protect all routers except `/health` and `/auth/*`.
  - Support roles `admin` and `user`.
  - Update the in-memory store fixture and add auth tests.
- **Frontend**
  - Create `LoginComponent` and `AuthService`.
  - Update `AppComponent` to show login when not authenticated and tabs when authenticated.
  - Add logout affordance.
  - Handle 401 responses by forcing re-login.

### Out of Scope
- Password reset / forgot password
- OAuth or third-party identity providers
- Password complexity rules (per decision: only must be different from current)
- Refresh token rotation
- User self-registration UI
- Role-based UI differences beyond the admin/user distinction (first slice only enforces authentication; admin-only features are deferred)

## Affected Areas

### Backend
| File / Path | Change |
| --- | --- |
| `odoo/routers/auth.py` | New login/logout endpoints |
| `odoo/auth.py` | New JWT creation, verification, and password hashing utilities |
| `odoo/main.py` | Mount auth router; apply auth dependency to all other routers |
| `odoo/config_store/codecs.py` | Add `users` table schema |
| `odoo/config_store/sql.py` | Add user SQL templates |
| `odoo/config_store/protocol.py` | Add user methods to `ConfigStore` Protocol |
| `odoo/config_store/bigquery.py` | Implement user methods |
| `odoo/config_store/memory.py` | Implement user methods for tests |
| `odoo/config_store/__init__.py` | Seed default user on startup if table empty |
| `odoo/routers/*.py` | Apply `Depends(get_current_user)` via router-level dependency |
| `tests/conftest.py` | Update in-memory fixture to include users |
| `tests/test_auth.py` | New login/logout/protection tests |

### Frontend
| File / Path | Change |
| --- | --- |
| `odoo-ui/src/app/login/login.ts` | New login component |
| `odoo-ui/src/app/login/login.html` | New login template |
| `odoo-ui/src/app/services/auth.service.ts` | New auth service |
| `odoo-ui/src/app/app.ts` | Auth state signal; conditional shell |
| `odoo-ui/src/app/app.html` | Login vs. tabs conditional rendering |
| `odoo-ui/src/styles.scss` | Optional login styling |

## Architecture & Design Decisions

### Token Strategy
- JWT stored in an `HttpOnly` cookie to mitigate XSS.
- Cookie attributes: `HttpOnly`, `Secure` (in production), `SameSite=Lax`, `Path=/`.
- Token payload: `sub` (user id), `email`, `role`, `iat`, `exp`.
- Access token TTL: 24 hours, configurable via `AUTH_TOKEN_TTL_HOURS`.

### Password Rules
- The only enforced rule is that a new password must differ from the current password.
- No complexity requirements.
- Passwords stored as bcrypt hashes.

### User Storage
- `users` table in the existing `config_store` schema.
- Columns: `id` (STRING), `email` (STRING), `password_hash` (STRING), `role` (STRING), `active` (BOOL), `created_at` (TIMESTAMP), `updated_at` (TIMESTAMP).
- Seed at startup if no users exist.

### Roles
- `admin`: full access.
- `user`: standard access (same routes in the first slice; role-based restrictions can be added later).

### Route Protection
- Backend: apply FastAPI dependency at router inclusion time so all routes in all routers (except auth and health) are protected.
- Frontend: shell renders login when `AuthService` reports not authenticated; otherwise renders tabs.

## Rollback
- Revert the deployment.
- Optionally drop the `users` table.
- Clear the auth cookie by issuing a `/auth/logout` or removing the cookie clientside.

## Success Criteria
- `/auth/login` returns a cookie and user info on valid credentials; returns 401 on invalid credentials.
- `/auth/logout` clears the cookie.
- All non-auth/non-health routes return 401 without a valid cookie.
- Frontend shows login when not authenticated; shows tabs after successful login.
- Seeded user can log in with `soporte@gmail.com` / `123456`.
- Backend tests cover login, logout, route protection, and user seeding.

## Risks
1. **JWT secret management**: If `SECRET_KEY` is weak or hardcoded, tokens can be forged.  
   *Mitigation:* load from environment; fail startup if missing.
2. **Cookie security**: Without correct `Secure`/`SameSite` attributes, cookies are vulnerable.  
   *Mitigation:* configure cookie attributes via environment; default to `HttpOnly` + `SameSite=Lax`.
3. **Route protection gaps**: If the dependency is not applied consistently, routes may remain open.  
   *Mitigation:* apply dependency at the router inclusion level in `main.py`.
4. **Frontend auth state desync**: User might see tabs after the cookie expires.  
   *Mitigation:* 401 handler forces re-login.
5. **BigQuery migration**: Adding the `users` table must not break existing tables.  
   *Mitigation:* use `CREATE TABLE IF NOT EXISTS`.

## Artifacts
- `openspec/changes/simple-secure-auth/proposal.md` (this document)
- Implementation artifacts listed under **Affected Areas**

## Next Recommended Phase
`sdd-spec` — write detailed specs before design and implementation.

## Skill Resolution
`none` — no project/user skill paths were injected for this phase.
