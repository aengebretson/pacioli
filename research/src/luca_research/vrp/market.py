"""Strict historical-cutoff joins for official daily VIX term files."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import math
import re
from typing import Mapping, Sequence

from .calibration import VixTermObservation


_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class VixTenorConvention:
    label: str
    official_target_tenor: str
    model_trading_days: int
    mapping: str


VIX_TENOR_CONVENTIONS = (
    VixTenorConvention("VIX9D", "9_calendar_days", 6, "round(9*252/365)"),
    VixTenorConvention("VIX", "30_calendar_days", 21, "round(30*252/365)"),
    VixTenorConvention("VIX3M", "3_calendar_months", 63, "3/12*252"),
    VixTenorConvention("VIX6M", "6_calendar_months", 126, "6/12*252"),
    VixTenorConvention("VIX1Y", "1_calendar_year", 252, "252"),
)


@dataclass(frozen=True)
class VixDailyClose:
    label: str
    observation_date: str
    close_percent: float
    source_sha256: str
    source_url: str

    def __post_init__(self) -> None:
        if self.label not in {item.label for item in VIX_TENOR_CONVENTIONS}:
            raise ValueError("unsupported VIX term label")
        try:
            date.fromisoformat(self.observation_date)
        except ValueError as exc:
            raise ValueError("observation_date must be an ISO calendar date") from exc
        if not math.isfinite(self.close_percent) or self.close_percent <= 0.0:
            raise ValueError("close_percent must be positive and finite")
        if not _SHA256.fullmatch(self.source_sha256):
            raise ValueError("source_sha256 must be a lowercase SHA-256 digest")
        if not isinstance(self.source_url, str) or not self.source_url:
            raise ValueError("source_url must be nonempty")


@dataclass(frozen=True)
class VixJoinEntry:
    label: str
    official_target_tenor: str
    model_trading_days: int
    tenor_mapping: str
    status: str
    exclusion_reason: str | None
    observation_date: str | None
    close_percent: float | None
    source_sha256: str | None
    source_url: str | None


@dataclass(frozen=True)
class VixCutoffJoin:
    cutoff_date: str
    information_cutoff_utc: str
    assumed_close_time: str
    exact_date_required: bool
    observations: tuple[VixTermObservation, ...]
    entries: tuple[VixJoinEntry, ...]
    limitations: tuple[str, ...]


def join_vix_closes_at_cutoff(
    histories: Mapping[str, Sequence[VixDailyClose]],
    *,
    cutoff_date: str,
    information_cutoff_utc: str,
    assumed_close_time: str,
) -> VixCutoffJoin:
    """Join each named term on the exact cutoff date or exclude it explicitly.

    No prior close is carried forward.  This prevents a missing or stale term
    from becoming an apparently same-cutoff pricing observation.
    """

    parsed_cutoff = date.fromisoformat(cutoff_date)
    if not information_cutoff_utc.startswith(cutoff_date) or not information_cutoff_utc.endswith(
        "Z"
    ):
        raise ValueError("information_cutoff_utc must be a UTC timestamp on cutoff_date")
    if not isinstance(assumed_close_time, str) or not assumed_close_time:
        raise ValueError("assumed_close_time must be nonempty")

    entries: list[VixJoinEntry] = []
    observations: list[VixTermObservation] = []
    for convention in VIX_TENOR_CONVENTIONS:
        candidates = [
            item
            for item in histories.get(convention.label, ())
            if item.observation_date == parsed_cutoff.isoformat()
        ]
        if not candidates:
            entries.append(
                VixJoinEntry(
                    label=convention.label,
                    official_target_tenor=convention.official_target_tenor,
                    model_trading_days=convention.model_trading_days,
                    tenor_mapping=convention.mapping,
                    status="excluded",
                    exclusion_reason="no_exact_daily_close_on_cutoff_date",
                    observation_date=None,
                    close_percent=None,
                    source_sha256=None,
                    source_url=None,
                )
            )
            continue
        if len(candidates) != 1:
            entries.append(
                VixJoinEntry(
                    label=convention.label,
                    official_target_tenor=convention.official_target_tenor,
                    model_trading_days=convention.model_trading_days,
                    tenor_mapping=convention.mapping,
                    status="excluded",
                    exclusion_reason="duplicate_daily_closes_on_cutoff_date",
                    observation_date=cutoff_date,
                    close_percent=None,
                    source_sha256=None,
                    source_url=None,
                )
            )
            continue
        selected = candidates[0]
        entries.append(
            VixJoinEntry(
                label=convention.label,
                official_target_tenor=convention.official_target_tenor,
                model_trading_days=convention.model_trading_days,
                tenor_mapping=convention.mapping,
                status="included",
                exclusion_reason=None,
                observation_date=selected.observation_date,
                close_percent=selected.close_percent,
                source_sha256=selected.source_sha256,
                source_url=selected.source_url,
            )
        )
        observations.append(
            VixTermObservation(
                label=selected.label,
                maturity_trading_days=convention.model_trading_days,
                value_percent=selected.close_percent,
            )
        )

    return VixCutoffJoin(
        cutoff_date=cutoff_date,
        information_cutoff_utc=information_cutoff_utc,
        assumed_close_time=assumed_close_time,
        exact_date_required=True,
        observations=tuple(observations),
        entries=tuple(entries),
        limitations=(
            "The supplied Cboe files are retrospective daily OHLC histories, not publication vintages or timestamped close events.",
            "The information cutoff uses an explicit assumed close-time availability; contemporaneous receipt was not observed.",
            "Calendar target tenors are mapped to integer 252-day model periods and therefore do not reproduce Cboe minute weighting, holidays, or interpolation exactly.",
            "VIX term indices summarize option-implied variance at different constant maturities; they are calibration observations, not option trade prints.",
        ),
    )
