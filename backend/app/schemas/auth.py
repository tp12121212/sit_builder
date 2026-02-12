from uuid import UUID

from pydantic import BaseModel


class Principal(BaseModel):
    tenant_id: UUID
    user_id: UUID
    role: str
