from fastapi import APIRouter

from app.api.v1.endpoints import rulepacks, scans, sits

api_router = APIRouter()
api_router.include_router(scans.router)
api_router.include_router(sits.router)
api_router.include_router(rulepacks.router)
