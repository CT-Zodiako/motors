from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import catalog, runner, explorer, export, bigquery, schedules

app = FastAPI(title="Odoo Bridge API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(catalog.router)
app.include_router(runner.router)
app.include_router(explorer.router)
app.include_router(export.router)
app.include_router(bigquery.router)
app.include_router(schedules.router)

@app.on_event("startup")
def startup():
    schedules.start_scheduler()

@app.on_event("shutdown")
def shutdown():
    scheduler = schedules.get_scheduler()
    if scheduler.running:
        scheduler.shutdown(wait=False)


@app.get("/")
def health():
    return {"status": "ok"}
