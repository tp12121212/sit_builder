from __future__ import annotations

from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_principal
from app.db.session import get_db
from app.models import Rulepack, RulepackSit, SitDefinition, SitElement
from app.schemas.auth import Principal
from app.schemas.rulepack import (
    RulepackCreateRequest,
    RulepackCreateResponse,
    RulepackDetailResponse,
    RulepackListResponse,
    RulepackSummary,
)
from app.services.rulepack_builder import SitPayload, build_powershell_script, build_readme, build_rulepack_xml
from app.services.storage import read_artifact, write_artifact

router = APIRouter(prefix="/rulepacks", tags=["rulepacks"])


@router.post("", response_model=RulepackCreateResponse, status_code=status.HTTP_201_CREATED)
def create_rulepack(
    payload: RulepackCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> RulepackCreateResponse:
    if not payload.sit_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No SITs provided")

    sits = db.scalars(
        select(SitDefinition).where(SitDefinition.tenant_id == principal.tenant_id, SitDefinition.sit_id.in_(payload.sit_ids))
    ).all()
    if len(sits) != len(payload.sit_ids):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="One or more SIT IDs were not found")

    sit_payloads: list[SitPayload] = []
    for sit in sits:
        elements = db.scalars(select(SitElement).where(SitElement.sit_id == sit.sit_id)).all()
        sit_payloads.append(
            SitPayload(
                sit_id=str(sit.sit_id),
                name=sit.name,
                description=sit.description,
                confidence_level=sit.confidence_level,
                elements=[
                    {
                        "element_id": str(element.element_id),
                        "element_role": element.element_role,
                        "element_type": element.element_type,
                        "pattern": element.pattern,
                    }
                    for element in elements
                ],
            )
        )

    xml_content, purview_guid = build_rulepack_xml(payload.name, sit_payloads)
    powershell_content = build_powershell_script("rulepack.xml")
    readme_content = build_readme(payload.name, purview_guid)

    rulepack = Rulepack(
        tenant_id=principal.tenant_id,
        created_by=principal.user_id,
        name=payload.name,
        description=payload.description,
        sit_count=len(sits),
        purview_guid=purview_guid,
    )
    db.add(rulepack)
    db.flush()

    xml_path = write_artifact(f"rulepacks/{rulepack.rulepack_id}", "rulepack.xml", xml_content)
    ps_path = write_artifact(f"rulepacks/{rulepack.rulepack_id}", "Import-rulepack.ps1", powershell_content)
    readme_path = write_artifact(f"rulepacks/{rulepack.rulepack_id}", "README.md", readme_content)

    rulepack.xml_blob_path = xml_path
    rulepack.powershell_blob_path = ps_path
    rulepack.readme_blob_path = readme_path

    for sit in sits:
        db.add(RulepackSit(rulepack_id=rulepack.rulepack_id, sit_id=sit.sit_id))

    db.commit()
    db.refresh(rulepack)

    base = str(request.base_url).rstrip("/")

    return RulepackCreateResponse(
        rulepack_id=rulepack.rulepack_id,
        name=rulepack.name,
        sit_count=rulepack.sit_count or 0,
        purview_guid=rulepack.purview_guid or "",
        xml_download_url=f"{base}/v1/rulepacks/{rulepack.rulepack_id}/download/xml",
        powershell_download_url=f"{base}/v1/rulepacks/{rulepack.rulepack_id}/download/powershell",
        readme_download_url=f"{base}/v1/rulepacks/{rulepack.rulepack_id}/download/readme",
        created_at=rulepack.created_at,
    )


@router.get("", response_model=RulepackListResponse)
def list_rulepacks(
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> RulepackListResponse:
    rulepacks = db.scalars(
        select(Rulepack).where(Rulepack.tenant_id == principal.tenant_id).order_by(Rulepack.created_at.desc())
    ).all()
    return RulepackListResponse(
        rulepacks=[
            RulepackSummary(
                rulepack_id=item.rulepack_id,
                name=item.name,
                sit_count=item.sit_count,
                created_at=item.created_at,
            )
            for item in rulepacks
        ]
    )


@router.get("/{rulepack_id}", response_model=RulepackDetailResponse)
def get_rulepack(
    rulepack_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> RulepackDetailResponse:
    rulepack = db.scalar(select(Rulepack).where(Rulepack.rulepack_id == rulepack_id, Rulepack.tenant_id == principal.tenant_id))
    if rulepack is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rulepack not found")

    links = db.scalars(select(RulepackSit).where(RulepackSit.rulepack_id == rulepack.rulepack_id)).all()
    sits = db.scalars(select(SitDefinition).where(SitDefinition.sit_id.in_([link.sit_id for link in links]))).all() if links else []

    base = str(request.base_url).rstrip("/")

    return RulepackDetailResponse(
        rulepack_id=rulepack.rulepack_id,
        name=rulepack.name,
        description=rulepack.description,
        sits=[{"sit_id": sit.sit_id, "name": sit.name, "version": sit.version} for sit in sits],
        xml_download_url=f"{base}/v1/rulepacks/{rulepack.rulepack_id}/download/xml",
        powershell_download_url=f"{base}/v1/rulepacks/{rulepack.rulepack_id}/download/powershell",
        created_at=rulepack.created_at,
    )


@router.get("/{rulepack_id}/download/{file_type}")
def download_rulepack_artifact(
    rulepack_id: UUID,
    file_type: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> FileResponse:
    rulepack = db.scalar(select(Rulepack).where(Rulepack.rulepack_id == rulepack_id, Rulepack.tenant_id == principal.tenant_id))
    if rulepack is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rulepack not found")

    artifact_map = {
        "xml": (rulepack.xml_blob_path, "rulepack.xml"),
        "powershell": (rulepack.powershell_blob_path, "Import-rulepack.ps1"),
        "readme": (rulepack.readme_blob_path, "README.md"),
    }

    if file_type not in artifact_map:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="file_type must be xml, powershell, or readme")

    path, filename = artifact_map[file_type]
    if not path or not Path(path).exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found")

    # Touch read to surface permission/path errors before returning response.
    read_artifact(path)
    return FileResponse(path=path, filename=filename)
