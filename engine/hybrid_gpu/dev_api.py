"""Local development-only approval API. Not suitable for public deployment.
Run: python -m uvicorn engine.hybrid_gpu.dev_api:app --host 127.0.0.1 --port 8765
Requires fastapi and uvicorn. Do not expose this API to the internet.
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from threading import RLock
from uuid import uuid4
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from .policy import Job, Provider, Status, approve, dispatch, reject, submit

app = FastAPI(title="ARKAON GPU Approval Prototype", docs_url=None, redoc_url=None)
_lock = RLock()
_jobs: dict[str, Job] = {}

class NewJob(BaseModel):
    requester_id: str = Field(min_length=1, max_length=128)
    provider: Provider
    estimated_cost_krw: Decimal = Field(ge=0, max_digits=12, decimal_places=2)

class Approval(BaseModel):
    admin_id: str = Field(min_length=1, max_length=128)
    cost_limit_krw: Decimal = Field(ge=0, max_digits=12, decimal_places=2)

def view(job: Job) -> dict:
    return {"id": job.id, "provider": job.provider.value, "status": job.status.value,
            "estimated_cost_krw": str(job.estimated_cost_krw), "approval_id": job.approval_id,
            "approved_by": job.approved_by, "events": job.events}

@app.post("/jobs", status_code=201)
def create_job(body: NewJob):
    with _lock:
        job = submit(str(uuid4()), body.requester_id, body.provider, body.estimated_cost_krw)
        _jobs[job.id] = job
        return view(job)

@app.get("/jobs")
def list_jobs():
    with _lock:
        return [view(j) for j in _jobs.values()]

@app.post("/jobs/{job_id}/approve")
def approve_job(job_id: str, body: Approval):
    with _lock:
        job = _jobs.get(job_id)
        if not job: raise HTTPException(404, "Unknown job")
        try:
            approve(job, body.admin_id, str(uuid4()),
                    (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat(),
                    body.cost_limit_krw)
        except (ValueError, PermissionError) as exc:
            raise HTTPException(409, str(exc))
        return view(job)

@app.post("/jobs/{job_id}/reject")
def reject_job(job_id: str, body: Approval):
    with _lock:
        job = _jobs.get(job_id)
        if not job: raise HTTPException(404, "Unknown job")
        try: reject(job, body.admin_id)
        except PermissionError as exc: raise HTTPException(409, str(exc))
        return view(job)

# Intentionally no dispatch endpoint. Production execution must be protected by
# server-authenticated administrator authorization and one-time worker credentials.
