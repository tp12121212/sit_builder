from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_principal
from app.db.session import get_db
from app.models import (
    SitDefinition,
    SitElement,
    SitElementGroup,
    SitFilter,
    SitGroupElement,
    SitStatus,
)
from app.schemas.auth import Principal
from app.schemas.sit import (
    SitCompareResponse,
    SitCreateRequest,
    SitDetailResponse,
    SitElementBase,
    SitElementResponse,
    SitGroupCreateRequest,
    SitGroupElementRef,
    SitGroupResponse,
    SitListResponse,
    SitSummary,
    SitTestRequest,
    SitTestResponse,
    SitUpdateRequest,
    SitVersionResponse,
    VersionEntry,
)
from app.services.sit_engine import test_sit

router = APIRouter(prefix="/sits", tags=["sits"])


def _get_sit_or_404(db: Session, principal: Principal, sit_id: UUID) -> SitDefinition:
    sit = db.scalar(select(SitDefinition).where(SitDefinition.sit_id == sit_id, SitDefinition.tenant_id == principal.tenant_id))
    if sit is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SIT not found")
    return sit


def _build_sit_detail(db: Session, sit: SitDefinition) -> SitDetailResponse:
    elements = db.scalars(select(SitElement).where(SitElement.sit_id == sit.sit_id)).all()
    groups = db.scalars(select(SitElementGroup).where(SitElementGroup.sit_id == sit.sit_id)).all()
    filters = db.scalars(select(SitFilter).where(SitFilter.sit_id == sit.sit_id)).all()
    links = db.scalars(
        select(SitGroupElement).where(SitGroupElement.group_id.in_([group.group_id for group in groups]))
    ).all() if groups else []

    group_to_ids: dict[str, list[str]] = {}
    for link in links:
        group_to_ids.setdefault(str(link.group_id), []).append(str(link.element_id))

    element_by_id = {str(element.element_id): element for element in elements}

    group_payload = []
    for group in groups:
        element_refs = [
            SitGroupElementRef(
                element_id=element_by_id[element_id].element_id,
                element_type=element_by_id[element_id].element_type,
                pattern=element_by_id[element_id].pattern,
            )
            for element_id in group_to_ids.get(str(group.group_id), [])
            if element_id in element_by_id
        ]
        group_payload.append(
            SitGroupResponse(
                group_id=group.group_id,
                group_name=group.group_name,
                logic_type=group.logic_type,
                proximity_window_chars=group.proximity_window_chars,
                threshold_count=group.threshold_count,
                elements=element_refs,
            )
        )

    return SitDetailResponse(
        sit_id=sit.sit_id,
        name=sit.name,
        description=sit.description,
        confidence_level=sit.confidence_level,
        status=sit.status,
        version=sit.version,
        elements=[
            SitElementResponse(
                element_id=element.element_id,
                element_role=element.element_role,
                element_type=element.element_type,
                pattern=element.pattern,
                case_sensitive=element.case_sensitive,
                word_boundary=element.word_boundary,
                checksum_function=element.checksum_function,
                min_matches=element.min_matches,
                max_matches=element.max_matches,
                source_candidate_id=(element.metadata_json or {}).get("source_candidate_id"),
            )
            for element in elements
        ],
        groups=group_payload,
        filters=[
            {
                "filter_id": flt.filter_id,
                "filter_type": flt.filter_type,
                "pattern": flt.pattern,
                "description": flt.description,
            }
            for flt in filters
        ],
    )


def _assert_draft(sit: SitDefinition) -> None:
    if sit.status != SitStatus.DRAFT:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only DRAFT SITs can be modified")


