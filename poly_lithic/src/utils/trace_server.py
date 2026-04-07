"""Standalone FastAPI server for querying message trace records."""

import threading
from dataclasses import asdict

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from .trace_store import TraceStore

_VIEWER_HTML = None


def _load_viewer_html():
    global _VIEWER_HTML
    if _VIEWER_HTML is None:
        import pathlib
        p = pathlib.Path(__file__).with_name("trace_viewer.html")
        _VIEWER_HTML = p.read_text()
    return _VIEWER_HTML


def create_trace_app(trace_store: TraceStore) -> FastAPI:
    """Create a FastAPI app wired to the given TraceStore."""
    app = FastAPI(title="Poly-Lithic Tracing API")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"])

    @app.get("/", response_class=HTMLResponse)
    def viewer():
        return _load_viewer_html()

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/traces")
    def get_traces(limit: int = 100):
        records = trace_store.get_recent(limit)
        return [asdict(r) for r in records]

    @app.get("/traces/{trace_id}")
    def get_trace(trace_id: str):
        record = trace_store.get(trace_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Trace not found")
        return asdict(record)

    @app.get("/traces/{trace_id}/lineage")
    def get_lineage(trace_id: str):
        records = trace_store.get_lineage(trace_id)
        if not records:
            raise HTTPException(status_code=404, detail="Trace not found")
        return [asdict(r) for r in records]

    return app


def start_trace_server(trace_store: TraceStore, port: int = 8100) -> threading.Thread:
    """Start the tracing FastAPI server in a background daemon thread."""
    app = create_trace_app(trace_store)

    def _run():
        uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")

    thread = threading.Thread(target=_run, name="trace-server", daemon=True)
    thread.start()
    return thread
