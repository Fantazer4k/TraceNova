"""
FastAPI application setup
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os
from pathlib import Path

from backend.config import get_settings
from services.ip_resolver import resolve_domain_to_ip, get_additional_ip_info
from services.username_search import search_username
from services.email_search import search_email
from services.phone_search import search_phone

settings = get_settings()

def create_app() -> FastAPI:
    app = FastAPI(
        title="TraceNova",
        description="AI Digital Intelligence Platform",
        version="0.1.0"
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Static files
    static_path = Path(__file__).parent.parent / "frontend" / "static"
    if static_path.exists():
        app.mount("/static", StaticFiles(directory=str(static_path)), name="static")

    # Routes
    @app.get("/")
    async def root():
        template_path = Path(__file__).parent.parent / "frontend" / "templates" / "index.html"
        return FileResponse(template_path)

    @app.get("/api/analyze")
    async def analyze(query: str, query_type: str = "domain"):
        """
        Main analysis endpoint
        query_type: domain, url, ip, username, email
        """
        try:
            if not query or len(query) < 3:
                raise HTTPException(status_code=400, detail="Query too short")

            # Handle different query types
            if query_type == "domain":
                result = await resolve_domain_to_ip(query)

                # If successful, get additional IP info
                if result["status"] == "success":
                    ip_info = await get_additional_ip_info(result["ip_address"])
                    result["ip_info"] = ip_info

                return result

            elif query_type == "username":
                result = await search_username(query)
                return result

            elif query_type == "email":
                result = await search_email(query)
                return result

            elif query_type == "phone":
                result = await search_phone(query)
                return result

            else:
                return {
                    "status": "pending",
                    "message": f"{query_type} analysis not implemented yet",
                    "query": query
                }

        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/health")
    async def health_check():
        return {"status": "ok", "version": "0.1.0"}

    return app
