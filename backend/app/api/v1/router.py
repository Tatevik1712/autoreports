from fastapi import APIRouter

from backend.app.api.v1.endpoints import auth, files, reports, templates

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(auth.router)
api_router.include_router(templates.router)
api_router.include_router(files.router)
api_router.include_router(reports.router)
