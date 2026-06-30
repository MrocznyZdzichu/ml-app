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
from app.modules.datasets.repository import data_assets_table
from app.modules.pipelines.repository import (
    metadata as pipeline_metadata,
    pipeline_runs_table,
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
