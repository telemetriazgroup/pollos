"""Persistencia de cantidad de pollos transportados por servicio."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from data_processor import ServiceSummary, service_storage_key

CARGO_FILE = Path(__file__).parent / "pollos_carga.json"


def load_cargo(path: Path = CARGO_FILE) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    return data if isinstance(data, dict) else {}


def save_cargo(data: dict[str, dict[str, Any]], path: Path = CARGO_FILE) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)


def get_chicken_count(service: ServiceSummary, cargo_data: dict[str, dict[str, Any]]) -> int | None:
    entry = cargo_data.get(service_storage_key(service), {})
    value = entry.get("cantidad_pollos")
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def get_chicken_notes(service: ServiceSummary, cargo_data: dict[str, dict[str, Any]]) -> str:
    entry = cargo_data.get(service_storage_key(service), {})
    return str(entry.get("notas") or "")


def upsert_service_cargo(
    cargo_data: dict[str, dict[str, Any]],
    service: ServiceSummary,
    cantidad_pollos: int | None,
    notas: str = "",
) -> None:
    key = service_storage_key(service)
    if cantidad_pollos is None and not notas.strip():
        cargo_data.pop(key, None)
        return

    cargo_data[key] = {
        "cantidad_pollos": cantidad_pollos,
        "notas": notas.strip(),
        "servicio_id": service.service_id,
        "inicio": service.start.isoformat(),
        "fin": service.end.isoformat(),
    }
