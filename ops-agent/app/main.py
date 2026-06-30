import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import JSONResponse

from app import __version__
from app.config import get_settings
from app.graph.runner import (
    resume_approval,
    resume_runbook_notes,
    resume_runbook_review,
    start_diagnosis,
)
from app.observability.metrics import RUN_LATENCY, metrics_payload
from app.observability.tracing import init_langsmith
from app.schemas import (
    ApproveRequest,
    DiagnoseRequest,
    RunbookNotesRequest,
    RunbookReviewRequest,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    init_langsmith(settings)
    logger.info(
        "ops-agent starting version=%s backend=%s llm=%s",
        __version__,
        settings.backend_mode,
        settings.llm_mode,
    )
    yield
    logger.info("ops-agent shutdown")


app = FastAPI(
    title="ops-agent",
    version=__version__,
    description="Ops diagnosis and remediation agent",
    lifespan=lifespan,
)


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok", "version": __version__}


@app.get("/readyz")
async def readyz() -> dict:
    settings = get_settings()
    return {
        "status": "ready",
        "backend_mode": settings.backend_mode,
        "llm_mode": settings.llm_mode,
    }


@app.get("/metrics")
async def metrics() -> Response:
    body, content_type = metrics_payload()
    return Response(content=body, media_type=content_type)


@app.post("/diagnose")
async def diagnose(body: DiagnoseRequest):
    import time

    start = time.perf_counter()
    thread_id, response, meta = start_diagnosis(body.incident)
    RUN_LATENCY.observe(time.perf_counter() - start)
    payload = response.model_dump(mode="json")
    payload["meta"] = meta
    return payload


@app.post("/approve")
async def approve(body: ApproveRequest):
    try:
        response = resume_approval(body.thread_id, body.approved, body.comment)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return response.model_dump(mode="json")


@app.post("/runbooks/notes")
async def submit_runbook_notes(body: RunbookNotesRequest):
    try:
        response = resume_runbook_notes(body.thread_id, body.notes)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return response.model_dump(mode="json")


@app.post("/runbooks/review")
async def review_runbook(body: RunbookReviewRequest):
    try:
        response = resume_runbook_review(body.thread_id, body.approved, body.comment)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return response.model_dump(mode="json")


@app.get("/runs/{thread_id}")
async def get_run(thread_id: str):
    from app.graph.builder import build_graph

    graph = build_graph()
    config = {"configurable": {"thread_id": thread_id}}
    snapshot = graph.get_state(config)
    if not snapshot or not snapshot.values:
        raise HTTPException(status_code=404, detail="run not found")
    return {"thread_id": thread_id, "state": snapshot.values, "next": snapshot.next}


@app.get("/")
async def root() -> JSONResponse:
    return JSONResponse(
        {
            "service": "ops-agent",
            "version": __version__,
            "endpoints": [
                "/healthz",
                "/readyz",
                "/metrics",
                "/diagnose",
                "/approve",
                "/runbooks/notes",
                "/runbooks/review",
                "/runs",
            ],
        }
    )
