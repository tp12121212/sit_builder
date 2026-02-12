from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import User
from app.schemas.auth import Principal


def get_current_principal(
    db: Session = Depends(get_db),
    x_tenant_id: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
) -> Principal:
    """
    Development auth shim.
    In production, replace with Entra ID JWT validation.
    """
    if x_tenant_id and x_user_id:
        try:
            return Principal(tenant_id=UUID(x_tenant_id), user_id=UUID(x_user_id), role="ADMIN")
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid X-Tenant-ID or X-User-ID header",
            ) from exc

    user = db.scalar(select(User).limit(1))
    if user is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="No seeded default user found")

    return Principal(tenant_id=user.tenant_id, user_id=user.user_id, role=user.role)
