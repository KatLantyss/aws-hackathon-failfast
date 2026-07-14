"""
FastAPI wrapper around handler.py
Maps each HTTP route to the corresponding handler function via the Lambda-style
route() dispatcher, so no business logic is duplicated here.
"""
import json

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import handler

app = FastAPI(title="Ship Performance Analysis API", version="1.0.0")


@app.on_event("startup")
async def startup_event():
    """Prefetch all DynamoDB data into cache in background on server start."""
    handler.start_warmup()

# CORS – allow all origins (adjust in production as needed)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── helpers ───────────────────────────────────────────────────────────────────

def _json_response(result: dict) -> JSONResponse:
    """Convert a Lambda-style response dict into a FastAPI JSONResponse."""
    return JSONResponse(
        content=json.loads(result["body"]),
        status_code=result["statusCode"],
    )


def _event(method: str, path: str, query_params: dict | None = None, body: str | None = None) -> dict:
    """Build a minimal Lambda event dict."""
    return {
        "httpMethod": method,
        "path": path,
        "queryStringParameters": query_params or {},
        "body": body,
    }


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    result = handler.route(_event("GET", "/health"), None)
    return _json_response(result)


@app.get("/api/v1/vessels")
def get_vessels():
    result = handler.route(_event("GET", "/api/v1/vessels"), None)
    return _json_response(result)


@app.get("/api/v1/vessels/{vessel_id}")
def get_vessel_detail(vessel_id: str):
    result = handler.route(_event("GET", f"/api/v1/vessels/{vessel_id}"), None)
    return _json_response(result)


@app.get("/api/v1/vessels/{vessel_id}/noon-reports")
def get_noon_reports(vessel_id: str, limit: int = 100, voyage: str | None = None):
    qs: dict = {"limit": str(limit)}
    if voyage is not None:
        qs["voyage"] = voyage
    result = handler.route(
        _event("GET", f"/api/v1/vessels/{vessel_id}/noon-reports", query_params=qs),
        None,
    )
    return _json_response(result)


@app.get("/api/v1/vessels/{vessel_id}/speed-loss")
def get_speed_loss(vessel_id: str):
    result = handler.route(
        _event("GET", f"/api/v1/vessels/{vessel_id}/speed-loss"),
        None,
    )
    return _json_response(result)


@app.get("/api/v1/vessels/{vessel_id}/speed-loss-attribution")
def get_speed_loss_attribution(vessel_id: str):
    result = handler.route(
        _event("GET", f"/api/v1/vessels/{vessel_id}/speed-loss-attribution"),
        None,
    )
    return _json_response(result)


@app.get("/api/v1/vessels/{vessel_id}/maintenance-events")
def get_maintenance_events(vessel_id: str):
    result = handler.route(
        _event("GET", f"/api/v1/vessels/{vessel_id}/maintenance-events"),
        None,
    )
    return _json_response(result)


@app.get("/api/v1/vessels/{vessel_id}/maintenance-recommendation")
def get_maintenance_recommendation(vessel_id: str):
    result = handler.route(
        _event("GET", f"/api/v1/vessels/{vessel_id}/maintenance-recommendation"),
        None,
    )
    return _json_response(result)


@app.get("/api/v1/fleet/ranking")
def get_fleet_ranking():
    result = handler.route(_event("GET", "/api/v1/fleet/ranking"), None)
    return _json_response(result)


@app.get("/api/v1/fleet/summary")
def get_fleet_summary():
    result = handler.route(_event("GET", "/api/v1/fleet/summary"), None)
    return _json_response(result)


@app.post("/api/v1/predict/fuel-consumption")
async def predict_fuel(request: Request):
    body = await request.body()
    result = handler.route(
        _event("POST", "/api/v1/predict/fuel-consumption", body=body.decode()),
        None,
    )
    return _json_response(result)
