# SDD Design: `simple-secure-auth`

## Status
`design` — ready for task breakdown.

## 1. Design Goals

- Add a simple, secure email/password auth layer to the existing Motors Odoo Bridge.
- Follow the existing architecture: FastAPI + BigQuery config_store backend, Angular 21 + PrimeNG standalone frontend, no Angular Router.
- Keep the first slice minimal: one seeded admin user, login/logout, change password, route protection.

## 2. Backend Design

### 2.1 New module: `odoo/auth.py`

```python
from fastapi import HTTPException, Request, status
from fastapi.security import APIKeyCookie
from jose import jwt, JWTError
from passlib.context import CryptContext
from datetime import datetime, timedelta, timezone
import os

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
cookie_scheme = APIKeyCookie(name="access_token", auto_error=False)

SECRET_KEY = os.environ.get("SECRET_KEY")
ALGORITHM = "HS256"
TOKEN_TTL_HOURS = int(os.environ.get("AUTH_TOKEN_TTL_HOURS", "24"))
COOKIE_SECURE = os.environ.get("AUTH_COOKIE_SECURE", "false").lower() == "true"

if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY environment variable is required")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(plain_password: str) -> str:
    return pwd_context.hash(plain_password)


def create_access_token(user_id: str, email: str, role: str) -> str:
    now = datetime.now(timezone.utc)
    expire = now + timedelta(hours=TOKEN_TTL_HOURS)
    to_encode = {
        "sub": user_id,
        "email": email,
        "role": role,
        "iat": now,
        "exp": expire,
    }
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


async def get_current_user(request: Request) -> dict:
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    from config_store import get_store
    user = get_store().get_user_by_email(payload["email"])
    if user is None or not user.get("active"):
        raise HTTPException(status_code=401, detail="User not found or inactive")
    return user
```

### 2.2 New router: `odoo/routers/auth.py`

```python
from fastapi import APIRouter, HTTPException, Response, status, Depends
from pydantic import BaseModel
from auth import get_current_user, verify_password, get_password_hash, create_access_token, COOKIE_SECURE

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginIn(BaseModel):
    email: str
    password: str


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str


class UserOut(BaseModel):
    id: str
    email: str
    role: str


@router.post("/login")
def login(body: LoginIn, response: Response):
    from config_store import get_store
    user = get_store().get_user_by_email(body.email)
    if user is None or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = create_access_token(user["id"], user["email"], user["role"])
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
        path="/",
        max_age=24 * 3600,
    )
    return {"user": UserOut(**{k: user[k] for k in ("id", "email", "role")})}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(key="access_token", path="/")
    return {"ok": True}


@router.get("/me", response_model=UserOut)
def me(user: dict = Depends(get_current_user)):
    return {k: user[k] for k in ("id", "email", "role")}


@router.post("/change-password")
def change_password(body: ChangePasswordIn, user: dict = Depends(get_current_user)):
    if body.current_password == body.new_password:
        raise HTTPException(status_code=400, detail="New password must be different from current password")
    if not verify_password(body.current_password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Current password is incorrect")
    from config_store import get_store
    get_store().update_user_password(user["id"], get_password_hash(body.new_password))
    return {"ok": True}
```

### 2.3 `odoo/main.py` changes

```python
from fastapi import Depends
from auth import get_current_user
from routers import auth

app.include_router(auth.router)
app.include_router(catalog.router, dependencies=[Depends(get_current_user)])
app.include_router(categories.router, dependencies=[Depends(get_current_user)])
app.include_router(runner.router, dependencies=[Depends(get_current_user)])
app.include_router(explorer.router, dependencies=[Depends(get_current_user)])
app.include_router(export.router, dependencies=[Depends(get_current_user)])
app.include_router(bigquery.router, dependencies=[Depends(get_current_user)])
app.include_router(file_upload.router, dependencies=[Depends(get_current_user)])
app.include_router(schedules.router, dependencies=[Depends(get_current_user)])

# In startup, after seed_defaults:
# seed_default_user(store)
```

### 2.4 `odoo/config_store/protocol.py` additions

Add under a new `users` section:

```python
def get_user_by_email(self, email: str) -> dict | None: ...
def create_user(self, row: dict) -> dict: ...
def update_user_password(self, user_id: str, password_hash: str) -> dict: ...
def count_users(self) -> int: ...
```

### 2.5 `odoo/config_store/codecs.py` additions

Add to `TABLE_SCHEMAS`:

```python
"odoo_users": [
    {"name": "id", "type": "STRING", "mode": "REQUIRED"},
    {"name": "email", "type": "STRING", "mode": "REQUIRED"},
    {"name": "password_hash", "type": "STRING", "mode": "REQUIRED"},
    {"name": "role", "type": "STRING", "mode": "REQUIRED"},
    {"name": "active", "type": "BOOL", "mode": "REQUIRED"},
    {"name": "created_at", "type": "TIMESTAMP", "mode": "REQUIRED"},
    {"name": "updated_at", "type": "TIMESTAMP", "mode": "REQUIRED"},
],
```

