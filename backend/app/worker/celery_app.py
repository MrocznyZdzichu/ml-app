from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "ml_app",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_routes={
        "app.worker.tasks.profile_dataset": {"queue": "analytics"},
        "app.worker.tasks.train_model": {"queue": "ml"},
        "app.worker.tasks.batch_score": {"queue": "serving"},
        "app.worker.tasks.export_resource": {"queue": "exports"},
    },
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
)
