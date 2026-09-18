"""
FastAPI application setup
"""

import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.config import get_settings
from services.email_search import search_email
from services.ip_resolver import get_additional_ip_info, resolve_domain_to_ip
from services.phone_search import search_phone
from services.username_search import search_username

settings = get_settings()
logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(
        title="TraceNova",
        description="OSINT and digital-intelligence learning platform",
        version=settings.api_version,
        debug=settings.debug,
    )

    # CORS is disabled by default. Configure CORS_ORIGINS when a separate
    # frontend origin needs access to the API.
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["GET"],
            allow_headers=["*"],
        )

    # Static files
    static_path = Path(__file__).parent.parent / "frontend" / "static"
    if static_path.exists():
        app.mount("/static", StaticFiles(directory=str(static_path)), name="static")

    @app.get("/")
    async def root():
        template_path = Path(__file__).parent.parent / "frontend" / "templates" / "index.html"
        return FileResponse(template_path)

    @app.get("/api/analyze")
    async def analyze(query: str, query_type: str = "domain"):
        """Main analysis endpoint."""
        if not query or len(query.strip()) < 3:
            raise HTTPException(status_code=400, detail="Query too short")

        try:
            if query_type == "domain":
                result = await resolve_domain_to_ip(query)

                if result["status"] == "success":
                    result["ip_info"] = await get_additional_ip_info(result["ip_address"])

                return result

            if query_type == "username":
                return await search_username(query)

            if query_type == "email":
                return await search_email(query)

            if query_type == "phone":
                return await search_phone(query)

            return {
                "status": "pending",
                "message": f"{query_type} analysis not implemented yet",
                "query": query,
            }

        except HTTPException:
            raise
        except Exception:
            logger.exception("Analysis failed for query_type=%s", query_type)
            raise HTTPException(
                status_code=500,
                detail="An internal error occurred while processing the request.",
            )

    @app.get("/health")
    async def health_check():
        return {"status": "ok", "version": settings.api_version}

    return app
