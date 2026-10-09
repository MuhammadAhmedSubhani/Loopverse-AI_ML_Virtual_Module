"""FastAPI backend. Run: uvicorn app.main:app --port 8000"""
import csv, io, os
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ConfigDict, field_validator
from . import llm, rules as X
from .engine import Engine
from .store import Store

app = FastAPI(title="ARES ACCORD API", version="2.0.0", description="Auditable multi-agent Mars-colony resource negotiation with deterministic safety validation.", docs_url="/docs", redoc_url="/redoc")
app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in os.environ.get("ARES_CORS", "http://localhost:8000,http://127.0.0.1:8000").split(",") if o.strip()], allow_methods=["*"], allow_headers=["*"])
engine = Engine(Store(os.environ.get("ARES_DB", "ares.db")))


@app.middleware("http")
async def security_headers(request: Request, call_next):
    """Add safe defaults without breaking the local dashboard or API docs."""
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault("Cache-Control", "no-store" if request.url.path.startswith("/api/") else "no-cache")
    return response


class StartIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pool: List[int] = Field(default_factory=lambda: [79, 52, 59, 26, 17], min_length=5, max_length=5)
    policy: str = "bal"  # bal | hab | rep
    risk_limit: int = Field(default=24, ge=0, le=100)
    max_sacrifices: int = Field(default=1, ge=0, le=4)

    @field_validator("pool", mode="before")
    @classmethod
    def valid_pool(cls, value):
        if any(type(v) is not int or not 0 <= v <= 999 for v in value):
            raise ValueError("each resource pool value must be an integer from 0 to 999")
        return value

    @field_validator("policy")
    @classmethod
    def valid_policy(cls, value):
        if value not in {"bal", "hab", "rep"}:
            raise ValueError("policy must be bal, hab, or rep")
        return value


class EventImpact(BaseModel):
    """Official starter-kit event impact fields."""
    model_config = ConfigDict(extra="allow")
    power_reduction_percent: Optional[float] = Field(default=None, ge=0, le=100)
    duration_hours: Optional[float] = Field(default=None, gt=0, le=8760)
    affected_systems: List[str] = Field(default_factory=list, max_length=50)


class EventIn(BaseModel):
    """Accept both the official structured event envelope and the dashboard delta shortcut."""
    model_config = ConfigDict(extra="forbid")
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    event_id: Optional[str] = Field(default=None, max_length=120)
    event_name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    trigger_time: Optional[str] = Field(default=None, max_length=120)
    description: Optional[str] = Field(default=None, max_length=2000)
    impact: Optional[EventImpact] = None
    requires_replan: bool = True
    message_to_commander: Optional[str] = Field(default=None, max_length=2000)
    delta: Optional[List[int]] = Field(default=None, min_length=5, max_length=5)
    allow_override: bool = True
    risk_limit: Optional[int] = Field(default=None, ge=0, le=100)
    max_sacrifices: Optional[int] = Field(default=None, ge=0, le=4)

    @field_validator("delta", mode="before")
    @classmethod
    def valid_delta(cls, value):
        if value is not None and (not isinstance(value, list) or
                                  any(type(v) is not int or not -999 <= v <= 999 for v in value)):
            raise ValueError("each resource delta must be an integer from -999 to 999")
        return value

    def normalized(self, current_pool):
        event_name = self.event_name or self.name or self.event_id or "Unnamed emergency"
        if self.delta is not None:
            delta = self.delta
        elif self.impact and self.impact.power_reduction_percent is not None:
            # Translate the official temporary capacity shock into a conservative power-pool reduction.
            import math
            current = current_pool[0]
            remaining = math.floor(current * (1 - self.impact.power_reduction_percent / 100))
            delta = [remaining - current, 0, 0, 0, 0]
        else:
            raise ValueError("provide delta[5] or official impact.power_reduction_percent")
        details = {
            "event_id": self.event_id,
            "event_name": event_name,
            "trigger_time": self.trigger_time,
            "description": self.description,
            "impact": self.impact.model_dump() if self.impact else None,
            "requires_replan": self.requires_replan,
            "message_to_commander": self.message_to_commander,
            "affected_systems": self.impact.affected_systems if self.impact else [],
        }
        return event_name, delta, details


class LLMIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: Optional[str] = Field(default=None, min_length=1, max_length=40)
    model: Optional[str] = Field(default=None, min_length=1, max_length=160)
    api_key: Optional[str] = Field(default=None, max_length=4096)
    base: Optional[str] = Field(default=None, max_length=500)
    enabled: Optional[bool] = None


@app.get("/api/llm")
def llm_info(): return {**llm.info(), "presets": {k: dict(model=v["model"], base=v["base"]) for k, v in llm.PRESETS.items()}}

@app.post("/api/llm/config")
def llm_config(b: LLMIn): return llm.set_config(b.provider, b.model, b.api_key, b.base, b.enabled)  # key kept in server memory only

@app.post("/api/llm/test")
def llm_test(): return llm.test()

@app.get("/api/health", tags=["operations"])
def health():
    return {"ok": True}


@app.get("/api/ready", tags=["operations"])
def readiness():
    """Liveness/readiness summary suitable for local demos and container probes."""
    s = engine.snapshot()
    return {"ready": True, "running": bool(s.get("running")), "status": s.get("status", "UNKNOWN"),
            "llm_enabled": bool(llm.info().get("enabled")), "storage": "sqlite"}


