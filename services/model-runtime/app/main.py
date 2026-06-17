from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field

from app.model_loader import ModelLoader

app = FastAPI(title="ML App Model Runtime", version="0.1.0")
loader = ModelLoader()


class ScoreRequest(BaseModel):
    records: list[dict[str, Any]] = Field(min_length=1)


class ScoreResponse(BaseModel):
    predictions: list[Any]


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "model_loaded": str(loader.is_loaded).lower()}


@app.post("/score", response_model=ScoreResponse)
def score(payload: ScoreRequest) -> ScoreResponse:
    model = loader.load()
    if hasattr(model, "predict"):
        raw_predictions = model.predict(payload.records)
        predictions = raw_predictions.tolist() if hasattr(raw_predictions, "tolist") else list(raw_predictions)
    else:
        predictions = [0.0 for _ in payload.records]
    return ScoreResponse(predictions=predictions)
