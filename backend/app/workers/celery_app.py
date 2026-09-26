from celery import Celery
from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "bookai",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "app.workers.upload_worker",
        "app.workers.generate_worker",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=600,
    task_soft_time_limit=540,
)
