from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import engine
from app.models import Tenant, User


def create_tables() -> None:
    Base.metadata.create_all(bind=engine)


def migrate_schema() -> None:
    inspector = inspect(engine)
    if "scans" not in inspector.get_table_names():
        return

    existing_columns = {col["name"] for col in inspector.get_columns("scans")}
    if "scan_type" not in existing_columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE scans ADD COLUMN scan_type VARCHAR(50) DEFAULT 'classic_nlp'"))
            conn.execute(text("UPDATE scans SET scan_type = 'classic_nlp' WHERE scan_type IS NULL"))
            conn.execute(text("ALTER TABLE scans ALTER COLUMN scan_type SET NOT NULL"))


def seed_defaults(db: Session) -> None:
    settings = get_settings()
    tenant = db.scalar(select(Tenant).where(Tenant.name == settings.default_tenant_name))
    if tenant is None:
        tenant = Tenant(name=settings.default_tenant_name)
        db.add(tenant)
        db.flush()

    user = db.scalar(select(User).where(User.email == settings.default_user_email))
    if user is None:
        db.add(
            User(
                tenant_id=tenant.tenant_id,
                email=settings.default_user_email,
                display_name=settings.default_user_name,
                role=settings.default_user_role,
            )
        )

    db.commit()


def init_db() -> None:
    from app.db.session import SessionLocal

    create_tables()
    migrate_schema()
    with SessionLocal() as db:
        seed_defaults(db)
