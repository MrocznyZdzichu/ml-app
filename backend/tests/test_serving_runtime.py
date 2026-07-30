import httpx2
import pytest

from app.modules.serving.runtime import (
    HttpModelRuntimeGateway,
    RuntimeInputError,
)


def test_http_runtime_gateway_reuses_the_injected_client() -> None:
    requests: list[httpx2.Request] = []

    def handle(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        return httpx2.Response(
            200,
            json={"predictions": [{"prediction": len(requests)}]},
        )

    client = httpx2.Client(
        base_url="http://model-runtime",
        transport=httpx2.MockTransport(handle),
    )
    gateway = HttpModelRuntimeGateway(
        base_url="http://model-runtime",
        client=client,
    )

    first = gateway.score(
        model_artifact_uri="file:///models/a.joblib",
        model_hash="hash",
        records=[{"value": 1}],
        request_id="request-1",
    )
    second = gateway.score(
        model_artifact_uri="file:///models/a.joblib",
        model_hash="hash",
        records=[{"value": 2}],
        request_id="request-2",
    )

    assert first == [{"prediction": 1}]
    assert second == [{"prediction": 2}]
    assert [request.headers["x-request-id"] for request in requests] == [
        "request-1",
        "request-2",
    ]


def test_http_runtime_gateway_preserves_input_error_semantics() -> None:
    client = httpx2.Client(
        base_url="http://model-runtime",
        transport=httpx2.MockTransport(
            lambda request: httpx2.Response(422, text="missing feature")
        ),
    )
    gateway = HttpModelRuntimeGateway(
        base_url="http://model-runtime",
        client=client,
    )

    with pytest.raises(RuntimeInputError, match="missing feature"):
        gateway.score(
            model_artifact_uri="file:///models/a.joblib",
            model_hash="hash",
            records=[{}],
            request_id="request-1",
        )
