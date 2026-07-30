import hashlib

from app.core.storage import sha256_file


def test_sha256_file_streams_the_complete_artifact(tmp_path) -> None:
    payload = (b"bounded-model-artifact-" * 100_000) + b"tail"
    path = tmp_path / "model.joblib"
    path.write_bytes(payload)

    assert sha256_file(path, chunk_size=4096) == hashlib.sha256(payload).hexdigest()
