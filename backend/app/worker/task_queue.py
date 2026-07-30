from typing import Any

from celery import Celery

from app.worker.celery_app import celery_app


class CeleryTaskQueue:
    """Celery adapter kept outside application and domain modules."""

    def __init__(self, application: Celery | None = None) -> None:
        self.application = application or celery_app

    def enqueue(
        self,
        task_name: str,
        args: list[Any],
        *,
        task_id: str | None = None,
    ) -> Any:
        return self.application.send_task(task_name, args=args, task_id=task_id)

    def result(self, task_id: str) -> Any:
        return self.application.AsyncResult(task_id)
