import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.vcp_routes import router as vcp_router
from app.api.report_routes import router as report_router
from app.api.ingest_routes import router as ingest_router
from app.graph.checkpointer import get_checkpointer, is_configured as checkpointer_configured
from app.store.postgres_json_store import PostgresJsonStore, close_all_pools

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    if checkpointer_configured():
        get_checkpointer()
        # One physical table (app_documents) backs every collection, so a
        # single ensure_table() call provisions it for all stores.
        PostgresJsonStore("_bootstrap").ensure_table()
    else:
        print("DATABASE_URL not set; LangGraph checkpointer and Postgres stores setup skipped.")
    yield
    close_all_pools()


app = FastAPI(title="PE Value Creation Copilot API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174,http://localhost:4173",
    ).split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(vcp_router)
app.include_router(report_router)
app.include_router(ingest_router)


@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": "PE Value Creation Copilot API",
    }