### 2.6 `odoo/config_store/sql.py` additions

```python
def T_USERS():
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

### 2.7 `odoo/config_store/bq_store.py` additions

Add methods to `BigQueryConfigStore`:

```python
def get_user_by_email(self, email: str) -> dict | None:
    rows = self._query(sql.SQL_GET_USER_BY_EMAIL(), [self._string_param("email", email.lower())])
    return codecs.decode_row("odoo_users", rows[0]) if rows else None

def create_user(self, row: dict) -> dict:
    # check duplicate email
    if self._query(sql.SQL_COUNT_USERS(), [self._string_param("email", row["email"].lower())])[0]["n"] > 0:
        raise ConflictError(f"User with email {row['email']} already exists")
    params = self._build_params_for_table("odoo_users", row)
    self._query(sql.SQL_INSERT_USER(), params)
    self._cache.invalidate_users()
    return self.get_user_by_email(row["email"])

def update_user_password(self, user_id: str, password_hash: str) -> dict:
    if self._query(sql.SQL_GET_USER_BY_ID(), [self._string_param("id", user_id)]) is None:
        raise NotFoundError(f"User {user_id} not found")
    params = [
        self._string_param("password_hash", password_hash),
        self._timestamp_param("updated_at", datetime.now(timezone.utc).replace(tzinfo=None)),
        self._string_param("id", user_id),
    ]
    self._query(sql.SQL_UPDATE_USER_PASSWORD(), params)
    self._cache.invalidate_users()
    return self.get_user_by_email(...)  # or get_user_by_id if implemented

def count_users(self) -> int:
    cached = self._cache.get("users_count")
    if cached is not None:
        return cached
    rows = self._query(sql.SQL_COUNT_USERS())
    count = rows[0]["n"]
    self._cache.set("users_count", count)
    return count
```

(Note: `SQL_GET_USER_BY_ID` and `_cache.invalidate_users()` would be added similarly.)

### 2.8 `odoo/config_store/memory_store.py` additions

Mirror the BQ methods using `self._data["odoo_users"]`.

### 2.9 `odoo/config_store/bootstrap.py` or `__init__.py` seeding

Add `seed_default_user(store)` helper:

```python
def seed_default_user(store):
    if store.count_users() == 0:
        from auth import get_password_hash
        store.create_user({
            "id": str(uuid.uuid4()),
            "email": "soporte@gmail.com",
            "password_hash": get_password_hash("123456"),
            "role": "admin",
            "active": True,
            "created_at": datetime.now(timezone.utc).replace(tzinfo=None),
            "updated_at": datetime.now(timezone.utc).replace(tzinfo=None),
        })
```

Call it from `odoo/main.py` startup after `seed_defaults`.

### 2.10 Backend dependencies

Add to `odoo/requirements.txt` (or `.venv`):

```
passlib[bcrypt]
python-jose[cryptography]
python-multipart
```

## 3. Frontend Design

### 3.1 New service: `odoo-ui/src/app/services/auth.ts`

```typescript
export interface User {
  id: string;
  email: string;
  role: 'admin' | 'user';
}

@Injectable({ providedIn: 'root' })
export class AuthService {
  private http = inject(HttpClient);
  private msg = inject(MessageService);
  private base = 'http://localhost:8000';

  user = signal<User | null>(null);
  isAuthenticated = computed(() => this.user() !== null);
  isAdmin = computed(() => this.user()?.role === 'admin');

  login(email: string, password: string): Observable<User> {
    return this.http.post<{ user: User }>(`${this.base}/auth/login`, { email, password }, { withCredentials: true })
      .pipe(tap((res) => this.user.set(res.user)));
  }

  logout(): Observable<void> {
    return this.http.post<void>(`${this.base}/auth/logout`, {}, { withCredentials: true })
      .pipe(tap(() => this.user.set(null)));
  }

  me(): Observable<User> {
    return this.http.get<User>(`${this.base}/auth/me`, { withCredentials: true })
      .pipe(tap((u) => this.user.set(u)));
  }

  changePassword(current_password: string, new_password: string): Observable<void> {
    return this.http.post<void>(`${this.base}/auth/change-password`, { current_password, new_password }, { withCredentials: true });
  }

