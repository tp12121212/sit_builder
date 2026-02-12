from __future__ import annotations

import asyncio
from uuid import UUID

from fastapi import Depends, FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_principal
from app.api.v1.router import api_router
from app.core.config import get_settings
from app.db.init_db import init_db
from app.db.session import SessionLocal, get_db
from app.models import Scan
from app.schemas.auth import Principal
from app.schemas.scan import ScanStatusEvent
from app.services.storage import ensure_storage_dirs

settings = get_settings()
app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.api_prefix)


@app.on_event("startup")
def startup_event() -> None:
    ensure_storage_dirs()
    init_db()


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.websocket(f"{settings.api_prefix}/ws/scans/{{scan_id}}")
async def scan_status_ws(websocket: WebSocket, scan_id: str) -> None:
    await websocket.accept()

    try:
        scan_uuid = UUID(scan_id)
    except ValueError:
        await websocket.send_json({"error": "invalid scan_id"})
        await websocket.close()
        return

    status_progress = {
        "PENDING": (0.05, "Scan queued"),
        "EXTRACTING": (0.45, "Extracting content"),
        "EXTRACTED": (0.6, "Extraction complete"),
        "ANALYZING": (0.8, "Generating candidates"),
        "COMPLETED": (1.0, "Scan complete"),
        "FAILED": (1.0, "Scan failed"),
    }

    try:
        while True:
            with SessionLocal() as db:
                scan = db.scalar(select(Scan).where(Scan.scan_id == scan_uuid))

            if scan is None:
                await websocket.send_json({"error": "scan not found"})
                await websocket.close()
                break

            progress, message = status_progress.get(scan.status, (0.0, "Unknown"))
            event = ScanStatusEvent(
                scan_id=scan.scan_id,
                status=scan.status,
                progress=progress,
                message=message,
            )
            await websocket.send_json(event.model_dump(mode="json"))

            if scan.status in {"COMPLETED", "FAILED"}:
                await websocket.close()
                break

            await asyncio.sleep(2)
    except WebSocketDisconnect:
        return


@app.get(f"{settings.api_prefix}/me")
def me(principal: Principal = Depends(get_current_principal), db: Session = Depends(get_db)) -> dict:
    return principal.model_dump(mode="json")
