import json
from pathlib import Path

from mlb_predictor.api.schemas import GameDetail, ModelMetadata, PredictionList


def test_dashboard_synthetic_fixture_matches_current_api_contract() -> None:
    path = Path(__file__).resolve().parents[1] / "frontend/src/demo-fixture.json"
    fixture = json.loads(path.read_text())
    assert "Synthetic demonstration only" in fixture["notice"]
    slate = PredictionList.model_validate(fixture["slate"])
    assert slate.count == 2
    for prediction in slate.predictions:
        assert prediction.provenance.prediction_kind == "synthetic_demo"
        assert prediction.provenance.code_version == "synthetic-demo"
        detail = GameDetail.model_validate(fixture["details"][str(prediction.game_pk)])
        assert detail.official_prediction == prediction
    assert {p.explanation.status for p in slate.predictions} == {"available", "not_retained"}
    assert (
        GameDetail.model_validate(fixture["details"]["8000003"]).prediction_status == "not_recorded"
    )
    ModelMetadata.model_validate(fixture["model"])
