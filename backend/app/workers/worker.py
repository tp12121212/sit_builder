from app.workers.celery_app import celery_app

# Import task module so Celery discovers registered tasks.
import app.workers.tasks  # noqa: F401

__all__ = ["celery_app"]
