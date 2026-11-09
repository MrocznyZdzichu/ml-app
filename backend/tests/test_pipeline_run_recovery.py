from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import uuid4

import pytest

from app.modules.pipelines.domain import PipelineRun, PipelineRunStatus, PipelineRunTrigger, PipelineStepRun
from app.modules.pipelines.repository import (
    PostgresPipelineRepository,
    pipeline_runs_table,
    pipeline_step_runs_table,
)
from app.modules.pipelines.run_executor import PipelineRunExecutor


@pytest.fixture
def queued_run():
    repository = PostgresPipelineRepository()
    run = PipelineRun(
        id=str(uuid4()), owner_id="test-owner", pipeline_id="test-pipeline",
        pipeline_version_id="test-version", business_case_id="test-case",
        status=PipelineRunStatus.QUEUED, trigger_type=PipelineRunTrigger.MANUAL,
    )
    repository.add_run(run)
    try:
        yield repository, run
    finally:
        with repository.engine.begin() as connection:
            connection.execute(pipeline_step_runs_table.delete().where(
                pipeline_step_runs_table.c.pipeline_run_id == run.id
            ))
            connection.execute(pipeline_runs_table.delete().where(pipeline_runs_table.c.id == run.id))


def test_duplicate_delivery_and_reconciliation_skip_live_worker(queued_run, monkeypatch):
    repository, run = queued_run
    executor = PipelineRunExecutor(repository_factory=lambda: repository)
    entered = Event()
    release = Event()

    def hold_worker(_):
        entered.set()
        assert release.wait(timeout=10)
        raise ValueError("end test execution")

    monkeypatch.setattr(executor, "_require_execution_access", hold_worker)
    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(executor.execute, run.id)
        try:
            assert entered.wait(timeout=10)
            assert executor.execute(run.id) == {"run_id": run.id, "status": "running"}
            with repository.lock_run_execution(run.id) as verify_lock:
                assert verify_lock is None
            assert repository.get_run(run.id).status == PipelineRunStatus.RUNNING
        finally:
            release.set()
        assert first.result(timeout=10)["status"] == "failed"

    assert executor.execute(run.id) == {"run_id": run.id, "status": "failed"}
    assert [event["type"] for event in repository.get_run(run.id).events] == ["run.started"]


@pytest.mark.parametrize("cancelled", [False, True])
def test_reconciliation_closes_interrupted_run_and_step(queued_run, monkeypatch, cancelled):
    repository, run = queued_run
    executor = PipelineRunExecutor(repository_factory=lambda: repository)
    step = PipelineStepRun(
        id=str(uuid4()), owner_id=run.owner_id, pipeline_run_id=run.id,
        pipeline_step_id="transform", step_type="data_engineering", status=PipelineRunStatus.RUNNING,
    )

    def interrupt(_):
        repository.add_step_run(step)
        if cancelled:
            active = repository.get_run(run.id)
            active.status = PipelineRunStatus.CANCELLED
            repository.update_run(active)
        raise SystemExit("simulated worker interruption")

    monkeypatch.setattr(executor, "_require_execution_access", interrupt)
    with pytest.raises(SystemExit, match="interruption"):
        executor.execute(run.id)
    active_status = PipelineRunStatus.CANCELLED if cancelled else PipelineRunStatus.RUNNING
    assert repository.get_run(run.id).status == active_status
    assert run.id in repository.interrupted_run_candidates("", 100)

    assert executor.reconcile_interrupted_runs() == {"recovered_runs": 1}
    recovered = repository.get_run(run.id)
    final_status = PipelineRunStatus.CANCELLED if cancelled else PipelineRunStatus.FAILED
    assert recovered.status == final_status
    if not cancelled:
        assert recovered.finished_at is not None
        assert recovered.events[-1]["type"] == "run.interrupted"
    recovered_step, = repository.list_step_runs(run.id, run.owner_id)
    assert recovered_step.status == final_status
    assert recovered_step.finished_at is not None
    assert executor.reconcile_interrupted_runs() == {"recovered_runs": 0}
