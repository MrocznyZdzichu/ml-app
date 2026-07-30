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


def test_hot_catalog_and_monitoring_queries_have_composite_indexes() -> None:
    engine = get_engine()
    run_migrations(engine)
    expected = {
        "ix_pipeline_runs_pipeline_created_at",
        "ix_pipeline_versions_pipeline_version",
        "ix_serving_deployments_bc_updated",
        "ix_serving_inference_monitoring_window",
        "ix_pipelines_bc_updated",
        "ix_artifacts_bc_type_created",
        "ix_artifacts_report_logical_id",
        "ix_artifacts_feature_transform_lineage",
        "ix_bc_grants_subject_bc_expiry",
        "ix_resource_grants_subject_resource_expiry",
        "ix_group_memberships_user_group",
        "ix_bc_attachments_bc_asset",
    }
    with engine.begin() as connection:
        present = {
            str(row[0])
            for row in connection.execute(text(
                "SELECT indexname FROM pg_indexes "
                "WHERE schemaname = 'mlapp' AND indexname = ANY(:names)"
            ), {"names": list(expected)})
        }

    assert present == expected