  handleUnauthorized(): void {
    this.user.set(null);
    this.msg.add({ severity: 'error', summary: 'Sesión expirada', detail: 'Volvé a iniciar sesión' });
  }
}
```

### 3.2 HTTP interceptor: `odoo-ui/src/app/services/auth.interceptor.ts`

```typescript
export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const auth = inject(AuthService);
  const modified = req.clone({ withCredentials: true });
  return next(modified).pipe(
    catchError((err) => {
      if (err.status === 401 || err.status === 403) {
        auth.handleUnauthorized();
      }
      return throwError(() => err);
    })
  );
};
```

Register in `app.config.ts`:

```typescript
provideHttpClient(withInterceptors([authInterceptor]))
```

### 3.3 New component: `odoo-ui/src/app/pages/login/login.ts` and `login.html`

Standalone component with PrimeNG form:
- Email input (`pInputText`).
- Password input (`pPassword` or `pInputText` type password).
- Login button (`p-button`).
- Error message on failure.
- Emits success via `output()` or relies on `AuthService.user` signal.

### 3.4 New component: `odoo-ui/src/app/pages/change-password/change-password.ts` and `change-password.html`

Standalone component with:
- Current password input.
- New password input.
- Confirm new password input.
- Validation: confirm must match new; new must differ from current (also validated backend).
- Submit button.
- Success/error toasts.

### 3.5 `odoo-ui/src/app/app.ts` changes

```typescript
export class App {
  auth = inject(AuthService);
  activeTab = signal<Tab | 'login' | 'change-password'>('list');

  navGroups = [
    // ... existing groups plus:
    {
      label: 'Cuenta',
      items: [
        { id: 'change-password', label: 'Cambiar contraseña', icon: 'pi-lock' },
      ]
    }
  ];

  ngOnInit() {
    this.auth.me().subscribe({ error: () => this.auth.user.set(null) });
  }

  setTab(tab: Tab | 'change-password') {
    this.activeTab.set(tab);
  }
}
```

### 3.6 `odoo-ui/src/app/app.html` changes

```html
@if (auth.isAuthenticated()) {
  <div class="layout">
    <aside class="sidebar">...sidebar with nav items + logout...</aside>
    <main class="content">
      @if (activeTab() === 'list') { ... }
      @if (activeTab() === 'change-password') { <app-change-password /> }
    </main>
  </div>
} @else {
  <app-login />
}
```

Add logout button in the sidebar, perhaps in `sidebar-security` replacement area or as a nav item.

## 4. Testing Design

### 4.1 Backend tests

New file: `odoo/tests/test_auth.py`.

- `conftest.py` should provide a `user` fixture with a seeded user and an `authorized_client` fixture that overrides `get_current_user` for existing router tests.
- Alternatively, update `conftest.py` to always seed the default user and provide a helper cookie for authenticated requests.

### 4.2 Frontend tests

- `auth.service.spec.ts`: mock `HttpTestingController`, test login/logout/me/changePassword.
- `login/login.spec.ts`: test form submission and error handling.
- `app.spec.ts`: test conditional rendering (login vs shell) with mock `AuthService`.

## 5. File Changes Summary

### Backend
- `odoo/auth.py` (new)
- `odoo/routers/auth.py` (new)
- `odoo/main.py` (wire auth, seed user)
- `odoo/config_store/protocol.py` (+users methods)
- `odoo/config_store/codecs.py` (+users schema)
- `odoo/config_store/sql.py` (+users SQL)
- `odoo/config_store/bq_store.py` (+users impl)
- `odoo/config_store/memory_store.py` (+users impl)
- `odoo/config_store/bootstrap.py` or `__init__.py` (+seed_default_user)
- `odoo/config_store/cache.py` (optional: +invalidate_users)
- `odoo/tests/conftest.py` (+seed default user, auth override for existing tests)
- `odoo/tests/test_auth.py` (new)
- `odoo/requirements.txt` (+deps)

### Frontend
- `odoo-ui/src/app/services/auth.ts` (new)
- `odoo-ui/src/app/services/auth.interceptor.ts` (new)
- `odoo-ui/src/app/pages/login/login.ts` (new)
- `odoo-ui/src/app/pages/login/login.html` (new)
- `odoo-ui/src/app/pages/login/login.css` (new)
- `odoo-ui/src/app/pages/change-password/change-password.ts` (new)
- `odoo-ui/src/app/pages/change-password/change-password.html` (new)
- `odoo-ui/src/app/pages/change-password/change-password.css` (new)
- `odoo-ui/src/app/app.ts` (auth integration, tab model)
- `odoo-ui/src/app/app.html` (conditional shell)
- `odoo-ui/src/app/app.config.ts` (+interceptor)
- `odoo-ui/src/styles.css` (optional login styles)
- `odoo-ui/src/app/services/auth.service.spec.ts` (new)
- `odoo-ui/src/app/pages/login/login.spec.ts` (new)
- `odoo-ui/src/app/app.spec.ts` (update)

## 6. Risks and Mitigations

- **JWT secret in env:** startup must fail if `SECRET_KEY` missing.
- **HttpOnly cookie dev/test:** `withCredentials: true` required in Angular and CORS must allow credentials.
- **Existing tests break:** `conftest.py` must seed a default user and override `get_current_user` for all non-auth tests.
- **BigQuery migration:** `ensure_schema` already uses `CREATE TABLE IF NOT EXISTS`, so adding a new table is safe.
- **Token expiration UX:** frontend `handleUnauthorized` on 401 forces re-login.

## 7. Next Recommended Phase

`sdd-tasks` — break the design into implementation tasks with review workload forecast.
