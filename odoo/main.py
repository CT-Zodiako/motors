from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import catalog, runner, explorer, export, bigquery

app = FastAPI(title="Odoo Bridge API", version="1.0.0")

import os

allowed_origins = ["http://localhost:4200"]
ngrok_origin = os.getenv("NGROK_FRONTEND_URL")
if ngrok_origin:
    allowed_origins.append(ngrok_origin)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(catalog.router)
app.include_router(runner.router)
app.include_router(explorer.router)
app.include_router(export.router)
app.include_router(bigquery.router)


@app.get("/")
def health():
    return {"status": "ok"}
