from typing import Any, Protocol


class TaskResult(Protocol):
    state: str
    result: Any

    def successful(self) -> bool:
        ...

    def failed(self) -> bool:
        ...


class TaskQueue(Protocol):
    """Minimal queue contract used by application services."""

    def enqueue(
        self,
        task_name: str,
        args: list[Any],
        *,
        task_id: str | None = None,
    ) -> Any:
        ...

    def result(self, task_id: str) -> TaskResult:
        ...


def require_task_queue(task_queue: TaskQueue | None) -> TaskQueue:
    """Fail explicitly when a use case was built outside the composition root."""
    if task_queue is None:
        raise RuntimeError("A task queue adapter is required for background operations")
    return task_queue
