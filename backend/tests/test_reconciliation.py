"""Tests for provider data reconciliation / conflict detection."""
from __future__ import annotations

from decimal import Decimal

from app.providers.reconciliation import DataReconciler


class TestDataReconciler:
    def test_no_conflict_when_equal(self) -> None:
        r = DataReconciler()
        result = r.compare(
            "revenue", "FY2024",
            "yahoo", Decimal("250000000000"),
            "alpha_vantage", Decimal("250000000000"),
        )
        assert result is None

    def test_no_conflict_within_threshold(self) -> None:
        r = DataReconciler(threshold_pct=Decimal("1.0"))
        result = r.compare(
            "revenue", "FY2024",
            "yahoo", Decimal("250000000000"),
            "alpha_vantage", Decimal("250500000000"),
        )
        assert result is None

    def test_conflict_beyond_threshold(self) -> None:
        r = DataReconciler(threshold_pct=Decimal("1.0"))
        result = r.compare(
            "revenue", "FY2024",
            "yahoo", Decimal("250000000000"),
            "alpha_vantage", Decimal("260000000000"),
        )
        assert result is not None
        assert result.metric == "revenue"
        assert result.source_a == "yahoo"
        assert result.source_b == "alpha_vantage"
        assert result.difference_pct > Decimal("1.0")

    def test_both_zero_no_conflict(self) -> None:
        r = DataReconciler()
        result = r.compare(
            "revenue", "FY2024",
            "a", Decimal("0"),
            "b", Decimal("0"),
        )
        assert result is None

    def test_one_zero_is_conflict(self) -> None:
        r = DataReconciler(threshold_pct=Decimal("1.0"))
        result = r.compare(
            "revenue", "FY2024",
            "a", Decimal("100"),
            "b", Decimal("0"),
        )
        assert result is not None
        assert result.difference_pct == Decimal("100.00")

    def test_custom_threshold(self) -> None:
        r = DataReconciler(threshold_pct=Decimal("5.0"))
        result = r.compare(
            "revenue", "FY2024",
            "a", Decimal("100"),
            "b", Decimal("104"),
        )
        assert result is None

    def test_negative_values(self) -> None:
        r = DataReconciler(threshold_pct=Decimal("1.0"))
        result = r.compare(
            "net_income", "FY2024",
            "a", Decimal("-100"),
            "b", Decimal("-110"),
        )
        assert result is not None


class TestReconcileStatements:
    def test_detects_conflicts_across_statement_items(self) -> None:
        r = DataReconciler(threshold_pct=Decimal("1.0"))
        stmt_a = {
            "revenue": Decimal("250000000000"),
            "net_income": Decimal("50000000000"),
            "operating_expenses": Decimal("30000000000"),
        }
        stmt_b = {
            "revenue": Decimal("250000000000"),
            "net_income": Decimal("55000000000"),
            "operating_expenses": Decimal("30100000000"),
        }
        conflicts = r.reconcile_statements(
            "yahoo", stmt_a,
            "alpha_vantage", stmt_b,
            period="FY2024",
        )
        conflict_metrics = {c.metric for c in conflicts}
        assert "net_income" in conflict_metrics
        assert "revenue" not in conflict_metrics

    def test_no_conflicts_when_identical(self) -> None:
        r = DataReconciler()
        stmt = {
            "revenue": Decimal("100"),
            "net_income": Decimal("50"),
        }
        conflicts = r.reconcile_statements(
            "a", stmt, "b", stmt, period="FY2024",
        )
        assert conflicts == []

    def test_only_compares_common_keys(self) -> None:
        r = DataReconciler(threshold_pct=Decimal("1.0"))
        stmt_a = {"revenue": Decimal("100"), "extra_a": Decimal("999")}
        stmt_b = {"revenue": Decimal("100"), "extra_b": Decimal("888")}
        conflicts = r.reconcile_statements(
            "a", stmt_a, "b", stmt_b, period="FY2024",
        )
        assert conflicts == []
