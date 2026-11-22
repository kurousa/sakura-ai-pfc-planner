from __future__ import annotations

import json
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.ai_client import AIUpstreamError, SakuraAIClient
from app.config import get_settings
from app.schemas import MealPlanOutput, PlanRequest, PlanResponse
from app.storage import Storage

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(
    title="1口IH・高タンパク制約対応 7日間PFC献立ジェネレーター",
    version="0.1.0",
)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@app.get("/")
def serve_index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/status")
def api_status() -> dict[str, object]:
    settings = get_settings()
    storage = Storage(settings.sqlite_db_path)
    used = storage.get_monthly_used()
    return {
        "model": settings.sakura_ai_model,
        "monthly_used": used,
        "monthly_limit": settings.monthly_request_limit,
        "ip_daily_limit": settings.ip_daily_limit,
    }


@app.post("/api/plan", response_model=PlanResponse)
def create_plan(req: PlanRequest, request: Request) -> PlanResponse:
    settings = get_settings()
    storage = Storage(settings.sqlite_db_path)

    cache_key = storage.build_cache_key(req, settings.sakura_ai_model)
    cached = storage.get_cached_plan(cache_key)
    if cached:
        cached_json, cached_model = cached
        payload = json.loads(cached_json)
        if "plan" in payload:
            plan = MealPlanOutput.model_validate(payload["plan"])
            warnings = payload.get("warnings", [])
        else:
            plan = MealPlanOutput.model_validate(payload)
            warnings = []
        return PlanResponse(
            plan=plan,
            warnings=warnings,
            cached=True,
            retried=False,
            model=cached_model,
            monthly_used=storage.get_monthly_used(),
            monthly_limit=settings.monthly_request_limit,
        )

    client_ip = _get_client_ip(request)
    limit_error = storage.check_rate_limits(
        ip=client_ip,
        monthly_limit=settings.monthly_request_limit,
        ip_daily_limit=settings.ip_daily_limit,
        ip_minute_limit=settings.ip_minute_limit,
    )
    if limit_error:
        raise HTTPException(status_code=429, detail=limit_error)

    try:
        ai = SakuraAIClient(settings)
        plan, warnings, retried, upstream_calls = ai.generate_plan(req)
    except AIUpstreamError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    storage.record_usage(client_ip, upstream_calls=upstream_calls)
    cache_payload = json.dumps(
        {"plan": plan.model_dump(), "warnings": warnings},
        ensure_ascii=False,
    )
    storage.save_cached_plan(cache_key, cache_payload, settings.sakura_ai_model)

    return PlanResponse(
        plan=plan,
        warnings=warnings,
        cached=False,
        retried=retried,
        model=settings.sakura_ai_model,
        monthly_used=storage.get_monthly_used(),
        monthly_limit=settings.monthly_request_limit,
    )
