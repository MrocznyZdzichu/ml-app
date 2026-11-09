from collections.abc import Iterator, Mapping
from typing import BinaryIO
from uuid import uuid4

from requests_toolbelt.multipart.encoder import MultipartEncoder


class MultipartUpload:
    """A streamed requests body that can be replayed on 307/308 redirects."""

    def __init__(
        self, fields: Mapping[str, str], filename: str, stream: BinaryIO, content_type: str
    ) -> None:
        self._stream = stream
        self._fields = {**fields, "file": (filename, stream, content_type)}
        self._boundary = uuid4().hex
        self.seek(0)

    @property
    def content_type(self) -> str:
        return self._encoder.content_type

    def __len__(self) -> int:
        return self._encoder.len

    def __iter__(self) -> Iterator[bytes]:
        return iter(lambda: self.read(64 * 1024), b"")

    def read(self, size: int = -1) -> bytes:
        chunk = self._encoder.read(size)
        self._position += len(chunk)
        return chunk

    def tell(self) -> int:
        return self._position

    def seek(self, position: int) -> int:
        if position != 0:
            raise OSError("Multipart uploads can only be rewound to the start")
        self._stream.seek(0)
        self._encoder = MultipartEncoder(self._fields, boundary=self._boundary)
        self._position = 0
        return self._position
