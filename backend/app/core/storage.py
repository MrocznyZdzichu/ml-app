from dataclasses import dataclass

from app.core.config import settings


@dataclass(frozen=True)
class ObjectStorageLocation:
    bucket: str
    key: str

    @property
    def uri(self) -> str:
        return f"s3://{self.bucket}/{self.key}"


class ObjectStorageNamer:
    def __init__(self, bucket: str | None = None) -> None:
        self.bucket = bucket or settings.object_storage_bucket

    def dataset_key(self, owner_id: str, dataset_id: str, filename: str) -> ObjectStorageLocation:
        safe_name = filename.replace("\\", "_").replace("/", "_")
        return ObjectStorageLocation(
            bucket=self.bucket,
            key=f"users/{owner_id}/datasets/{dataset_id}/{safe_name}",
        )

    def artifact_key(self, owner_id: str, artifact_id: str, filename: str) -> ObjectStorageLocation:
        safe_name = filename.replace("\\", "_").replace("/", "_")
        return ObjectStorageLocation(
            bucket=self.bucket,
            key=f"users/{owner_id}/artifacts/{artifact_id}/{safe_name}",
        )
