from dotenv import load_dotenv
load_dotenv()

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import admin, auth, bigquery, catalog, categories, explorer, export, file_upload, runner, schedules
from auth import get_current_user

app = FastAPI(title="Odoo Bridge API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

app.include_router(auth.router)
app.include_router(admin.router, dependencies=[Depends(get_current_user)])
app.include_router(catalog.router, dependencies=[Depends(get_current_user)])
app.include_router(categories.router, dependencies=[Depends(get_current_user)])
app.include_router(runner.router, dependencies=[Depends(get_current_user)])
app.include_router(explorer.router, dependencies=[Depends(get_current_user)])
app.include_router(export.router, dependencies=[Depends(get_current_user)])
app.include_router(bigquery.router, dependencies=[Depends(get_current_user)])
app.include_router(file_upload.router, dependencies=[Depends(get_current_user)])
app.include_router(schedules.router, dependencies=[Depends(get_current_user)])

import logging

logger = logging.getLogger(__name__)

@app.on_event("startup")
def startup():
    # WU6: bootstrap BigQueryConfigStore directly; PostgreSQL is no longer used.
    import time
    from config_store.bootstrap import ensure_schema, seed_defaults
    from config_store.bq_store import BigQueryConfigStore
    from config_store import set_store

    for attempt in range(1, 4):
        try:
            _config_store = BigQueryConfigStore()
            ensure_schema(_config_store)
            seed_defaults(_config_store)
            set_store(_config_store)
            from auth import get_password_hash
            from auth_seed import seed_default_user
            seed_default_user(_config_store, get_password_hash)
            _config_store.seed_permission_defaults()
            logger.info("config_store bootstrap OK (BigQueryConfigStore)")
            break
        except Exception as e:
            logger.warning("config_store bootstrap attempt %d failed: %s", attempt, e)
            if attempt == 3:
                raise
            time.sleep(2)
    schedules.start_scheduler()

@app.on_event("shutdown")
def shutdown():
    scheduler = schedules.get_scheduler()
    if scheduler.running:
        scheduler.shutdown(wait=False)


@app.get("/")
def health():
    return {"status": "ok"}
