"""Procesamiento y validación de telemetría del furgón refrigerado."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import mean, median, stdev
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

LOCAL_TZ = ZoneInfo("America/Bogota")
SERVICE_GAP_HOURS = 5
MIN_SERVICE_HOURS = 1

SENSOR_RANGES: dict[str, tuple[float, float]] = {
    "set_point": (-40, 40),
    "temp_supply_1": (-40, 40),
    "return_air": (-40, 40),
    "evaporation_coil": (-40, 40),
    "condensation_coil": (-40, 40),
    "ambient_air": (-10, 50),
    "cargo_1_temp": (5, 50),
    "cargo_2_temp": (5, 50),
    "cargo_3_temp": (5, 50),
    "cargo_4_temp": (5, 50),
    "relative_humidity": (20, 99),
    "avl": (0, 230),
    "co2_reading": (0, 24),
    "o2_reading": (0, 24),
    "capacity_load": (0, 100),
}

DISCARD_ZERO_FIELDS = ("return_air", "temp_supply_1")

CARGO_FIELDS = ("cargo_1_temp", "cargo_2_temp", "cargo_3_temp", "cargo_4_temp")
TEMP_AVG_FIELDS = (
    "temp_supply_1",
    "return_air",
    "cargo_1_temp",
    "cargo_2_temp",
    "cargo_3_temp",
    "cargo_4_temp",
    "set_point",
    "ambient_air",
)

TEMP_CHART_FIELDS = (
    "set_point",
    "temp_supply_1",
    "return_air",
    "ambient_air",
    *CARGO_FIELDS,
)

TEMP_CHART_GROUPS: dict[str, tuple[str, ...]] = {
    "Sistema reefer": ("set_point", "temp_supply_1", "return_air"),
    "Zonas de pollitos": CARGO_FIELDS,
    "Ambiente exterior": ("ambient_air",),
}

TIMELINE_TABLE_FIELDS = (
    "set_point",
    "temp_supply_1",
    "return_air",
    "cargo_1_temp",
    "cargo_2_temp",
    "cargo_3_temp",
    "cargo_4_temp",
    "co2_reading",
    "avl",
    "relative_humidity",
    "ambient_air",
    "capacity_load",
    "power_state",
)

TIMELINE_DELTA_FIELDS = (
    "temp_supply_1",
    "return_air",
    *CARGO_FIELDS,
    "co2_reading",
)

SIGNIFICANCE_THRESHOLDS = {
    "temp_supply_1": 1.5,
    "return_air": 1.5,
    "cargo_1_temp": 2.0,
    "cargo_2_temp": 2.0,
    "cargo_3_temp": 2.0,
    "cargo_4_temp": 2.0,
    "co2_reading": 1.0,
    "relative_humidity": 5.0,
    "avl": 20.0,
}

SENSOR_LABELS: dict[str, str] = {
    "set_point": "Set point",
    "temp_supply_1": "Suministro",
    "return_air": "Retorno",
    "evaporation_coil": "Evaporador",
    "condensation_coil": "Condensador",
    "ambient_air": "Ambiente exterior",
    "cargo_1_temp": "Zona 1",
    "cargo_2_temp": "Zona 2",
    "cargo_3_temp": "Zona 3",
    "cargo_4_temp": "Zona 4",
    "relative_humidity": "Humedad relativa",
    "avl": "Ventilación (cfm)",
    "co2_reading": "CO₂",
    "o2_reading": "O₂",
    "capacity_load": "Carga compresor",
    "power_state": "Estado encendido",
}


@dataclass
class CleanRecord:
    timestamp: datetime
    values: dict[str, float | int | str]
    invalid_fields: list[str] = field(default_factory=list)


@dataclass
class DaySummary:
    day: date
    service_ids: list[int]
    service_count: int
    total_readings: int
    avg_return_air: float | None
    avg_supply: float | None
    avg_cargo: float | None
    avg_co2: float | None
    avg_avl: float | None


@dataclass
class ServiceSummary:
    service_id: int
    start: datetime
    end: datetime
    duration_hours: float
    raw_count: int
    valid_count: int
    discarded_count: int
    averages: dict[str, float | None]
    medians: dict[str, float | None]
    stddevs: dict[str, float | None]
    min_values: dict[str, float | None]
    max_values: dict[str, float | None]
    power_on_ratio: float | None
    records: list[CleanRecord]


def parse_timestamp(value: dict[str, str] | str) -> datetime:
    if isinstance(value, dict):
        raw = value["$date"]
    else:
        raw = value
    dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(LOCAL_TZ)


def is_in_range(field: str, value: Any) -> bool:
    if value is None:
        return False
    if field in DISCARD_ZERO_FIELDS and value == 0:
        return False
    if field not in SENSOR_RANGES:
        return True
    low, high = SENSOR_RANGES[field]
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return False
    return low <= numeric <= high


def clean_record(raw: dict[str, Any]) -> CleanRecord | None:
    timestamp = parse_timestamp(raw["created_at"])
    values: dict[str, float | int | str] = {}
    invalid_fields: list[str] = []

    if raw.get("return_air") == 0 or raw.get("temp_supply_1") == 0:
        return None

    for key, value in raw.items():
        if key in ("_id", "created_at"):
            continue
        if key == "power_state":
            if value in (0, 1):
                values[key] = int(value)
            else:
                invalid_fields.append(key)
            continue
        if key == "controlling_mode":
            values[key] = str(value)
            continue
        if key in SENSOR_RANGES:
            if is_in_range(key, value):
                values[key] = float(value)
            else:
                invalid_fields.append(key)
            continue
        values[key] = value

    if "return_air" not in values or "temp_supply_1" not in values:
        return None

    return CleanRecord(timestamp=timestamp, values=values, invalid_fields=invalid_fields)


def _safe_stats(values: list[float]) -> tuple[float | None, float | None, float | None]:
    if not values:
        return None, None, None
    avg = mean(values)
    med = median(values)
    sd = stdev(values) if len(values) > 1 else 0.0
    return avg, med, sd


def summarize_records(service_id: int, records: list[CleanRecord]) -> ServiceSummary:
    numeric_fields = set(SENSOR_RANGES) | {"power_state"}
    series: dict[str, list[float]] = {f: [] for f in numeric_fields}

    for record in records:
        for key in numeric_fields:
            value = record.values.get(key)
            if value is not None and key != "power_state":
                series[key].append(float(value))

    averages: dict[str, float | None] = {}
    medians: dict[str, float | None] = {}
    stddevs: dict[str, float | None] = {}
    min_values: dict[str, float | None] = {}
    max_values: dict[str, float | None] = {}

    for key, values in series.items():
        avg, med, sd = _safe_stats(values)
        averages[key] = avg
        medians[key] = med
        stddevs[key] = sd
        min_values[key] = min(values) if values else None
        max_values[key] = max(values) if values else None

    power_values = [record.values["power_state"] for record in records if "power_state" in record.values]
    power_on_ratio = mean(power_values) if power_values else None

    start = records[0].timestamp
    end = records[-1].timestamp
    duration = (end - start).total_seconds() / 3600

    return ServiceSummary(
        service_id=service_id,
        start=start,
        end=end,
        duration_hours=duration,
        raw_count=len(records),
        valid_count=len(records),
        discarded_count=0,
        averages=averages,
        medians=medians,
        stddevs=stddevs,
        min_values=min_values,
        max_values=max_values,
        power_on_ratio=power_on_ratio,
        records=records,
    )


def service_duration_hours(records: list[CleanRecord]) -> float:
    if len(records) < 2:
        return 0.0
    return (records[-1].timestamp - records[0].timestamp).total_seconds() / 3600


def detect_services(records: list[CleanRecord]) -> list[list[CleanRecord]]:
    if not records:
        return []

    records = sorted(records, key=lambda r: r.timestamp)
    gap = timedelta(hours=SERVICE_GAP_HOURS)
    services: list[list[CleanRecord]] = [[records[0]]]

    for record in records[1:]:
        if record.timestamp - services[-1][-1].timestamp > gap:
            services.append([record])
        else:
            services[-1].append(record)

    return services


def filter_valid_services(grouped: list[list[CleanRecord]]) -> tuple[list[list[CleanRecord]], int]:
    valid: list[list[CleanRecord]] = []
    discarded_short = 0
    for group in grouped:
        if service_duration_hours(group) < MIN_SERVICE_HOURS:
            discarded_short += 1
            continue
        valid.append(group)
    return valid, discarded_short


def load_and_process(json_path: str | Path) -> tuple[list[ServiceSummary], dict[str, int]]:
    path = Path(json_path)
    with path.open(encoding="utf-8") as handle:
        raw_data = json.load(handle)

    stats = {
        "total_raw": len(raw_data),
        "discarded_bad_zero": 0,
        "discarded_invalid_core": 0,
        "discarded_short_duration": 0,
        "kept": 0,
        "partial_invalid_fields": 0,
    }

    clean_records: list[CleanRecord] = []
    for raw in raw_data:
        if raw.get("return_air") == 0 or raw.get("temp_supply_1") == 0:
            stats["discarded_bad_zero"] += 1
            continue

        cleaned = clean_record(raw)
        if cleaned is None:
            stats["discarded_invalid_core"] += 1
            continue

        stats["kept"] += 1
        if cleaned.invalid_fields:
            stats["partial_invalid_fields"] += 1
        clean_records.append(cleaned)

    grouped = detect_services(clean_records)
    grouped, stats["discarded_short_duration"] = filter_valid_services(grouped)
    summaries: list[ServiceSummary] = []
    for index, group in enumerate(grouped, start=1):
        summaries.append(summarize_records(index, group))

    return summaries, stats


def compare_services(
    base: ServiceSummary,
    other: ServiceSummary,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    fields = sorted(set(TEMP_AVG_FIELDS) | {"co2_reading", "relative_humidity", "avl", "capacity_load"})

    for field_name in fields:
        base_avg = base.averages.get(field_name)
        other_avg = other.averages.get(field_name)
        if base_avg is None or other_avg is None:
            continue

        delta = other_avg - base_avg
        threshold = SIGNIFICANCE_THRESHOLDS.get(field_name, 2.0)
        rows.append(
            {
                "campo": field_name,
                "servicio_base": round(base_avg, 2),
                "servicio_comparado": round(other_avg, 2),
                "delta": round(delta, 2),
                "significativo": abs(delta) >= threshold,
                "umbral": threshold,
            }
        )

    return rows


def service_label(service: ServiceSummary) -> str:
    start_day = service.start.strftime("%Y-%m-%d")
    start_time = service.start.strftime("%H:%M")
    end_time = service.end.strftime("%H:%M")
    if service.start.date() == service.end.date():
        return f"Servicio {service.service_id:03d} · {start_day} · {start_time}-{end_time}"
    end_day = service.end.strftime("%Y-%m-%d")
    return f"Servicio {service.service_id:03d} · {start_day} {start_time} → {end_day} {end_time}"


def service_storage_key(service: ServiceSummary) -> str:
    return f"{service.start.isoformat()}|{service.end.isoformat()}"


def cargo_average(service: ServiceSummary) -> float | None:
    values = [
        service.averages.get(field)
        for field in CARGO_FIELDS
        if service.averages.get(field) is not None
    ]
    return mean(values) if values else None


def services_for_day(services: list[ServiceSummary], day) -> list[ServiceSummary]:
    return [
        service
        for service in services
        if service.start.date() <= day <= service.end.date()
    ]


def records_on_day(records: list[CleanRecord], day) -> list[CleanRecord]:
    return [record for record in records if record.timestamp.date() == day]


def power_on_intervals(records: list[CleanRecord]) -> list[tuple[datetime, datetime]]:
    sorted_records = sorted(records, key=lambda record: record.timestamp)
    if not sorted_records:
        return []

    raw_intervals: list[tuple[datetime, datetime]] = []
    for index, record in enumerate(sorted_records):
        if record.values.get("power_state") != 1:
            continue
        start = record.timestamp
        end = sorted_records[index + 1].timestamp if index + 1 < len(sorted_records) else start
        raw_intervals.append((start, end))

    if not raw_intervals:
        return []

    merged: list[tuple[datetime, datetime]] = [raw_intervals[0]]
    for start, end in raw_intervals[1:]:
        prev_start, prev_end = merged[-1]
        if start <= prev_end:
            merged[-1] = (prev_start, max(prev_end, end))
        else:
            merged.append((start, end))
    return merged


def _average_field_from_records(records: list[CleanRecord], field: str) -> float | None:
    values = [
        float(record.values[field])
        for record in records
        if field in record.values and record.values[field] is not None
    ]
    return mean(values) if values else None


def build_day_summaries(services: list[ServiceSummary]) -> list[DaySummary]:
    records_by_day: dict[date, list[CleanRecord]] = {}
    services_by_day: dict[date, set[int]] = {}

    for service in services:
        for record in service.records:
            day = record.timestamp.date()
            records_by_day.setdefault(day, []).append(record)
            services_by_day.setdefault(day, set()).add(service.service_id)

    summaries: list[DaySummary] = []
    for day in sorted(records_by_day):
        day_records_list = records_by_day[day]
        active_service_ids = sorted(services_by_day[day])
        cargo_values = [
            _average_field_from_records(day_records_list, field)
            for field in CARGO_FIELDS
        ]
        valid_cargo = [value for value in cargo_values if value is not None]
        summaries.append(
            DaySummary(
                day=day,
                service_ids=active_service_ids,
                service_count=len(active_service_ids),
                total_readings=len(day_records_list),
                avg_return_air=_average_field_from_records(day_records_list, "return_air"),
                avg_supply=_average_field_from_records(day_records_list, "temp_supply_1"),
                avg_cargo=mean(valid_cargo) if valid_cargo else None,
                avg_co2=_average_field_from_records(day_records_list, "co2_reading"),
                avg_avl=_average_field_from_records(day_records_list, "avl"),
            )
        )

    return summaries


def label_for(field: str) -> str:
    return SENSOR_LABELS.get(field, field)


def records_to_series(records: list[CleanRecord], field: str) -> list[dict[str, Any]]:
    points = []
    for record in records:
        value = record.values.get(field)
        if value is not None:
            points.append({"timestamp": record.timestamp, "value": float(value)})
    return points


def records_to_long_frame(
    records: list[CleanRecord],
    fields: tuple[str, ...] | list[str],
    service_name: str | None = None,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for field in fields:
        for point in records_to_series(records, field):
            row = {
                "timestamp": point["timestamp"],
                "sensor": field,
                "sensor_label": label_for(field),
                "value": point["value"],
            }
            if service_name:
                row["servicio"] = service_name
            rows.append(row)
    return pd.DataFrame(rows)


def day_records(services: list[ServiceSummary], day) -> list[CleanRecord]:
    records: list[CleanRecord] = []
    for service in services_for_day(services, day):
        records.extend(records_on_day(service.records, day))
    return sorted(records, key=lambda record: record.timestamp)


def build_day_timeline_dataframe(
    services: list[ServiceSummary],
    day,
    service_id: int | None = None,
    fields: tuple[str, ...] | list[str] | None = None,
    with_deltas: bool = True,
) -> pd.DataFrame:
    selected_fields = tuple(fields or TIMELINE_TABLE_FIELDS)
    day_services = services_for_day(services, day)
    if service_id is not None:
        day_services = [service for service in day_services if service.service_id == service_id]

    rows: list[dict[str, Any]] = []
    for service in day_services:
        for record in records_on_day(service.records, day):
            row: dict[str, Any] = {
                "timestamp": record.timestamp,
                "Fecha y hora": record.timestamp.strftime("%d/%m/%Y %H:%M:%S"),
                "Hora": record.timestamp.strftime("%H:%M:%S"),
                "Servicio": f"#{service.service_id:03d}",
                "servicio_id": service.service_id,
            }
            for field in selected_fields:
                row[label_for(field)] = record.values.get(field)
            rows.append(row)

    if not rows:
        return pd.DataFrame()

    frame = pd.DataFrame(rows).sort_values("timestamp").reset_index(drop=True)
    frame.insert(0, "#", range(1, len(frame) + 1))

    if with_deltas:
        for field in TIMELINE_DELTA_FIELDS:
            if field not in selected_fields:
                continue
            column = label_for(field)
            if column in frame.columns:
                frame[f"Δ {column}"] = pd.to_numeric(frame[column], errors="coerce").diff().round(2)

    return frame