@app.get("/api/metrics", tags=["observability"])
def metrics():
    """Small, derived run summary; no secrets or prompt content are exposed."""
    s = engine.snapshot()
    plan = s.get("plan") if isinstance(s.get("plan"), dict) else None
    totals = X.tot(plan["sel"]) if plan and isinstance(plan.get("sel"), dict) and all(k in plan["sel"] for k in X.K) else None
    pool = s.get("pool", [])
    reserve = [pool[i] - totals[i] for i in range(5)] if totals and len(pool) == 5 else None
    transcript = engine.store.messages()
    return {"status": s.get("status"), "running": bool(s.get("running")),
            "scenario": s.get("scen"), "round": s.get("round", 0),
            "plan_version": plan.get("ver") if plan else None,
            "plan_status": plan.get("status") if plan else None,
            "validation_pass": bool(s.get("vr")) and X.ok_all(s["vr"]),
            "resources": dict(zip(X.R, pool)) if len(pool) == 5 else {},
            "allocation": dict(zip(X.R, totals)) if totals else None,
            "reserve": dict(zip(X.R, reserve)) if reserve else None,
            "transcript_messages": len(transcript),
            "llm_enabled": bool(llm.info().get("enabled"))}

@app.get("/api/modes")
def modes(): return dict(R=X.R, K=X.K, M=X.M, GOAL=X.GOAL, LOSS=X.LOSS, RET=X.RET)

@app.get("/api/state")
def state(): return engine.snapshot()

@app.get("/api/transcript")
def transcript(since: int = Query(default=0, ge=0)): return engine.store.messages(since)

@app.post("/api/start")
def start(b: StartIn):
    try: engine.start(b.pool, b.policy, lim=b.risk_limit, sac=b.max_sacrifices)
    except RuntimeError as e: raise HTTPException(409, str(e))
    return {"started": True}

@app.post("/api/event")
def event(b: EventIn):
    try:
        name, delta, details = b.normalized(engine.snapshot()["pool"])
        engine.inject(name, delta, b.allow_override, lim=b.risk_limit, sac=b.max_sacrifices, metadata=details)
    except ValueError as e:
        raise HTTPException(422, str(e))
    except RuntimeError as e:
        raise HTTPException(409, str(e))
    return {"started": True, "event": details, "normalized_delta": delta}

@app.post("/api/reset")
def reset():
    try: engine.reset()
    except RuntimeError as e: raise HTTPException(409, str(e))
    return {"reset": True}

@app.get("/api/export/json")
def export_json():
    s = engine.snapshot()
    plan = s.get("plan") or {}
    selected = plan.get("sel") or {}
    starter_kit_records = []
    agent_ids = {
        "LS": "LIFE_SUPPORT_OFFICER",
        "MED": "MEDICAL_OFFICER",
        "FOOD": "FOOD_PRODUCTION_OFFICER",
        "ENG": "ENGINEERING_OFFICER",
    }
    for key in X.K:
        mode = selected.get(key, 0)
        label, values, risk = X.pkg(key, mode)
        vote = (plan.get("votes") or {}).get(key, {}).get("v", "REJECT")
        starter_kit_records.append({
            "round": s.get("round", 0),
            "agent_id": agent_ids[key],
            "proposal": {
                "oxygen_units": values[2],
                "water_liters": values[1],
                "power_kwh": values[0],
                "food_rations": 0,
                "robot_time_units": values[3],
                "bandwidth_units": values[4],
                "mode": label,
                "justification": f"Selected published mode {label}; resource allocation validated by deterministic rules.",
            },
            "vote": "APPROVE" if vote == "ACCEPT" else "REJECT",
            "risk_score": risk,
            "flag_human_review": bool(s.get("status") != "APPROVED" or not X.ok_all(s.get("vr", []))),
        })
    return {
        "schema_version": "2.0",
        "starter_kit_schema_version": "ARES-Accord-output-schema-example",
        "exported_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "mode": "LLM-driven agents when enabled; otherwise deterministic rule-based mode. Every message carries a source label (llm / rule-fallback / rule).",
        "resources": dict(zip(X.R, s["pool"])),
        "events": s["events"],
        "status": s["status"],
        "scenario": s["scen"],
        "round": s["round"],
        "policy": s.get("policy"),
        "plan": s["plan"],
        "validation": s["vr"],
        "metrics": metrics(),
        "transcript": engine.store.messages(),
        "starter_kit_records": starter_kit_records,
    }

def _spreadsheet_safe(value):
    """Prefix spreadsheet formula-leading text so exported dialogue stays inert in CSV viewers."""
    if isinstance(value, str) and value.lstrip(" \t\r\n").startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


@app.get("/api/export/csv")
def export_csv():
    fields = ["id", "scenario", "round", "plan_version", "frm", "type", "to", "text", "source"]
    b = io.StringIO(newline="")
    w = csv.DictWriter(b, fieldnames=fields, lineterminator="\r\n")
    w.writeheader()
    for row in engine.store.messages():
        w.writerow({key: _spreadsheet_safe(row.get(key, "")) for key in fields})
    return Response(b.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=ares_transcript.csv", "X-Content-Type-Options": "nosniff"})


_web = os.path.join(os.path.dirname(__file__), "..", "..", "web")
if os.path.isdir(_web): app.mount("/", StaticFiles(directory=_web, html=True), name="web")  # dashboard at http://localhost:8000
