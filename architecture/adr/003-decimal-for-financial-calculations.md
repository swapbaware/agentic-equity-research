# ADR-003: decimal.Decimal for All Financial Calculations

## Status

Accepted

## Date

2026-09-28

## Context

Financial calculations (ratios, valuations, growth rates, portfolio values) require exact decimal arithmetic. IEEE 754 floating-point (Python `float`) introduces rounding errors that are unacceptable for:
- Displaying financial data to users (e.g., `0.1 + 0.2 = 0.30000000000000004`)
- Valuation models where small errors compound
- Regulatory compliance where exact figures matter
- Reproducibility of calculations

## Decision

Use Python `decimal.Decimal` for all monetary values, financial ratios, percentages, and valuation model inputs/outputs throughout the backend.

## Implementation

- **Pydantic models**: Use `Decimal` type for all financial fields
- **PostgreSQL**: Use `NUMERIC` column type (arbitrary precision), never `FLOAT` or `DOUBLE PRECISION`
- **SQLAlchemy**: Map to `Numeric(precision, scale)` with appropriate precision
- **API responses**: Serialize as strings to preserve precision (JSON `number` can lose precision)
- **Rounding**: Define explicit rounding rules per context:
  - Financial ratios: 4 decimal places
  - Percentages: 2 decimal places
  - Currency values: 2 decimal places (INR)
  - Per-share values: 2 decimal places

## Consequences

- Slightly more verbose code (cannot use `+`, `-`, `*`, `/` with mixed float/Decimal)
- JSON serialization requires string representation for exact values
- LLM outputs containing financial numbers must be parsed to Decimal and validated against stored data
- Performance impact negligible for the scale of calculations in this platform
- Third-party libraries that return floats need conversion at the boundary
