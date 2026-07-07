"""Generación de reportes exportables por servicio."""

from __future__ import annotations

from typing import Any

import pandas as pd

from cargo_store import get_chicken_count, get_chicken_notes
from data_processor import (
    ServiceSummary,
    cargo_average,
    label_for,
)

EXPORT_SENSOR_FIELDS = (
    "set_point",
    "temp_supply_1",
    "return_air",
    "cargo_1_temp",
    "cargo_2_temp",
    "cargo_3_temp",
    "cargo_4_temp",
    "ambient_air",
    "co2_reading",
    "o2_reading",
    "relative_humidity",
    "avl",
    "capacity_load",
)


def _round_value(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 2)


def build_services_export_dataframe(
    services: list[ServiceSummary],
    selected_ids: list[int],
    cargo_data: dict[str, dict[str, Any]],
) -> pd.DataFrame:
    selected = set(selected_ids)
    rows: list[dict[str, Any]] = []

    for service in services:
        if service.service_id not in selected:
            continue

        row: dict[str, Any] = {
            "Servicio": service.service_id,
            "Inicio": service.start.strftime("%Y-%m-%d %H:%M:%S"),
            "Fin": service.end.strftime("%Y-%m-%d %H:%M:%S"),
            "Duración (h)": _round_value(service.duration_hours),
            "Lecturas válidas": service.valid_count,
            "Cantidad pollos": get_chicken_count(service, cargo_data),
            "Notas carga": get_chicken_notes(service, cargo_data),
            "Zona prom. pollitos (°C)": _round_value(cargo_average(service)),
        }

        for field in EXPORT_SENSOR_FIELDS:
            row[f"{label_for(field)} prom."] = _round_value(service.averages.get(field))

        rows.append(row)

    return pd.DataFrame(rows)


def export_filename(prefix: str = "promedios_servicios") -> str:
    from datetime import datetime

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{prefix}_{stamp}.csv"
