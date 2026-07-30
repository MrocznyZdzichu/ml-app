from sqlalchemy import JSON, Column, DateTime, MetaData, String, Table, Text

BUSINESS_CASE_SCHEMA = "mlapp"
metadata = MetaData(schema=BUSINESS_CASE_SCHEMA)

business_cases_table = Table(
    "business_cases",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("owner_id", String(64), nullable=False, index=True),
    Column("name", String(255), nullable=False),
    Column("description", Text, nullable=False, default=""),
    Column("problem_type", String(64), nullable=False),
    Column("status", String(32), nullable=False),
    Column("business_owner", String(255), nullable=False, default=""),
    Column("primary_metric", String(128), nullable=False, default=""),
    Column("target_column", String(255), nullable=False, default=""),
    Column("business_goal", Text, nullable=False, default=""),
    Column("success_criteria", Text, nullable=False, default=""),
    Column("created_by", String(64), nullable=False),
    Column("updated_by", String(64), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

artifacts_table = Table(
    "artifacts",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("owner_id", String(64), nullable=False, index=True),
    Column("type", String(64), nullable=False),
    Column("reference_id", String(128), nullable=False, index=True),
    Column("origin", String(64), nullable=False),
    Column("business_case_id", String(64), nullable=True, index=True),
    Column("external_notes", Text, nullable=False, default=""),
    Column("metadata", JSON, nullable=False, default=dict),
    Column("created_by", String(64), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

business_case_data_attachments_table = Table(
    "business_case_data_attachments",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("owner_id", String(64), nullable=False, index=True),
    Column("business_case_id", String(64), nullable=False, index=True),
    Column("artifact_id", String(64), nullable=False, index=True),
    Column("data_asset_id", String(64), nullable=False, index=True),
    Column("data_asset_kind", String(32), nullable=False),
    Column("role", String(64), nullable=False),
    Column("context_note", Text, nullable=False, default=""),
    Column("primary_key_column", String(255), nullable=False, default=""),
    Column("target_column", String(255), nullable=False, default=""),
    Column("created_by", String(64), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)
