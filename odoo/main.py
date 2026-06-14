from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import catalog, runner, explorer, export

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


@app.get("/")
def health():
    return {"status": "ok"}
