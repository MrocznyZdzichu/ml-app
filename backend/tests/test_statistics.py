from app.modules.analysis.statistics import describe_records


def test_describe_records_counts_numeric_columns() -> None:
    result = describe_records(
        [
            {"age": 30, "segment": "A"},
            {"age": 40, "segment": "B"},
            {"age": None, "segment": "A"},
        ]
    )

    assert result.row_count == 3
    assert result.columns["age"].count == 2
    assert result.columns["age"].mean == 35
    assert result.columns["segment"].unique == 2
