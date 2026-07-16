from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import bigquery, catalog, categories, explorer, export, file_upload, runner, schedules

app = FastAPI(title="Odoo Bridge API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(catalog.router)
app.include_router(categories.router)
app.include_router(runner.router)
app.include_router(explorer.router)
app.include_router(export.router)
app.include_router(bigquery.router)
app.include_router(file_upload.router)
app.include_router(schedules.router)

import logging

logger = logging.getLogger(__name__)

@app.on_event("startup")
def startup():
    # WU4: bootstrap config_store and wire BigQueryConfigStore for production.
    import time
    import init_db
    from config_store.bootstrap import ensure_schema, seed_defaults
    from config_store.bq_store import BigQueryConfigStore
    from config_store import set_store

    for attempt in range(1, 4):
        try:
            init_db.init()
            _config_store = BigQueryConfigStore()
            ensure_schema(_config_store)
            seed_defaults(_config_store)
            set_store(_config_store)
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
