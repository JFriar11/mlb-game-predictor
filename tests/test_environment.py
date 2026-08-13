from mlb_predictor.features.environment_builder import parse_wind


def test_wind_parser_produces_oriented_components() -> None:
    assert parse_wind("12 mph, Out To CF") == (12.0, 12.0, 0.0)
    assert parse_wind("10 mph, In From CF") == (10.0, -10.0, 0.0)
    assert parse_wind("8 mph, L To R") == (8.0, 0.0, 8.0)
    assert parse_wind(None) == (0.0, 0.0, 0.0)
