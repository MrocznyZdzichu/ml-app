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


def test_business_case_name_uniqueness_migration_is_recorded() -> None:
    engine = get_engine()
    run_migrations(engine)
    with engine.begin() as connection:
        row = connection.execute(
            text(
                "SELECT description FROM mlapp.schema_migrations "
                "WHERE version = '20260717_0004'"
            )
        ).one()
        duplicate_count = connection.execute(text(
            "SELECT count(*) FROM ("
            "SELECT lower(name) FROM mlapp.business_cases "
            "GROUP BY lower(name) HAVING count(*) > 1"
            ") duplicates"
        )).scalar_one()
    assert row.description == "Enforce globally unique case-insensitive Business Case names"
    assert duplicate_count == 0
