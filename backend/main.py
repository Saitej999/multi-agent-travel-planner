"""Single-process local API. Jobs and their results disappear on restart."""

import asyncio
from dataclasses import dataclass, field
from typing import Literal
from uuid import uuid4

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from travel_core.api_schemas import (BudgetEstimateRequest, PlanTripRequest,
                                     TripPlanResponse, plan_response,
                                     recalculate_trip_estimates)
from travel_core.config import gemini_key_available, model_name
from travel_core.geo import GeographicDataError, ResolvedLocation, search_cities
from travel_planner.runner import WorkflowRunError, run_adk_trip


app = FastAPI(title='Multi-Agent Travel Planner', version='1.0.0')
app.add_middleware(
    CORSMiddleware,
    allow_origins=['http://localhost:5173', 'http://127.0.0.1:5173'],
    allow_methods=['GET', 'POST'],
    allow_headers=['Content-Type'],
)


class ApiError(BaseModel):
    code: str
    message: str
    diagnostics: dict | None = None


class ProgressEvent(BaseModel):
    agent: str
    event: str
    tool: str | None = None
    count: int | None = None


class JobStatus(BaseModel):
    trip_id: str
    status: Literal['queued', 'running', 'completed', 'failed']
    progress: list[ProgressEvent] = Field(default_factory=list)
    error: ApiError | None = None


@dataclass
class LocalJob:
    trip_id: str
    status: Literal['queued', 'running', 'completed', 'failed'] = 'queued'
    progress: list[ProgressEvent] = field(default_factory=list)
    result: TripPlanResponse | None = None
    error: ApiError | None = None

    def public_status(self) -> JobStatus:
        return JobStatus(trip_id=self.trip_id, status=self.status,
                         progress=self.progress.copy(), error=self.error)


_jobs: dict[str, LocalJob] = {}
_tasks: set[asyncio.Task] = set()


def _error_for(exc: Exception) -> ApiError:
    detail = str(exc).lower()
    if 'api_key_invalid' in detail or 'invalid api key' in detail or '401' in detail:
        return ApiError(code='invalid_gemini_key',
                        message='The Gemini API key was rejected. Check the backend environment.')
    if 'resource_exhausted' in detail or 'quota' in detail or '429' in detail:
        return ApiError(code='gemini_quota',
                        message='The Gemini free-tier quota or rate limit was reached. Try later.')
    if 'high demand' in detail or '503 unavailable' in detail:
        return ApiError(code='gemini_unavailable',
                        message='The selected Gemini model is temporarily busy. Try again later.')
    if 'no longer available' in detail or ('model' in detail and '404 not_found' in detail):
        return ApiError(code='gemini_model_unavailable',
                        message='The selected Gemini model is unavailable to this key. Choose an available free-tier model.')
    if 'exceeded' in detail or isinstance(exc, TimeoutError):
        return ApiError(code='workflow_timeout',
                        message='The AI planning run took too long. Try again later.')
    if 'location service' in detail or isinstance(exc, GeographicDataError):
        return ApiError(code='geographic_service',
                        message='City or attraction data is temporarily unavailable.')
    if 'missing upstream results' in detail or 'did not execute python tools' in detail:
        return ApiError(code='missing_specialist_result',
                        message='A travel planning stage did not return the data needed for a complete plan.')
    if 'connect' in detail or 'network' in detail:
        return ApiError(code='network_error',
                        message='The backend could not reach a required service. Try again later.')
    return ApiError(code='workflow_failed',
                    message='The travel plan could not be completed. Try again.')


async def _run_job(job: LocalJob, request: PlanTripRequest) -> None:
    job.status = 'running'

    def observed_progress(raw: dict) -> None:
        try:
            job.progress.append(ProgressEvent.model_validate(raw))
        except Exception:
            # A malformed display event must never change the ADK result.
            pass

    try:
        result = await run_adk_trip(request.to_trip_request(), timeout_seconds=180,
                                    on_progress=observed_progress)
        job.result = plan_response(request, result)
    except Exception as exc:
        job.error = _error_for(exc)
        if isinstance(exc, WorkflowRunError):
            job.error.diagnostics = {
                'trace': exc.trace, 'timings': exc.timings,
                'model_metrics': exc.model_metrics, 'tool_metrics': exc.tool_metrics,
            }
        job.status = 'failed'
    else:
        job.status = 'completed'


@app.get('/api/health')
def health() -> dict:
    return {'status': 'ok', 'model': model_name(),
            'gemini_configured': gemini_key_available()}


@app.get('/api/locations/search', response_model=list[ResolvedLocation],
         responses={503: {'model': ApiError}})
async def locations_search(q: str = Query(min_length=2, max_length=60)):
    try:
        return await asyncio.to_thread(search_cities, q)
    except GeographicDataError:
        return JSONResponse(status_code=503, content=ApiError(
            code='geographic_service',
            message='City lookup is temporarily unavailable. Try again later.').model_dump())


@app.post('/api/trips/plan', response_model=JobStatus, status_code=202,
          responses={503: {'model': ApiError}})
async def plan_trip(request: PlanTripRequest):
    if not gemini_key_available():
        return JSONResponse(status_code=503, content=ApiError(
            code='missing_gemini_key',
            message='Gemini is not configured. Set GOOGLE_API_KEY in the backend environment.').model_dump())
    job = LocalJob(trip_id=uuid4().hex)
    _jobs[job.trip_id] = job
    task = asyncio.create_task(_run_job(job, request))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return job.public_status()


@app.get('/api/trips/{trip_id}/status', response_model=JobStatus,
         responses={404: {'model': ApiError}})
def trip_status(trip_id: str):
    job = _jobs.get(trip_id)
    if job is None:
        return JSONResponse(status_code=404, content=ApiError(
            code='trip_not_found', message='This trip job was not found.').model_dump())
    return job.public_status()


@app.get('/api/trips/{trip_id}/result', response_model=TripPlanResponse,
         responses={202: {'model': JobStatus}, 404: {'model': ApiError},
                    409: {'model': ApiError}})
def trip_result(trip_id: str):
    job = _jobs.get(trip_id)
    if job is None:
        return JSONResponse(status_code=404, content=ApiError(
            code='trip_not_found', message='This trip job was not found.').model_dump())
    if job.status == 'failed':
        return JSONResponse(status_code=409, content=job.error.model_dump(mode='json'))
    if job.result is None:
        return JSONResponse(status_code=202,
                            content=job.public_status().model_dump(mode='json'))
    return job.result


@app.post('/api/trips/{trip_id}/budget', response_model=TripPlanResponse,
          responses={404: {'model': ApiError}, 409: {'model': ApiError}})
def update_trip_budget(trip_id: str, estimates: BudgetEstimateRequest):
    job = _jobs.get(trip_id)
    if job is None:
        return JSONResponse(status_code=404, content=ApiError(
            code='trip_not_found', message='This trip job was not found.').model_dump())
    if job.result is None:
        return JSONResponse(status_code=409, content=ApiError(
            code='trip_not_ready', message='The trip plan is not ready for budget updates.').model_dump())
    try:
        job.result = recalculate_trip_estimates(job.result, estimates)
    except ValueError as exc:
        return JSONResponse(status_code=409, content=ApiError(
            code='estimate_not_applicable', message=str(exc)).model_dump())
    return job.result
