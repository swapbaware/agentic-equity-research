"""Data provenance tracking for provider-sourced records.

Every record imported from an external provider carries provenance metadata
so the application layer can trace data back to its source.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class DataQuality(StrEnum):
    AUTHORITATIVE = "AUTHORITATIVE"
    DERIVED = "DERIVED"
    ESTIMATED = "ESTIMATED"
    UNVERIFIED = "UNVERIFIED"


class SourceType(StrEnum):
    EXCHANGE = "EXCHANGE"
    REGULATORY = "REGULATORY"
    MARKET_DATA = "MARKET_DATA"
    FILING = "FILING"
    NEWS = "NEWS"
    DERIVED = "DERIVED"


class Confidence(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class DataProvenance(BaseModel):
    model_config = ConfigDict(frozen=True)

    source: str
    source_type: SourceType
    source_url: str | None = None
    retrieved_at: datetime
    published_at: datetime | None = None
    provider: str
    provider_version: str | None = None
    data_period: str | None = None
    data_quality: DataQuality = DataQuality.DERIVED
    confidence: Confidence = Confidence.MEDIUM


class DataConflict(BaseModel):
    model_config = ConfigDict(frozen=True)

    metric: str
    period: str
    source_a: str
    value_a: Decimal
    source_b: str
    value_b: Decimal
    unit: str = "INR"
    difference_pct: Decimal
    resolved_value: Decimal | None = None
    resolution: str | None = None
