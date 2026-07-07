"""Generación de reportes PDF para servicios y comparaciones."""

from __future__ import annotations

from datetime import datetime
from io import BytesIO
from typing import Any

from fpdf import FPDF

from cargo_store import get_chicken_count, get_chicken_notes
from data_processor import (
    CARGO_FIELDS,
    ServiceSummary,
    cargo_average,
    compare_services,
    label_for,
)
from service_export import EXPORT_SENSOR_FIELDS

TEMPERATURE_FIELDS = (
    "set_point",
    "temp_supply_1",
    "return_air",
    *CARGO_FIELDS,
    "ambient_air",
)

GAS_FIELDS = (
    "co2_reading",
    "o2_reading",
    "relative_humidity",
    "avl",
    "capacity_load",
)


def _pdf_safe(text: Any) -> str:
    if text is None:
        return "-"
    value = str(text)
    return (
        value.replace("°", " deg")
        .replace("₂", "2")
        .replace("·", "-")
        .replace("→", "->")
    )


def _fmt_num(value: float | None, suffix: str = "") -> str:
    if value is None:
        return "-"
    return f"{float(value):.2f}{suffix}"


class PollosPDF(FPDF):
    def footer(self) -> None:
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.cell(0, 10, f"Pagina {self.page_no()}/{{nb}}", align="C")


def _content_width(pdf: PollosPDF) -> float:
    return pdf.w - pdf.l_margin - pdf.r_margin


def _column_widths(pdf: PollosPDF, proportions: list[float]) -> list[float]:
    total = sum(proportions)
    content = _content_width(pdf)
    return [content * proportion / total for proportion in proportions]


def _begin_table_row(pdf: PollosPDF, widths: list[float]) -> None:
    pdf.set_x(pdf.l_margin)


def _section_title(pdf: PollosPDF, title: str) -> None:
    pdf.set_font("Helvetica", "B", 12)
    pdf.ln(4)
    pdf.set_x(pdf.l_margin)
    pdf.cell(0, 8, _pdf_safe(title), ln=True)
    pdf.set_font("Helvetica", "", 10)


def _table_header(pdf: PollosPDF, columns: list[str], widths: list[float]) -> None:
    _begin_table_row(pdf, widths)
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_fill_color(240, 240, 240)
    for column, width in zip(columns, widths):
        pdf.cell(width, 7, _pdf_safe(column), border=1, fill=True)
    pdf.ln()


def _table_row(pdf: PollosPDF, columns: list[str], widths: list[float]) -> None:
    _begin_table_row(pdf, widths)
    pdf.set_font("Helvetica", "", 9)
    for column, width in zip(columns, widths):
        pdf.cell(width, 7, _pdf_safe(column), border=1)
    pdf.ln()


def _wrap_lines(pdf: PollosPDF, lines: list[str]) -> None:
    pdf.set_font("Helvetica", "", 10)
    for line in lines:
        pdf.multi_cell(0, 6, _pdf_safe(line))
        pdf.ln(1)


def build_comparison_analysis(
    base: ServiceSummary,
    other: ServiceSummary,
    rows: list[dict[str, Any]],
) -> list[str]:
    significant = [row for row in rows if row["significativo"]]
    analysis = [
        f"Servicio base #{base.service_id:03d} vs servicio comparado #{other.service_id:03d}.",
        f"Metricas evaluadas: {len(rows)}. Diferencias significativas: {len(significant)}.",
    ]

    if not significant:
        analysis.append(
            "Conclusion: no se detectaron cambios relevantes entre ambos traslados dentro de los umbrales definidos."
        )
        return analysis

    analysis.append("Conclusion: se detectaron las siguientes diferencias significativas:")
    for row in significant:
        sensor = label_for(row["campo"])
        direction = "aumento" if row["delta"] > 0 else "disminucion"
        analysis.append(
            f"- {sensor}: {direction} de {abs(row['delta'])} "
            f"(base {row['servicio_base']} -> comparado {row['servicio_comparado']}; umbral {row['umbral']})."
        )

    temp_changes = [row for row in significant if row["campo"] in TEMPERATURE_FIELDS]
    gas_changes = [row for row in significant if row["campo"] in GAS_FIELDS]
    if temp_changes:
        analysis.append(
            f"Impacto termico: {len(temp_changes)} sensor(es) de temperatura con variacion significativa."
        )
    if gas_changes:
        analysis.append(
            f"Impacto en gases/ventilacion: {len(gas_changes)} indicador(es) con variacion significativa."
        )

    return analysis


