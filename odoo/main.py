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
    # WU1: bootstrap config_store alongside new init_db wiring (init_db removed in WU4).
    # The InMemoryConfigStore here is intentionally a shadow-run for WU1 —
    # no router consumes it yet; WU4 will replace it with BigQueryConfigStore.
    import time
    import init_db
    from config_store.bootstrap import ensure_schema, seed_defaults
    from config_store.memory_store import InMemoryConfigStore

    for attempt in range(1, 4):
        try:
            init_db.init()
            _config_store = InMemoryConfigStore()
            ensure_schema(_config_store)
            seed_defaults(_config_store)
            logger.info("config_store bootstrap OK (shadow-run, memory)")
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
