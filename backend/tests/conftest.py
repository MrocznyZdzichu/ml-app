import re
import shutil
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import delete, or_, select

from app.core.database import get_engine
from app.modules.business_cases.repository import (
    artifacts_table,
    business_case_data_attachments_table,
    business_cases_table,
    metadata as business_case_metadata,
)
from app.modules.auth.repository import user_accounts_table
from app.modules.auth.api_credentials import api_credentials_table
from app.modules.serving.repository import (
    challenger_replay_jobs_table,
    deployment_revisions_table,
    deployments_table,
    inference_items_table,
    inference_requests_table,
)
from app.modules.sharing.repository import (
    access_groups_table,
    audit_events_table,
    business_case_grants_table,
    group_memberships_table,
    resource_grants_table,
)
from app.modules.datasets.repository import data_assets_table
from app.modules.pipelines.repository import (
    metadata as pipeline_metadata,
    pipeline_runs_table,
    pipeline_step_runs_table,
    pipeline_versions_table,
    pipelines_table,
)


TEST_ACCOUNT_PATTERN = re.compile(
    r"^(?:alice|bob|dupe|delete-owner|roles-owner|metadata-merge-owner|sql-owner|"
    r"restart-owner|preview-owner|preview-limit-owner|view-owner)-"
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}@example[.]com$"
)
USER_REPOSITORY_ROOT = Path("data/repository/users").resolve()


@pytest.fixture(autouse=True)
def clean_persistent_test_accounts(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Remove only persistent users created by the current test and their datasets."""
    test_token = str(uuid4())
    if hasattr(request.module, "uuid4"):
        monkeypatch.setattr(request.module, "uuid4", lambda: test_token)
    try:
        yield
    finally:
        _delete_test_accounts(_test_account_ids(test_token))


def _test_account_ids(test_token: str | None = None) -> set[str]:
    with get_engine().begin() as connection:
        rows = connection.execute(
            select(user_accounts_table.c.id, user_accounts_table.c.email).where(
                user_accounts_table.c.email.like("%@example.com")
            )
        )
    return {
        str(row.id)
        for row in rows
        if TEST_ACCOUNT_PATTERN.fullmatch(str(row.email))
        and (test_token is None or str(row.email).endswith(f"-{test_token}@example.com"))
    }


def _delete_test_accounts(user_ids: set[str]) -> None:
    if not user_ids:
        return
    with get_engine().begin() as connection:
        business_case_metadata.create_all(connection)
        pipeline_metadata.create_all(connection)
        connection.execute(delete(group_memberships_table).where(group_memberships_table.c.user_id.in_(user_ids)))
        connection.execute(delete(business_case_grants_table).where(
            business_case_grants_table.c.subject_type == "user",
            business_case_grants_table.c.subject_id.in_(user_ids),
        ))
        connection.execute(delete(resource_grants_table).where(
            resource_grants_table.c.subject_type == "user",
            resource_grants_table.c.subject_id.in_(user_ids),
        ))
        owned_group_ids = select(access_groups_table.c.id).where(access_groups_table.c.owner_id.in_(user_ids))
        connection.execute(delete(group_memberships_table).where(group_memberships_table.c.group_id.in_(owned_group_ids)))
        connection.execute(delete(business_case_grants_table).where(
            business_case_grants_table.c.subject_type == "group",
            business_case_grants_table.c.subject_id.in_(owned_group_ids),
        ))
        connection.execute(delete(resource_grants_table).where(
            resource_grants_table.c.subject_type == "group",
            resource_grants_table.c.subject_id.in_(owned_group_ids),
        ))
        connection.execute(delete(access_groups_table).where(access_groups_table.c.owner_id.in_(user_ids)))
        connection.execute(delete(audit_events_table).where(audit_events_table.c.actor_id.in_(user_ids)))
        owned_deployments = select(deployments_table.c.id).where(deployments_table.c.owner_id.in_(user_ids))
        owned_inference = select(inference_requests_table.c.id).where(
            inference_requests_table.c.deployment_id.in_(owned_deployments)
        )
        connection.execute(delete(inference_items_table).where(inference_items_table.c.request_id.in_(owned_inference)))
        connection.execute(delete(inference_requests_table).where(inference_requests_table.c.deployment_id.in_(owned_deployments)))
        connection.execute(delete(challenger_replay_jobs_table).where(challenger_replay_jobs_table.c.deployment_id.in_(owned_deployments)))
        connection.execute(delete(deployment_revisions_table).where(deployment_revisions_table.c.deployment_id.in_(owned_deployments)))
        connection.execute(delete(deployments_table).where(deployments_table.c.owner_id.in_(user_ids)))
        connection.execute(delete(api_credentials_table).where(api_credentials_table.c.user_id.in_(user_ids)))
        connection.execute(
            delete(pipeline_step_runs_table).where(pipeline_step_runs_table.c.owner_id.in_(user_ids))
        )
        connection.execute(delete(pipeline_runs_table).where(pipeline_runs_table.c.owner_id.in_(user_ids)))
        connection.execute(delete(pipeline_versions_table).where(pipeline_versions_table.c.owner_id.in_(user_ids)))
        connection.execute(delete(pipelines_table).where(pipelines_table.c.owner_id.in_(user_ids)))
        connection.execute(
            delete(business_case_data_attachments_table)
            .where(business_case_data_attachments_table.c.owner_id.in_(user_ids))
        )
        connection.execute(delete(artifacts_table).where(artifacts_table.c.owner_id.in_(user_ids)))
        connection.execute(delete(business_cases_table).where(business_cases_table.c.owner_id.in_(user_ids)))
        connection.execute(
            delete(data_assets_table).where(or_(
                data_assets_table.c.owner_id.in_(user_ids),
                data_assets_table.c.uploaded_by.in_(user_ids),
                data_assets_table.c.deleted_by.in_(user_ids),
            ))
        )
        connection.execute(delete(user_accounts_table).where(user_accounts_table.c.id.in_(user_ids)))

    for user_id in user_ids:
        user_directory = (USER_REPOSITORY_ROOT / user_id).resolve()
        if user_directory.parent != USER_REPOSITORY_ROOT:
            raise RuntimeError(f"Unsafe test repository path: {user_directory}")
        shutil.rmtree(user_directory, ignore_errors=True)
