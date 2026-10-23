"""Tests for Phase 6 Learning-to-Rank models, walk-forward embargo splits, and model card."""
import pandas as pd
import pytest

from blumberg_market_radar.data.ingestion import generate_synthetic_universe
from blumberg_market_radar.models.ranking import (
    RankerTrainingResult,
    RankingDataset,
    discretize_forward_returns,
    evaluate_ranker_vs_baseline,
    generate_model_card,
    prepare_ranking_dataset,
    train_lgbm_ranker,
)


@pytest.fixture(scope="module")
def sample_bars():
    return generate_synthetic_universe(["BEL", "HAL", "RELIANCE", "TRENT", "SUZLON"], num_days=140)


def test_discretize_forward_returns():
    dates = pd.date_range("2026-01-01", periods=3, freq="D")
    records = []
    for d in dates:
        for sym, ret in [("A", -0.05), ("B", 0.01), ("C", 0.08), ("D", 0.20)]:
            records.append({"date": d, "symbol": sym, "forward_return": ret})
    df = pd.DataFrame(records)

    grades = discretize_forward_returns(df, target_col="forward_return", num_grades=4)
    assert len(grades) == len(df)
    assert set(grades.unique()).issubset({0, 1, 2, 3})
    # Highest return in each group should have highest grade
    df["grade"] = grades
    for _, grp in df.groupby("date"):
        sorted_grp = grp.sort_values("forward_return")
        assert sorted_grp.iloc[-1]["grade"] == 3
        assert sorted_grp.iloc[0]["grade"] == 0


def test_prepare_ranking_dataset(sample_bars):
    horizon = 15
    embargo = 15
    dataset = prepare_ranking_dataset(
        sample_bars,
        future_horizon=horizon,
        num_grades=4,
        train_ratio=0.7,
        embargo_buffer=embargo,
    )

    assert isinstance(dataset, RankingDataset)
    assert not dataset.X_train.empty
    assert not dataset.X_test.empty
    assert len(dataset.X_train) == sum(dataset.group_train)
    assert len(dataset.X_test) == sum(dataset.group_test)

    # Verify embargo buffer: train end date must precede test start date
    assert dataset.train_date_range[1] < dataset.test_date_range[0]

    # Verify container unpacking and item access
    X_tr, _y_tr, _g_tr, _X_te, _y_te, _g_te = dataset
    assert len(X_tr) == len(dataset.X_train)
    assert dataset["feature_cols"] == dataset.feature_cols
    assert "return_20d" in dataset.feature_cols


def test_prepare_ranking_dataset_error_handling():
    with pytest.raises(ValueError, match="features_df must contain"):
        prepare_ranking_dataset(pd.DataFrame({"close": [100.0]}))

    # Too short dataset
    short_bars = generate_synthetic_universe(["BEL"], num_days=10)
    with pytest.raises(ValueError, match="No data points remain|Insufficient unique dates"):
        prepare_ranking_dataset(short_bars, future_horizon=20)


def test_train_lgbm_ranker_and_unpacking(sample_bars):
    dataset = prepare_ranking_dataset(
        sample_bars,
        future_horizon=10,
        num_grades=4,
        train_ratio=0.7,
        embargo_buffer=10,
    )

    res = train_lgbm_ranker(
        dataset.X_train,
        dataset.y_train,
        dataset.group_train,
        dataset.X_test,
        dataset.y_test,
        dataset.group_test,
        n_estimators=20,
    )

    assert isinstance(res, RankerTrainingResult)
    assert hasattr(res.model, "predict")
    assert isinstance(res.feature_importances, pd.Series)
    assert len(res.feature_importances) == dataset.X_train.shape[1]

    # Test unpacking
    model, _importances = res
    preds = model.predict(dataset.X_test)
    assert len(preds) == len(dataset.X_test)


def test_train_lgbm_fallback(sample_bars):
    dataset = prepare_ranking_dataset(
        sample_bars,
        future_horizon=10,
        num_grades=4,
        train_ratio=0.7,
        embargo_buffer=10,
    )

    # Force fallback by passing invalid lightgbm parameter that raises error or mock
    res = train_lgbm_ranker(
        dataset.X_train,
        dataset.y_train,
        dataset.group_train,
        objective="invalid_objective_that_triggers_fallback",
    )
    assert "Fallback" in res.model_type
    assert hasattr(res.model, "predict")


def test_evaluate_ranker_vs_baseline(sample_bars):
    dataset = prepare_ranking_dataset(
        sample_bars,
        future_horizon=10,
        num_grades=4,
        train_ratio=0.7,
        embargo_buffer=10,
    )

    res = train_lgbm_ranker(
        dataset.X_train,
        dataset.y_train,
        dataset.group_train,
        n_estimators=25,
    )

    metrics = evaluate_ranker_vs_baseline(
        dataset.test_df,
        res.model,
        dataset.feature_cols,
        rule_score_col="radar_score",
    )

    assert "ml_spearman_ic" in metrics
    assert "baseline_spearman_ic" in metrics
    assert "spearman_ic_delta" in metrics
    assert "ml_top3_excess_return_pct" in metrics
    assert "baseline_top3_excess_return_pct" in metrics
    assert "ml_top5_excess_return_pct" in metrics
    assert "ml_ndcg_at_5" in metrics
    assert "baseline_ndcg_at_5" in metrics
    assert "ml_top3_win_rate_pct" in metrics
    assert "outperformance_summary" in metrics

    assert isinstance(metrics["outperformance_summary"]["beats_baseline"], bool)
    assert metrics["num_test_dates"] > 0
    assert metrics["num_test_samples"] > 0


def test_generate_model_card(tmp_path, sample_bars):
    dataset = prepare_ranking_dataset(
        sample_bars,
        future_horizon=10,
        num_grades=4,
        train_ratio=0.7,
        embargo_buffer=10,
    )

    res = train_lgbm_ranker(
        dataset.X_train,
        dataset.y_train,
        dataset.group_train,
        n_estimators=20,
    )

    metrics = evaluate_ranker_vs_baseline(
        dataset.test_df,
        res.model,
        dataset.feature_cols,
    )

    card_file = tmp_path / "TEST_MODEL_CARD.md"
    card_dict = generate_model_card(
        metrics=metrics,
        train_date_range=dataset.train_date_range,
        test_date_range=dataset.test_date_range,
        feature_names=dataset.feature_cols,
        model_details=res.params,
        feature_importances=res.feature_importances,
        output_path=card_file,
    )

    assert card_file.exists()
    content = card_file.read_text(encoding="utf-8")
    assert "Model Card" in content
    assert "LambdaRank via LightGBM" in content
    assert "Spearman Rank Correlation (IC)" in content
    assert "Top-3 Out-of-Sample Excess Return" in content
    assert "Failure Modes, Edge Cases & Risk Mitigations" in content
    assert "Phase 6 Gate Compliance Checklist" in content
    assert "Governance Sign-Off" in content

    assert card_dict["model_version"] == "0.1.0-phase6"
    assert "metrics" in card_dict