@router.post("", response_model=SitSummary, status_code=status.HTTP_201_CREATED)
def create_sit(
    payload: SitCreateRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> SitSummary:
    sit = SitDefinition(
        tenant_id=principal.tenant_id,
        created_by=principal.user_id,
        name=payload.name,
        description=payload.description,
        confidence_level=payload.confidence_level,
        status=SitStatus.DRAFT,
        version=1,
        tags=payload.tags,
    )
    db.add(sit)
    db.commit()
    db.refresh(sit)

    return SitSummary(
        sit_id=sit.sit_id,
        name=sit.name,
        description=sit.description,
        confidence_level=sit.confidence_level,
        status=sit.status,
        version=sit.version,
        tags=sit.tags,
        created_at=sit.created_at,
        updated_at=sit.updated_at,
    )


@router.get("", response_model=SitListResponse)
def list_sits(
    q: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    tags: str | None = Query(default=None),
    sort: str = Query(default="updated_at_desc"),
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> SitListResponse:
    query = select(SitDefinition).where(SitDefinition.tenant_id == principal.tenant_id)

    if q:
        like = f"%{q.lower()}%"
        query = query.where(or_(func.lower(SitDefinition.name).like(like), func.lower(SitDefinition.description).like(like)))
    if status_filter:
        query = query.where(SitDefinition.status == status_filter)
    if tags:
        wanted = [tag.strip() for tag in tags.split(",") if tag.strip()]
        for tag in wanted:
            query = query.where(SitDefinition.tags.any(tag))

    if sort == "created_at":
        query = query.order_by(SitDefinition.created_at)
    elif sort == "created_at_desc":
        query = query.order_by(SitDefinition.created_at.desc())
    elif sort == "name":
        query = query.order_by(SitDefinition.name.asc())
    elif sort == "name_desc":
        query = query.order_by(SitDefinition.name.desc())
    else:
        query = query.order_by(SitDefinition.updated_at.desc())

    sits = db.scalars(query).all()
    return SitListResponse(
        sits=[
            SitSummary(
                sit_id=sit.sit_id,
                name=sit.name,
                description=sit.description,
                confidence_level=sit.confidence_level,
                status=sit.status,
                version=sit.version,
                tags=sit.tags,
                created_at=sit.created_at,
                updated_at=sit.updated_at,
            )
            for sit in sits
        ],
        total=len(sits),
    )


@router.get("/{sit_id}", response_model=SitDetailResponse)
def get_sit(
    sit_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> SitDetailResponse:
    sit = _get_sit_or_404(db, principal, sit_id)
    return _build_sit_detail(db, sit)


@router.put("/{sit_id}", response_model=SitDetailResponse)
def update_sit(
    sit_id: UUID,
    payload: SitUpdateRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> SitDetailResponse:
    sit = _get_sit_or_404(db, principal, sit_id)
    _assert_draft(sit)

    if payload.name is not None:
        sit.name = payload.name
    if payload.description is not None:
        sit.description = payload.description
    if payload.confidence_level is not None:
        sit.confidence_level = payload.confidence_level
    if payload.tags is not None:
        sit.tags = payload.tags

    if payload.elements is not None:
        db.query(SitElement).filter(SitElement.sit_id == sit.sit_id).delete()
        for element in payload.elements:
            db.add(
                SitElement(
                    sit_id=sit.sit_id,
                    element_role=element.element_role,
                    element_type=element.element_type,
                    pattern=element.pattern,
                    case_sensitive=element.case_sensitive,
                    word_boundary=element.word_boundary,
                    checksum_function=element.checksum_function,
                    min_matches=element.min_matches,
                    max_matches=element.max_matches,
                    metadata_json={"source_candidate_id": str(element.source_candidate_id)} if element.source_candidate_id else None,
                )
            )

    sit.updated_at = datetime.now(tz=timezone.utc)
    db.commit()
    db.refresh(sit)
    return _build_sit_detail(db, sit)


@router.post("/{sit_id}/publish", response_model=SitSummary)
def publish_sit(
    sit_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> SitSummary:
    sit = _get_sit_or_404(db, principal, sit_id)
    _assert_draft(sit)

    sit.status = SitStatus.PUBLISHED
    sit.published_at = datetime.now(tz=timezone.utc)
    db.commit()
    db.refresh(sit)

    return SitSummary(
        sit_id=sit.sit_id,
        name=sit.name,
        description=sit.description,
        confidence_level=sit.confidence_level,
        status=sit.status,
        version=sit.version,
        tags=sit.tags,
        created_at=sit.created_at,
        updated_at=sit.updated_at,
    )


@router.post("/{sit_id}/clone", response_model=SitSummary, status_code=status.HTTP_201_CREATED)
def clone_sit(
    sit_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> SitSummary:
    source = _get_sit_or_404(db, principal, sit_id)

    max_version = db.scalar(
        select(func.max(SitDefinition.version)).where(
            SitDefinition.tenant_id == principal.tenant_id,
            SitDefinition.name == source.name,
        )
    ) or 1

    clone = SitDefinition(
        tenant_id=source.tenant_id,
        created_by=principal.user_id,
        name=source.name,
        description=source.description,
        confidence_level=source.confidence_level,
        status=SitStatus.DRAFT,
        version=max_version + 1,
        parent_sit_id=source.parent_sit_id or source.sit_id,
        tags=source.tags,
    )
    db.add(clone)
    db.flush()

    source_elements = db.scalars(select(SitElement).where(SitElement.sit_id == source.sit_id)).all()
    element_id_map: dict[UUID, UUID] = {}

    for element in source_elements:
        copied = SitElement(
            sit_id=clone.sit_id,
            element_role=element.element_role,
            element_type=element.element_type,
            pattern=element.pattern,
            case_sensitive=element.case_sensitive,
            word_boundary=element.word_boundary,
            checksum_function=element.checksum_function,
            min_matches=element.min_matches,
            max_matches=element.max_matches,
            metadata_json=element.metadata_json,
        )
        db.add(copied)
        db.flush()
        element_id_map[element.element_id] = copied.element_id

    source_groups = db.scalars(select(SitElementGroup).where(SitElementGroup.sit_id == source.sit_id)).all()
    group_id_map: dict[UUID, UUID] = {}
    for group in source_groups:
        copied_group = SitElementGroup(
            sit_id=clone.sit_id,
            group_name=group.group_name,
            logic_type=group.logic_type,
            threshold_count=group.threshold_count,
            proximity_window_chars=group.proximity_window_chars,
        )
        db.add(copied_group)
        db.flush()
        group_id_map[group.group_id] = copied_group.group_id

    if group_id_map:
        links = db.scalars(select(SitGroupElement).where(SitGroupElement.group_id.in_(list(group_id_map.keys())))).all()
        for link in links:
            new_group_id = group_id_map.get(link.group_id)
            new_element_id = element_id_map.get(link.element_id)
            if new_group_id and new_element_id:
                db.add(SitGroupElement(group_id=new_group_id, element_id=new_element_id))

    source_filters = db.scalars(select(SitFilter).where(SitFilter.sit_id == source.sit_id)).all()
    for flt in source_filters:
        db.add(
            SitFilter(
                sit_id=clone.sit_id,
                filter_type=flt.filter_type,
                pattern=flt.pattern,
                description=flt.description,
            )
        )

    db.commit()
    db.refresh(clone)

    return SitSummary(
        sit_id=clone.sit_id,
        name=clone.name,
        description=clone.description,
        confidence_level=clone.confidence_level,
        status=clone.status,
        version=clone.version,
        tags=clone.tags,
        created_at=clone.created_at,
        updated_at=clone.updated_at,
    )


@router.get("/{sit_id}/versions", response_model=SitVersionResponse)
def get_versions(
    sit_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> SitVersionResponse:
    sit = _get_sit_or_404(db, principal, sit_id)
    root = sit.parent_sit_id or sit.sit_id

    versions = db.scalars(
        select(SitDefinition).where(
            SitDefinition.tenant_id == principal.tenant_id,
            or_(SitDefinition.sit_id == root, SitDefinition.parent_sit_id == root),
            SitDefinition.name == sit.name,
        ).order_by(SitDefinition.version.desc())
    ).all()

    return SitVersionResponse(
        versions=[VersionEntry(version=item.version, status=item.status, updated_at=item.updated_at) for item in versions]
    )


@router.get("/{sit_id1}/compare/{sit_id2}", response_model=SitCompareResponse)
def compare_versions(
    sit_id1: UUID,
    sit_id2: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> SitCompareResponse:
    sit1 = _get_sit_or_404(db, principal, sit_id1)
    sit2 = _get_sit_or_404(db, principal, sit_id2)

    elements_1 = db.scalars(select(SitElement).where(SitElement.sit_id == sit1.sit_id)).all()
    elements_2 = db.scalars(select(SitElement).where(SitElement.sit_id == sit2.sit_id)).all()

    set_1 = {(item.element_role, item.element_type, item.pattern or "") for item in elements_1}
    set_2 = {(item.element_role, item.element_type, item.pattern or "") for item in elements_2}

    added = [
        {"element_role": role, "element_type": element_type, "pattern": pattern}
        for (role, element_type, pattern) in sorted(set_2 - set_1)
    ]
    removed = [
        {"element_role": role, "element_type": element_type, "pattern": pattern}
        for (role, element_type, pattern) in sorted(set_1 - set_2)
    ]

    return SitCompareResponse(diff={"elements_added": added, "elements_removed": removed, "elements_modified": []})


@router.delete("/{sit_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_sit(
    sit_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> Response:
    sit = _get_sit_or_404(db, principal, sit_id)
    sit.status = SitStatus.ARCHIVED
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{sit_id}/elements", response_model=SitElementResponse, status_code=status.HTTP_201_CREATED)
def add_element(
    sit_id: UUID,
    payload: SitElementBase,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> SitElementResponse:
    sit = _get_sit_or_404(db, principal, sit_id)
    _assert_draft(sit)

    element = SitElement(
        sit_id=sit.sit_id,
        element_role=payload.element_role,
        element_type=payload.element_type,
        pattern=payload.pattern,
        case_sensitive=payload.case_sensitive,
        word_boundary=payload.word_boundary,
        checksum_function=payload.checksum_function,
        min_matches=payload.min_matches,
        max_matches=payload.max_matches,
        metadata_json={"source_candidate_id": str(payload.source_candidate_id)} if payload.source_candidate_id else None,
    )
    db.add(element)
    db.commit()
    db.refresh(element)

    return SitElementResponse(
        element_id=element.element_id,
        element_role=element.element_role,
        element_type=element.element_type,
        pattern=element.pattern,
        case_sensitive=element.case_sensitive,
        word_boundary=element.word_boundary,
        checksum_function=element.checksum_function,
        min_matches=element.min_matches,
        max_matches=element.max_matches,
        source_candidate_id=(element.metadata_json or {}).get("source_candidate_id"),
    )


@router.put("/{sit_id}/elements/{element_id}", response_model=SitElementResponse)
def update_element(
    sit_id: UUID,
    element_id: UUID,
    payload: SitElementBase,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> SitElementResponse:
    sit = _get_sit_or_404(db, principal, sit_id)
    _assert_draft(sit)

    element = db.scalar(select(SitElement).where(SitElement.sit_id == sit_id, SitElement.element_id == element_id))
    if element is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Element not found")

    element.element_role = payload.element_role
    element.element_type = payload.element_type
    element.pattern = payload.pattern
    element.case_sensitive = payload.case_sensitive
    element.word_boundary = payload.word_boundary
    element.checksum_function = payload.checksum_function
    element.min_matches = payload.min_matches
    element.max_matches = payload.max_matches
    element.metadata_json = {"source_candidate_id": str(payload.source_candidate_id)} if payload.source_candidate_id else None

    db.commit()
    db.refresh(element)

    return SitElementResponse(
        element_id=element.element_id,
        element_role=element.element_role,
        element_type=element.element_type,
        pattern=element.pattern,
        case_sensitive=element.case_sensitive,
        word_boundary=element.word_boundary,
        checksum_function=element.checksum_function,
        min_matches=element.min_matches,
        max_matches=element.max_matches,
        source_candidate_id=(element.metadata_json or {}).get("source_candidate_id"),
    )


@router.delete("/{sit_id}/elements/{element_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_element(
    sit_id: UUID,
    element_id: UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> Response:
    sit = _get_sit_or_404(db, principal, sit_id)
    _assert_draft(sit)

    element = db.scalar(select(SitElement).where(SitElement.sit_id == sit_id, SitElement.element_id == element_id))
    if element is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Element not found")

    db.delete(element)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{sit_id}/groups", response_model=SitGroupResponse, status_code=status.HTTP_201_CREATED)
def create_group(
    sit_id: UUID,
    payload: SitGroupCreateRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> SitGroupResponse:
    sit = _get_sit_or_404(db, principal, sit_id)
    _assert_draft(sit)

    group = SitElementGroup(
        sit_id=sit.sit_id,
        group_name=payload.group_name,
        logic_type=payload.logic_type,
        threshold_count=payload.threshold_count,
        proximity_window_chars=payload.proximity_window_chars,
    )
    db.add(group)
    db.flush()

    for element_id in payload.element_ids:
        db.add(SitGroupElement(group_id=group.group_id, element_id=element_id))

    db.commit()
    db.refresh(group)

    elements = db.scalars(select(SitElement).where(SitElement.element_id.in_(payload.element_ids))).all() if payload.element_ids else []

    return SitGroupResponse(
        group_id=group.group_id,
        group_name=group.group_name,
        logic_type=group.logic_type,
        proximity_window_chars=group.proximity_window_chars,
        threshold_count=group.threshold_count,
        elements=[
            SitGroupElementRef(element_id=item.element_id, element_type=item.element_type, pattern=item.pattern)
            for item in elements
        ],
    )


@router.put("/{sit_id}/groups/{group_id}", response_model=SitGroupResponse)
def update_group(
    sit_id: UUID,
    group_id: UUID,
    payload: SitGroupCreateRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> SitGroupResponse:
    sit = _get_sit_or_404(db, principal, sit_id)
    _assert_draft(sit)

    group = db.scalar(select(SitElementGroup).where(SitElementGroup.sit_id == sit_id, SitElementGroup.group_id == group_id))
    if group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")

    group.group_name = payload.group_name
    group.logic_type = payload.logic_type
    group.proximity_window_chars = payload.proximity_window_chars
    group.threshold_count = payload.threshold_count

    db.query(SitGroupElement).filter(SitGroupElement.group_id == group.group_id).delete()
    for element_id in payload.element_ids:
        db.add(SitGroupElement(group_id=group.group_id, element_id=element_id))

    db.commit()

    elements = db.scalars(select(SitElement).where(SitElement.element_id.in_(payload.element_ids))).all() if payload.element_ids else []
    return SitGroupResponse(
        group_id=group.group_id,
        group_name=group.group_name,
        logic_type=group.logic_type,
        proximity_window_chars=group.proximity_window_chars,
        threshold_count=group.threshold_count,
        elements=[
            SitGroupElementRef(element_id=item.element_id, element_type=item.element_type, pattern=item.pattern)
            for item in elements
        ],
    )


@router.post("/{sit_id}/test", response_model=SitTestResponse)
def test_sit_definition(
    sit_id: UUID,
    payload: SitTestRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
) -> SitTestResponse:
    sit = _get_sit_or_404(db, principal, sit_id)

    elements = db.scalars(select(SitElement).where(SitElement.sit_id == sit.sit_id)).all()
    groups = db.scalars(select(SitElementGroup).where(SitElementGroup.sit_id == sit.sit_id)).all()
    group_links = db.scalars(
        select(SitGroupElement).where(SitGroupElement.group_id.in_([group.group_id for group in groups]))
    ).all() if groups else []
    filters = db.scalars(select(SitFilter).where(SitFilter.sit_id == sit.sit_id)).all()

    matches = test_sit(payload.sample_text, sit.confidence_level, elements, groups, group_links, filters)
    return SitTestResponse(matches=matches, match_count=len(matches))
