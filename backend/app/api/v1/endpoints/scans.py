from __future__ import annotations

import threading
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_principal
from app.db.session import get_db
from app.models import Candidate, Scan, ScanFile, ScanStatus, ScanType
from app.schemas.auth import Principal
from app.schemas.scan import (
    CandidateListResponse,
    CandidateResponse,
    ScanCreateResponse,
    ScanFileResponse,
    ScanListResponse,
    ScanResponse,
    ScanSummary,
)
from app.services.storage import save_upload_file
from app.workers.tasks import process_scan

router = APIRouter(prefix="/scans", tags=["scans"])


@router.get("", response_model=ScanListResponse)
def list_scans(
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> ScanListResponse:
    scans = db.scalars(
        select(Scan).where(Scan.tenant_id == principal.tenant_id).order_by(Scan.created_at.desc())
    ).all()
    return ScanListResponse(
        scans=[
            ScanSummary(
                scan_id=item.scan_id,
                name=item.name,
                scan_type=item.scan_type,
                status=item.status,
                source_files_count=item.source_files_count,
                created_at=item.created_at,
                completed_at=item.completed_at,
            )
            for item in scans
        ]
    )


@router.post("", response_model=ScanCreateResponse, status_code=status.HTTP_201_CREATED)
def create_scan(
    files: list[UploadFile] = File(...),
    name: str | None = Form(default=None),
    scan_type: str = Form(default=ScanType.CLASSIC_NLP.value),
    sit_category: str | None = Form(default=None),
    preserve_case: bool = Form(default=False),
    force_ocr: bool = Form(default=False),
    user_principal_name: str | None = Form(default=None),
    exchange_access_token: str | None = Form(default=None),
    exchange_organization: str | None = Form(default=None),
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> ScanCreateResponse:
    if not files:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No files uploaded")
    if scan_type not in {ScanType.CLASSIC_NLP.value, ScanType.SENTENCE_TRANSFORMER.value}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid scan_type")
    if scan_type == ScanType.SENTENCE_TRANSFORMER.value and not user_principal_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="user_principal_name is required for sentence_transformer scans",
        )
    if scan_type == ScanType.SENTENCE_TRANSFORMER.value and not exchange_access_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="exchange_access_token is required for sentence_transformer scans",
        )

    total_size = 0
    scan = Scan(
        tenant_id=principal.tenant_id,
        created_by=principal.user_id,
        name=name,
        scan_type=scan_type,
        status=ScanStatus.PENDING,
        source_files_count=len(files),
        metadata_json={
            "user_principal_name": user_principal_name,
            "sit_category": sit_category,
            "preserve_case": bool(preserve_case),
            "force_ocr": bool(force_ocr) if scan_type == ScanType.CLASSIC_NLP.value else False,
        },
    )
    db.add(scan)
    db.flush()

    for upload in files:
        blob_path, size = save_upload_file(upload, principal.tenant_id, scan.scan_id)
        total_size += size
        db.add(
            ScanFile(
                scan_id=scan.scan_id,
                file_name=upload.filename,
                file_type=upload.content_type,
                file_size_bytes=size,
                blob_path=blob_path,
            )
        )

    scan.total_size_bytes = total_size
    db.commit()
    db.refresh(scan)

    task_kwargs: dict[str, str] = {}
    if scan_type == ScanType.SENTENCE_TRANSFORMER.value:
        task_kwargs["exchange_access_token"] = exchange_access_token or ""
        if exchange_organization:
            task_kwargs["exchange_organization"] = exchange_organization

    # Run in a local background thread so API returns immediately while scan progresses
    # even when Celery worker is not running in local/dev environments.
    threading.Thread(
        target=process_scan.run,
        args=(str(scan.scan_id),),
        kwargs=task_kwargs,
        daemon=True,
    ).start()

    return ScanCreateResponse(
        scan_id=scan.scan_id,
        status=scan.status,
        files_count=scan.source_files_count or 0,
        total_size_bytes=scan.total_size_bytes or 0,
        created_at=scan.created_at,
    )


@router.get("/{scan_id}", response_model=ScanResponse)
def get_scan(
    scan_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> ScanResponse:
    scan = db.scalar(select(Scan).where(Scan.scan_id == scan_id, Scan.tenant_id == principal.tenant_id))
    if scan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scan not found")

    return ScanResponse(
        scan_id=scan.scan_id,
        name=scan.name,
        scan_type=scan.scan_type,
        status=scan.status,
        source_files_count=scan.source_files_count,
        extracted_text_length=scan.extracted_text_length,
        ocr_confidence_avg=scan.ocr_confidence_avg,
        extraction_duration_sec=scan.extraction_duration_sec,
        analysis_duration_sec=scan.analysis_duration_sec,
        created_at=scan.created_at,
        completed_at=scan.completed_at,
        metadata=scan.metadata_json,
    )


@router.get("/{scan_id}/files", response_model=dict[str, list[ScanFileResponse]])
def get_scan_files(
    scan_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> dict[str, list[ScanFileResponse]]:
    scan = db.scalar(select(Scan).where(Scan.scan_id == scan_id, Scan.tenant_id == principal.tenant_id))
    if scan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scan not found")

    records = db.scalars(select(ScanFile).where(ScanFile.scan_id == scan_id)).all()
    files = [
        ScanFileResponse(
            file_id=item.file_id,
            file_name=item.file_name,
            file_type=item.file_type,
            file_size_bytes=item.file_size_bytes,
            extraction_method=item.extraction_method,
            ocr_confidence=item.ocr_confidence,
            page_count=item.page_count,
        )
        for item in records
    ]
    return {"files": files}


@router.get("/{scan_id}/candidates", response_model=CandidateListResponse)
def get_scan_candidates(
    scan_id: UUID,
    type: str | None = Query(default=None),
    element_hint: str | None = Query(default=None),
    min_score: float | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> CandidateListResponse:
    scan = db.scalar(select(Scan).where(Scan.scan_id == scan_id, Scan.tenant_id == principal.tenant_id))
    if scan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scan not found")

    query = select(Candidate).where(Candidate.scan_id == scan_id)
    count_query = select(func.count(Candidate.candidate_id)).where(Candidate.scan_id == scan_id)

    if type:
        query = query.where(Candidate.candidate_type == type)
        count_query = count_query.where(Candidate.candidate_type == type)
    if element_hint:
        query = query.where(Candidate.element_type_hint == element_hint)
        count_query = count_query.where(Candidate.element_type_hint == element_hint)
    if min_score is not None:
        query = query.where(Candidate.score >= min_score)
        count_query = count_query.where(Candidate.score >= min_score)

    query = query.order_by(Candidate.score.desc().nullslast()).offset(offset).limit(limit)
    total = db.scalar(count_query) or 0

    rows = db.scalars(query).all()
    candidates = [
        CandidateResponse(
            candidate_id=item.candidate_id,
            candidate_type=item.candidate_type,
            element_type_hint=item.element_type_hint,
            value=item.value,
            pattern_template=item.pattern_template,
            frequency=item.frequency,
            confidence=item.confidence,
            score=item.score,
            evidence=item.evidence,
            metadata=item.metadata_json,
        )
        for item in rows
    ]

    return CandidateListResponse(candidates=candidates, total=total, page=(offset // limit) + 1, page_size=limit)


@router.delete("/{scan_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_scan(
    scan_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> Response:
    scan = db.scalar(select(Scan).where(Scan.scan_id == scan_id, Scan.tenant_id == principal.tenant_id))
    if scan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scan not found")

    db.delete(scan)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
