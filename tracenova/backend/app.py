"""FastAPI application and validated public-analysis API."""
import logging
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend.config import get_settings
from services.email_search import search_email
from services.ip_resolver import analyze_ip, get_additional_ip_info, resolve_domain_to_ip
from services.phone_search import search_phone
from services.username_search import search_username
from services.url_analyzer import analyze_url

settings = get_settings()
logger = logging.getLogger(__name__)

QueryType = Literal["domain", "url", "ip", "username", "email", "phone"]


class AnalysisRequest(BaseModel):
    query_type: QueryType
    query: str = Field(min_length=1, max_length=2048)


def create_app() -> FastAPI:
    app = FastAPI(
        title="TraceNova",
        description="Public-source OSINT and digital-intelligence learning platform",
        version=settings.api_version,
        debug=settings.debug,
    )

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["POST"],
            allow_headers=["Content-Type"],
        )

    static_path = Path(__file__).parent.parent / "frontend" / "static"
    if static_path.exists():
        app.mount("/static", StaticFiles(directory=str(static_path)), name="static")

    @app.get("/")
    async def root():
        template_path = Path(__file__).parent.parent / "frontend" / "templates" / "index.html"
        return FileResponse(template_path)

    @app.post("/api/analyze")
    async def analyze(request: AnalysisRequest):
        """Do not place email, phone, or other search queries in URL/logs."""
        query = request.query.strip()
        kind = request.query_type
        if len(query) < (2 if kind == "username" else 1):
            raise HTTPException(status_code=422, detail="Query too short for this search type.")
        if kind == "domain" and len(query) < 3:
            raise HTTPException(status_code=422, detail="Domain must be at least three characters.")
        try:
            if kind == "url":
                result = await analyze_url(query)
            elif kind == "domain":
                result = await resolve_domain_to_ip(query)
                if result.get("status") == "success":
                    result["ip_info"] = await get_additional_ip_info(result["ip_address"])
            elif kind == "ip":
                result = await analyze_ip(query)
            elif kind == "username":
                result = await search_username(query)
            elif kind == "email":
                result = await search_email(query)
            elif kind == "phone":
                result = await search_phone(query)
            else:
                # The Literal model normally rejects this before execution.
                raise HTTPException(status_code=422, detail="Unsupported query type.")
            if isinstance(result, dict):
                result.setdefault("query_type", kind)
            return result
        except HTTPException:
            raise
        except Exception:
            # Never log full queries (email addresses, phone numbers, etc.).
            logger.exception("Analysis failed for query_type=%s", kind)
            raise HTTPException(status_code=500, detail="An internal error occurred.")

    @app.get("/health")
    async def health_check():
        return {"status": "ok", "version": settings.api_version}

    return app
