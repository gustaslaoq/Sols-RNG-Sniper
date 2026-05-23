from __future__ import annotations

from dataclasses import dataclass
import os

import psutil


@dataclass(frozen=True)
class PerformanceProfile:
    name: str
    ui_metrics_interval_ms: int
    log_batch_interval_ms: int
    update_check_timeout_s: int


LOW_END = PerformanceProfile(
    name="Low",
    ui_metrics_interval_ms=1500,
    log_batch_interval_ms=1200,
    update_check_timeout_s=10,
)

STANDARD = PerformanceProfile(
    name="Standard",
    ui_metrics_interval_ms=1000,
    log_batch_interval_ms=700,
    update_check_timeout_s=15,
)

HIGH_END = PerformanceProfile(
    name="High",
    ui_metrics_interval_ms=500,
    log_batch_interval_ms=400,
    update_check_timeout_s=20,
)


def detect_performance_profile() -> PerformanceProfile:
    forced = os.getenv("SLAOQ_SNIPER_PERFORMANCE", "").strip().lower()
    if forced in {"low", "standard", "high"}:
        return {"low": LOW_END, "standard": STANDARD, "high": HIGH_END}[forced]

    memory_gb = psutil.virtual_memory().total / (1024**3)
    cpu_count = psutil.cpu_count(logical=True) or 1
    if memory_gb <= 4.5 or cpu_count <= 4:
        return LOW_END
    if memory_gb >= 12 and cpu_count >= 8:
        return HIGH_END
    return STANDARD
