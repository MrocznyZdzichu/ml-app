from sqlalchemy import text

from app.core.database import get_engine
from app.core.migrations import run_migrations


def test_migration_runner_is_idempotent_and_records_version() -> None:
    engine = get_engine()

    run_migrations(engine)
    second_run = run_migrations(engine)

    assert second_run == []
    with engine.begin() as connection:
        row = connection.execute(
            text(
                "SELECT description FROM mlapp.schema_migrations "
                "WHERE version = '20260703_0001'"
            )
        ).one()
    assert row.description == "Move legacy dataset and pipeline runtime DDL into migrations"
