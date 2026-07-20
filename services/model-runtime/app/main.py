from __future__ import annotations

import logging
import time
from typing import Any

import numpy as np
import pandas as pd
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from app.model_loader import ModelLoader

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("mlapp.model_runtime")

app = FastAPI(title="ML App Model Runtime", version="1.0.0")
loader = ModelLoader()


class RuntimeScoreRequest(BaseModel):
    model_artifact_uri: str = Field(min_length=1)
    model_hash: str = Field(default="", max_length=128)
    records: list[dict[str, Any]] = Field(min_length=1, max_length=1000)


class RuntimeScoreResponse(BaseModel):
    predictions: list[dict[str, Any]]


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/score", response_model=RuntimeScoreResponse)
def score(
    payload: RuntimeScoreRequest,
    request_id: str = Header(default="", alias="X-Request-ID"),
) -> RuntimeScoreResponse:
    started = time.monotonic()
    safe_request_id = request_id[:128] or "missing"
    try:
        bundle = loader.load(payload.model_artifact_uri, payload.model_hash)
        feature_columns = [str(item) for item in bundle["feature_columns"]]
        missing = sorted({column for column in feature_columns if any(column not in row for row in payload.records)})
        if missing:
            raise HTTPException(status_code=422, detail=f"Scoring input is missing features: {', '.join(missing)}")
        frame = pd.DataFrame.from_records(payload.records, columns=feature_columns)
        try:
            values = frame.to_numpy(dtype=np.float64)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail="Scoring features must match the numeric model contract") from exc
        if not np.isfinite(values).all():
            raise HTTPException(status_code=422, detail="Scoring features contain null, NaN or infinite values")
        estimator = bundle["estimator"]
        raw = np.asarray(estimator.predict(values))
        predictions: list[dict[str, Any]] = [
            {"prediction": _json_scalar(value)} for value in raw.tolist()
        ]
        if hasattr(estimator, "predict_proba"):
            probabilities = np.asarray(estimator.predict_proba(values))
            classes = np.asarray(getattr(estimator, "classes_", bundle.get("classes", []))).tolist()
            for row_index, item in enumerate(predictions):
                item["class_probabilities"] = {
                    str(label): float(probabilities[row_index, class_index])
                    for class_index, label in enumerate(classes)
                }
                if len(classes) == 2:
                    item["prediction_score"] = float(probabilities[row_index, 1])
        elif hasattr(estimator, "decision_function"):
            scores = np.asarray(estimator.decision_function(values))
            for row_index, item in enumerate(predictions):
                value = scores[row_index]
                item["prediction_score"] = (
                    float(value) if np.asarray(value).ndim == 0
                    else [_json_scalar(part) for part in np.asarray(value).tolist()]
                )
        logger.info(
            "score_succeeded request_id=%s records=%d latency_ms=%d artifact_hash=%s",
            safe_request_id,
            len(payload.records),
            round((time.monotonic() - started) * 1000),
            payload.model_hash[:12],
        )
        return RuntimeScoreResponse(predictions=predictions)
    except HTTPException:
        logger.warning("score_rejected request_id=%s records=%d", safe_request_id, len(payload.records))
        raise
    except (FileNotFoundError, ValueError) as exc:
        logger.error("score_failed request_id=%s error=%s", safe_request_id, exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("score_failed request_id=%s", safe_request_id)
        raise HTTPException(status_code=503, detail="Model execution failed") from exc


def _json_scalar(value: Any) -> Any:
    return value.item() if hasattr(value, "item") else value
