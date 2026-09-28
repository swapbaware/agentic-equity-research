"""Provider data reconciliation — cross-source conflict detection.

When the same financial metric is available from multiple providers, the
reconciler compares values and flags DATA_CONFLICT when they disagree beyond
a configurable threshold. The application layer decides resolution.
"""
from __future__ import annotations

from decimal import Decimal

from app.providers.provenance import DataConflict


class DataReconciler:
    """Compare values from multiple providers and detect conflicts."""

    def __init__(self, *, threshold_pct: Decimal = Decimal("1.0")) -> None:
        self._threshold_pct = threshold_pct

    def compare(
        self,
        metric: str,
        period: str,
        source_a: str,
        value_a: Decimal,
        source_b: str,
        value_b: Decimal,
        *,
        unit: str = "INR",
    ) -> DataConflict | None:
        """Return a DataConflict if the two values disagree beyond threshold, else None."""
        if value_a == value_b:
            return None

        if value_a == Decimal("0") and value_b == Decimal("0"):
            return None

        base = max(abs(value_a), abs(value_b))
        if base == Decimal("0"):
            diff_pct = Decimal("100")
        else:
            diff_pct = (abs(value_a - value_b) / base * Decimal("100")).quantize(Decimal("0.01"))

        if diff_pct <= self._threshold_pct:
            return None

        return DataConflict(
            metric=metric,
            period=period,
            source_a=source_a,
            value_a=value_a,
            source_b=source_b,
            value_b=value_b,
            unit=unit,
            difference_pct=diff_pct,
        )

    def reconcile_statements(
        self,
        source_a_name: str,
        statement_a: dict[str, Decimal],
        source_b_name: str,
        statement_b: dict[str, Decimal],
        *,
        period: str,
        unit: str = "INR",
    ) -> list[DataConflict]:
        """Compare all overlapping line items from two financial statements."""
        conflicts: list[DataConflict] = []
        common_keys = set(statement_a.keys()) & set(statement_b.keys())
        for key in sorted(common_keys):
            conflict = self.compare(
                metric=key,
                period=period,
                source_a=source_a_name,
                value_a=statement_a[key],
                source_b=source_b_name,
                value_b=statement_b[key],
                unit=unit,
            )
            if conflict is not None:
                conflicts.append(conflict)
        return conflicts
