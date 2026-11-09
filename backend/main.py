import os
import logging
from typing import Optional, Dict, Any, Union, List
from fastapi import FastAPI, HTTPException, Request, status, Query
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import text

from backend.database import engine, Base, SessionLocal
from backend.tools import (
    get_kpis,
    get_monthly_revenue,
    get_category_performance,
    get_top_products
)
from backend.agent import BIAgent

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("backend.main")

# Initialize database schema if not already present
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="DDL Labs - AI Data Analyst & BI Agent API",
    description="Production-ready e-commerce analytics and conversational intelligence API",
    version="1.0.0"
)

# CORS setup for dashboard frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize BI Agent instance
agent = BIAgent()


# --- Pydantic Schemas ---
class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000, description="User prompt or query")
    session_id: Optional[str] = Field("default", description="Conversation session ID")


class ChatResponse(BaseModel):
    response: str
    tool_used: str
    data: Union[Dict[str, Any], List[Any]]
    chart_spec: Optional[Dict[str, Any]] = None


class HealthResponse(BaseModel):
    status: str
    database: str
    llm_provider: str
    version: str


# --- Custom Error Envelopes ---
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "status": "error",
            "status_code": exc.status_code,
            "error_type": "HTTPException",
            "message": exc.detail
        }
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "status": "error",
            "status_code": 422,
            "error_type": "ValidationError",
            "message": "Input validation failed on request body or parameters.",
            "errors": exc.errors()
        }
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.exception(f"Unhandled server error: {exc}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "status": "error",
            "status_code": 500,
            "error_type": "InternalServerError",
            "message": "An internal server error occurred while processing your analytics request."
        }
    )


# --- API Routes ---
@app.get("/health", response_model=HealthResponse)
def healthcheck():
    """Verifies database connectivity and LLM configuration."""
    db_status = "connected"
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
    except Exception as e:
        logger.error(f"Database healthcheck failed: {e}")
        db_status = f"unhealthy: {str(e)}"

    llm_info = []
    if agent.gemini_client:
        llm_info.append("Google Gemini")
    if agent.openai_client:
        llm_info.append("OpenAI")
    if not llm_info:
        llm_info.append("Deterministic Grounded Analytics (Offline Mode)")

    return HealthResponse(
        status="healthy" if "unhealthy" not in db_status else "degraded",
        database=db_status,
        llm_provider=" + ".join(llm_info),
        version="1.0.0"
    )


@app.post("/api/chat", response_model=ChatResponse)
def chat_endpoint(request: ChatRequest):
    """Processes natural language questions via the BI Agent."""
    msg = request.message.strip()
    if not msg:
        raise HTTPException(status_code=400, detail="User message must not be blank.")

    try:
        result = agent.process_query(msg)
        return ChatResponse(
            response=result["response"],
            tool_used=result["tool_used"],
            data=result["data"],
            chart_spec=result.get("chart_spec")
        )
    except Exception as e:
        logger.error(f"Error in chat processing: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to process chat query: {str(e)}"
        )


@app.get("/api/kpis")
def kpis_endpoint(
    start_date: Optional[str] = Query(None, description="Start date YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="End date YYYY-MM-DD")
):
    """Returns headline executive metrics for the dashboard."""
    try:
        return get_kpis(start_date=start_date, end_date=end_date)
    except Exception as e:
        logger.error(f"Failed to fetch KPIs: {e}")
        raise HTTPException(status_code=500, detail=f"KPI retrieval failed: {str(e)}")


@app.get("/api/analytics/monthly")
def monthly_endpoint():
    """Returns monthly time-series metrics with MoM growth."""
    try:
        return get_monthly_revenue()
    except Exception as e:
        logger.error(f"Failed to fetch monthly metrics: {e}")
        raise HTTPException(status_code=500, detail=f"Monthly analytics retrieval failed: {str(e)}")


@app.get("/api/analytics/categories")
def categories_endpoint():
    """Returns category breakdown and revenue contribution."""
    try:
        return get_category_performance()
    except Exception as e:
        logger.error(f"Failed to fetch category performance: {e}")
        raise HTTPException(status_code=500, detail=f"Category analytics retrieval failed: {str(e)}")


@app.get("/api/analytics/products/top")
def top_products_endpoint(
    metric: str = Query("revenue", pattern="^(revenue|quantity)$", description="Rank metric"),
    limit: int = Query(5, ge=1, le=50, description="Top N limit")
):
    """Returns top products ranked by sales or units sold."""
    try:
        return get_top_products(metric=metric, limit=limit)
    except Exception as e:
        logger.error(f"Failed to fetch top products: {e}")
        raise HTTPException(status_code=500, detail=f"Top product analytics retrieval failed: {str(e)}")
