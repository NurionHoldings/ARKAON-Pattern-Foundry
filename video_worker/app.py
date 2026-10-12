"""Private GPU-worker control plane. No public video generation endpoint."""
import hmac
import os
import uuid
from pathlib import Path
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(title="ARKAON Private Video Worker", docs_url=None, redoc_url=None)
JOBS = {}
ROOT = Path(os.environ.get("ARKAON_VIDEO_OUTPUT_DIR", "/tmp/arkaon-video")).resolve()
MAX_JOBS = int(os.environ.get("ARKAON_MAX_JOBS", "1"))

class Request(BaseModel):
    image_path: str = Field(min_length=1, max_length=1024)
    prompt: str = Field(min_length=1, max_length=2000)
    duration_seconds: int = Field(default=5, ge=1, le=10)
    approved_budget_krw: int = Field(ge=0, le=100000)

def authorize(token):
    expected = os.environ.get("ARKAON_WORKER_TOKEN")
    if not expected or not token or not hmac.compare_digest(token, expected):
        raise HTTPException(401, "Unauthorized")

@app.get("/health")
def health():
    return {"status": "ready", "generation_enabled": False}

@app.post("/jobs", status_code=202)
def create_job(req: Request, x_worker_token: str | None = Header(default=None)):
    authorize(x_worker_token)
    if os.environ.get("ARKAON_VIDEO_GENERATION_ENABLED") != "1":
        raise HTTPException(503, "Generation disabled until GPU model, billing cap and storage are configured")
    # Fail closed: real inference and persistent queue must be installed before enabling.
    raise HTTPException(501, "Inference backend not configured")

@app.get("/jobs/{job_id}")
def get_job(job_id: uuid.UUID, x_worker_token: str | None = Header(default=None)):
    authorize(x_worker_token)
    job = JOBS.get(str(job_id))
    if not job:
        raise HTTPException(404, "Job not found")
    return job