def generate_service_pdf(
    service: ServiceSummary,
    cargo_data: dict[str, dict[str, Any]],
    service_title: str,
) -> bytes:
    pdf = PollosPDF()
    pdf.alias_nb_pages()
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "Reporte de servicio - Transporte de pollitos", ln=True)
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 7, _pdf_safe(service_title), ln=True)
    pdf.cell(0, 7, f"Generado: {datetime.now().strftime('%d/%m/%Y %H:%M')}", ln=True)

    pollos = get_chicken_count(service, cargo_data)
    notas = get_chicken_notes(service, cargo_data)

    _section_title(pdf, "Informacion general")
    info_rows = [
        ("Servicio", f"#{service.service_id:03d}"),
        ("Inicio", service.start.strftime("%d/%m/%Y %H:%M:%S")),
        ("Fin", service.end.strftime("%d/%m/%Y %H:%M:%S")),
        ("Duracion (h)", _fmt_num(service.duration_hours)),
        ("Lecturas validas", str(service.valid_count)),
        ("Cantidad pollos", str(pollos) if pollos is not None else "No registrada"),
        ("Zona prom. pollitos", _fmt_num(cargo_average(service), " degC")),
        ("Notas carga", notas or "-"),
    ]
    widths = _column_widths(pdf, [0.28, 0.72])
    _table_header(pdf, ["Campo", "Valor"], widths)
    for label, value in info_rows:
        _table_row(pdf, [label, value], widths)

    _section_title(pdf, "Promedios de temperatura")
    stats_widths = _column_widths(pdf, [0.36, 0.16, 0.16, 0.16, 0.16])
    stats_headers = ["Sensor", "Promedio", "Mediana", "Minimo", "Maximo"]
    _table_header(pdf, stats_headers, stats_widths)
    for field in TEMPERATURE_FIELDS:
        _table_row(
            pdf,
            [
                label_for(field),
                _fmt_num(service.averages.get(field)),
                _fmt_num(service.medians.get(field)),
                _fmt_num(service.min_values.get(field)),
                _fmt_num(service.max_values.get(field)),
            ],
            stats_widths,
        )

    _section_title(pdf, "Promedios de gases y ambiente")
    _table_header(pdf, stats_headers, stats_widths)
    for field in GAS_FIELDS:
        _table_row(
            pdf,
            [
                label_for(field),
                _fmt_num(service.averages.get(field)),
                _fmt_num(service.medians.get(field)),
                _fmt_num(service.min_values.get(field)),
                _fmt_num(service.max_values.get(field)),
            ],
            stats_widths,
        )

    if service.power_on_ratio is not None:
        _section_title(pdf, "Operacion")
        _wrap_lines(
            pdf,
            [
                f"Power ON en {service.power_on_ratio * 100:.1f}% de las lecturas del servicio.",
                "En graficos del dashboard, el sombreado tenue indica periodos con power encendido.",
            ],
        )

    buffer = BytesIO()
    pdf.output(buffer)
    return buffer.getvalue()


def generate_comparison_pdf(
    base: ServiceSummary,
    other: ServiceSummary,
    cargo_data: dict[str, dict[str, Any]],
    base_title: str,
    other_title: str,
) -> bytes:
    rows = compare_services(base, other)
    analysis = build_comparison_analysis(base, other, rows)

    pdf = PollosPDF()
    pdf.alias_nb_pages()
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "Reporte comparativo entre servicios", ln=True)
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 7, f"Generado: {datetime.now().strftime('%d/%m/%Y %H:%M')}", ln=True)

    _section_title(pdf, "Servicios comparados")
    _wrap_lines(pdf, [f"Base: {base_title}", f"Comparado: {other_title}"])

    summary_widths = _column_widths(pdf, [0.34, 0.33, 0.33])
    _table_header(pdf, ["Indicador", "Servicio base", "Servicio comparado"], summary_widths)
    summary_rows = [
        ("Cantidad pollos", get_chicken_count(base, cargo_data), get_chicken_count(other, cargo_data)),
        ("Duracion (h)", round(base.duration_hours, 2), round(other.duration_hours, 2)),
        ("Zona prom. pollitos", cargo_average(base), cargo_average(other)),
        ("CO2 prom.", base.averages.get("co2_reading"), other.averages.get("co2_reading")),
        ("Retorno prom.", base.averages.get("return_air"), other.averages.get("return_air")),
        ("Suministro prom.", base.averages.get("temp_supply_1"), other.averages.get("temp_supply_1")),
    ]
    for label, base_value, other_value in summary_rows:
        base_text = str(base_value) if base_value is not None else "-"
        other_text = str(other_value) if other_value is not None else "-"
        if isinstance(base_value, float):
            base_text = _fmt_num(base_value)
        if isinstance(other_value, float):
            other_text = _fmt_num(other_value)
        _table_row(pdf, [label, base_text, other_text], summary_widths)

    _section_title(pdf, "Analisis de diferencias")
    _wrap_lines(pdf, analysis)

    _section_title(pdf, "Detalle de diferencias por sensor")
    detail_widths = _column_widths(pdf, [0.24, 0.16, 0.16, 0.14, 0.14, 0.16])
    _table_header(
        pdf,
        ["Sensor", "Base", "Comparado", "Delta", "Umbral", "Significativo"],
        detail_widths,
    )
    for row in rows:
        _table_row(
            pdf,
            [
                label_for(row["campo"]),
                _fmt_num(row["servicio_base"]),
                _fmt_num(row["servicio_comparado"]),
                _fmt_num(row["delta"]),
                _fmt_num(row["umbral"]),
                "Si" if row["significativo"] else "No",
            ],
            detail_widths,
        )

    buffer = BytesIO()
    pdf.output(buffer)
    return buffer.getvalue()


def service_pdf_filename(service_id: int) -> str:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"reporte_servicio_{service_id:03d}_{stamp}.pdf"


def comparison_pdf_filename(base_id: int, compare_id: int) -> str:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"reporte_comparacion_{base_id:03d}_vs_{compare_id:03d}_{stamp}.pdf"
