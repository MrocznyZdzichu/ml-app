from celery import Celery
from celery.signals import worker_ready

from app.core.config import settings
from app.core.migrations import run_migrations

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
    result_expires=settings.descriptive_profile_result_expires_seconds,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)

celery_app.autodiscover_tasks(["app.worker"])


@worker_ready.connect
def migrate_worker_database(**_: object) -> None:
    run_migrations()
