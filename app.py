"""Interfaz de navegación — furgón refrigerado de pollitos."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from cargo_store import (
    get_chicken_count,
    get_chicken_notes,
    load_cargo,
    save_cargo,
    upsert_service_cargo,
)
from data_processor import (
    CARGO_FIELDS,
    MIN_SERVICE_HOURS,
    SERVICE_GAP_HOURS,
    TEMP_AVG_FIELDS,
    TEMP_CHART_FIELDS,
    TEMP_CHART_GROUPS,
    TIMELINE_TABLE_FIELDS,
    ServiceSummary,
    build_day_summaries,
    build_day_timeline_dataframe,
    cargo_average,
    compare_services,
    day_records,
    label_for,
    load_and_process,
    power_on_intervals,
    records_on_day,
    records_to_long_frame,
    records_to_series,
    service_label,
    services_for_day,
)

DATA_FILE = Path(__file__).parent / "pollos_bebes.json"

st.set_page_config(
    page_title="Pollitos · Telemetría",
    page_icon="🐣",
    layout="wide",
    initial_sidebar_state="expanded",
)

CUSTOM_CSS = """
<style>
    .block-container { padding-top: 1.2rem; padding-bottom: 2rem; }
    .hero-box {
        background: linear-gradient(135deg, #1A1F2B 0%, #243047 100%);
        border: 1px solid #334155;
        border-radius: 14px;
        padding: 1.2rem 1.4rem;
        margin-bottom: 1rem;
    }
    .hero-box h1 { margin: 0; font-size: 1.8rem; }
    .hero-box p { margin: 0.4rem 0 0; color: #CBD5E1; }
    .nav-chip {
        display: inline-block;
        background: #334155;
        color: #F8FAFC;
        border-radius: 999px;
        padding: 0.25rem 0.75rem;
        margin-right: 0.35rem;
        font-size: 0.85rem;
    }
    div[data-testid="stMetric"] {
        background: #1A1F2B;
        border: 1px solid #334155;
        border-radius: 12px;
        padding: 0.75rem;
    }
</style>
"""


@st.cache_data(show_spinner="Cargando telemetría, limpiando sensores y detectando servicios...")
def get_data():
    services, stats = load_and_process(DATA_FILE)
    days = build_day_summaries(services)
    return services, stats, days


def inject_css() -> None:
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


def render_hero() -> None:
    st.markdown(
        """
        <div class="hero-box">
            <h1>🐣 Monitoreo de transporte de pollitos</h1>
            <p>
                Navegue por días de operación, analice servicios de traslado, compare temperaturas
                por zona y evalúe ventilación interior mediante CO₂.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def fmt(value, suffix: str = " °C") -> str:
    if value is None:
        return "—"
    return f"{value:.1f}{suffix}"


POWER_ON_FILL = "rgba(230, 126, 34, 0.07)"


def power_shading_caption() -> None:
    st.caption("Sombreado naranja = Power ON · Sin sombra = Power OFF")


def apply_power_shading(
    fig: go.Figure,
    records,
    subplot_rows: int = 1,
) -> go.Figure:
    intervals = power_on_intervals(records)
    if not intervals:
        return fig

    for start, end in intervals:
        if subplot_rows <= 1:
            fig.add_vrect(
                x0=start,
                x1=end,
                fillcolor=POWER_ON_FILL,
                layer="below",
                line_width=0,
            )
        else:
            for row in range(1, subplot_rows + 1):
                fig.add_vrect(
                    x0=start,
                    x1=end,
                    fillcolor=POWER_ON_FILL,
                    layer="below",
                    line_width=0,
                    row=row,
                    col=1,
                )
    return fig


def init_session_state(days) -> None:
    if "selected_day" not in st.session_state and days:
        st.session_state.selected_day = days[-1].day
    if "selected_service_id" not in st.session_state:
        st.session_state.selected_service_id = None


def sidebar_navigation(services, days) -> str:
    st.sidebar.markdown("### Navegación")
    page = st.sidebar.radio(
        "Sección",
        [
            "Inicio",
            "Explorador por día",
            "Evolución por día",
            "Gráficos de temperatura",
            "Carga de pollos",
            "Zonas de carga",
            "CO₂ y ventilación",
            "Comparar servicios",
            "Calidad de datos",
        ],
        label_visibility="collapsed",
    )

    st.sidebar.markdown("---")
    st.sidebar.markdown("#### Acceso rápido")
    day_options = [day_summary.day for day_summary in days]
    quick_day = st.sidebar.selectbox(
        "Día de operación",
        options=day_options,
        index=len(day_options) - 1,
        format_func=lambda value: value.strftime("%d/%m/%Y"),
    )
    st.session_state.selected_day = quick_day

    day_services = services_for_day(services, quick_day)
    if day_services:
        labels = {service.service_id: service_label(service) for service in day_services}
        quick_service = st.sidebar.selectbox(
            "Servicio del día",
            options=[service.service_id for service in day_services],
            format_func=lambda sid: labels[sid],
        )
        st.session_state.selected_service_id = quick_service

    st.sidebar.markdown("---")
    st.sidebar.caption(
        f"Periodo: {services[0].start.strftime('%d/%m/%Y')} → "
        f"{services[-1].end.strftime('%d/%m/%Y')}"
    )
    st.sidebar.caption(
        f"Servicios: {len(services)} · Días con operación: {len(days)} · "
        f"Gap máx. continuidad: {SERVICE_GAP_HOURS} h · Mínimo servicio: {MIN_SERVICE_HOURS} h"
    )
    return page


def render_home(services, stats, days) -> None:
    render_hero()
    cargo_data = load_cargo()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Servicios detectados", f"{len(services):,}")
    c2.metric("Días de operación", f"{len(days):,}")
    c3.metric("Lecturas válidas", f"{stats['kept']:,}")
    c4.metric("Retención de datos", f"{(stats['kept'] / stats['total_raw'] * 100):.1f} %")

    st.markdown(
        """
        <span class="nav-chip">Detección automática de servicios</span>
        <span class="nav-chip">Promedios por zona</span>
        <span class="nav-chip">Comparación entre traslados</span>
        <span class="nav-chip">CO₂ = carga de pollitos</span>
        """,
        unsafe_allow_html=True,
    )

    day_df = pd.DataFrame(
        [
            {
                "Fecha": day_summary.day,
                "Servicios": day_summary.service_count,
                "Lecturas": day_summary.total_readings,
                "Retorno prom.": day_summary.avg_return_air,
                "Suministro prom.": day_summary.avg_supply,
                "Zonas prom.": day_summary.avg_cargo,
                "CO₂ prom.": day_summary.avg_co2,
            }
            for day_summary in days
        ]
    )

    col_a, col_b = st.columns(2)
    with col_a:
        fig_days = px.bar(
            day_df.tail(30),
            x="Fecha",
            y="Servicios",
            title="Días de funcionamiento (últimos 30)",
            color="Servicios",
            color_continuous_scale="Oranges",
        )
        fig_days.update_layout(height=360, showlegend=False)
        st.plotly_chart(fig_days, use_container_width=True)

    with col_b:
        fig_co2 = px.line(
            day_df,
            x="Fecha",
            y="CO₂ prom.",
            markers=True,
            title="CO₂ promedio diario — indicador de ventilación y carga",
        )
        fig_co2.update_layout(height=360)
        st.plotly_chart(fig_co2, use_container_width=True)

    st.subheader("Historial de servicios")
    service_rows = []
    for service in reversed(services):
        service_rows.append(
            {
                "Servicio": service.service_id,
                "Inicio": service.start.strftime("%d/%m/%Y %H:%M"),
                "Fin": service.end.strftime("%d/%m/%Y %H:%M"),
                "Duración (h)": round(service.duration_hours, 1),
                "Cantidad pollos": get_chicken_count(service, cargo_data),
                "CO₂ prom.": service.averages.get("co2_reading"),
            }
        )
    st.dataframe(pd.DataFrame(service_rows), use_container_width=True, hide_index=True)

    st.subheader("Historial de días con operación")
    st.dataframe(
        day_df.sort_values("Fecha", ascending=False),
        use_container_width=True,
        hide_index=True,
    )


def day_navigator(days) -> date:
    day_list = [day_summary.day for day_summary in days]
    current = st.session_state.get("selected_day", day_list[-1])
    if current not in day_list:
        current = day_list[-1]

    idx = day_list.index(current)
    c1, c2, c3 = st.columns([1, 3, 1])
    if c1.button("◀ Día anterior", disabled=idx == 0):
        st.session_state.selected_day = day_list[idx - 1]
        st.rerun()
    c2.markdown(f"### {current.strftime('%A %d de %B, %Y')}")
    if c3.button("Día siguiente ▶", disabled=idx == len(day_list) - 1):
        st.session_state.selected_day = day_list[idx + 1]
        st.rerun()

    picked = st.date_input(
        "Ir a fecha",
        value=current,
        min_value=day_list[0],
        max_value=day_list[-1],
    )
    if picked in day_list:
        st.session_state.selected_day = picked
    return st.session_state.selected_day


def render_service_cards(services, day_services) -> ServiceSummary | None:
    labels = {service.service_id: service_label(service) for service in day_services}
    if not day_services:
        st.info("No hay servicios registrados para este día.")
        return None

    st.markdown(f"**{len(day_services)} servicio(s)** detectado(s) en este día.")

    cols = st.columns(min(len(day_services), 3))
    selected_id = st.session_state.get("selected_service_id")
    if selected_id not in [service.service_id for service in day_services]:
        selected_id = day_services[0].service_id

    for index, service in enumerate(day_services):
        with cols[index % len(cols)]:
            st.markdown(f"**{labels[service.service_id]}**")
            st.caption(f"{service.valid_count} lecturas · {service.duration_hours:.1f} h")
            st.write(f"Retorno: {fmt(service.averages.get('return_air'))}")
            st.write(f"Zonas prom.: {fmt(cargo_average(service))}")
            st.write(f"CO₂: {fmt(service.averages.get('co2_reading'), suffix=' %')}")
            pollos = get_chicken_count(service, load_cargo())
            if pollos is not None:
                st.write(f"Pollos: {pollos:,}")
            if st.button("Ver detalle", key=f"pick_{service.service_id}"):
                st.session_state.selected_service_id = service.service_id
                selected_id = service.service_id

    return next(item for item in day_services if item.service_id == selected_id)


def render_service_detail_panel(service) -> None:
    st.markdown("---")
    st.subheader(service_label(service))

    c1, c2, c3, c4, c5, c6, c7 = st.columns(7)
    c1.metric("Duración", f"{service.duration_hours:.1f} h")
    pollos = get_chicken_count(service, load_cargo())
    c2.metric("Pollos transportados", f"{pollos:,}" if pollos is not None else "—")
    c3.metric("Set point", fmt(service.averages.get("set_point")))
    c4.metric("Suministro", fmt(service.averages.get("temp_supply_1")))
    c5.metric("Retorno", fmt(service.averages.get("return_air")))
    c6.metric("CO₂ prom.", fmt(service.averages.get("co2_reading"), suffix=" %"))
    c7.metric("Ventilación", fmt(service.averages.get("avl"), suffix=" cfm"))

    zone_cols = st.columns(4)
    for index, field in enumerate(CARGO_FIELDS):
        zone_cols[index].metric(label_for(field), fmt(service.averages.get(field)))

    tab_temps, tab_co2, tab_stats = st.tabs(["Curvas de temperatura", "CO₂ y ventilación", "Estadísticas"])

    with tab_temps:
        traces = []
        for field in ["set_point", "temp_supply_1", "return_air", *CARGO_FIELDS]:
            series = records_to_series(service.records, field)
            if not series:
                continue
            frame = pd.DataFrame(series)
            traces.append(
                go.Scatter(
                    x=frame["timestamp"],
                    y=frame["value"],
                    mode="lines",
                    name=label_for(field),
                )
            )
        fig = go.Figure(data=traces)
        fig.update_layout(
            height=520,
            title="Evolución temporal durante el servicio",
            xaxis_title="Hora",
            yaxis_title="Temperatura (°C)",
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
        )
        apply_power_shading(fig, service.records)
        power_shading_caption()
        st.plotly_chart(fig, use_container_width=True)

        zone_rows = []
        for field in CARGO_FIELDS:
            zone_rows.append(
                {
                    "Zona": label_for(field),
                    "Promedio": service.averages.get(field),
                    "Mínimo": service.min_values.get(field),
                    "Máximo": service.max_values.get(field),
                }
            )
        st.dataframe(pd.DataFrame(zone_rows), use_container_width=True, hide_index=True)

    with tab_co2:
        co2_series = records_to_series(service.records, "co2_reading")
        avl_series = records_to_series(service.records, "avl")
        if co2_series:
            co2_df = pd.DataFrame(co2_series)
            fig_co2 = px.area(
                co2_df,
                x="timestamp",
                y="value",
                title="CO₂ interior — a más pollitos, mayor concentración",
            )
            fig_co2.update_layout(height=300, yaxis_title="CO₂ (%)")
            apply_power_shading(fig_co2, service.records)
            st.plotly_chart(fig_co2, use_container_width=True)
        if avl_series:
            avl_df = pd.DataFrame(avl_series)
            fig_avl = px.line(
                avl_df,
                x="timestamp",
                y="value",
                title="Apertura de ventilación",
            )
            fig_avl.update_layout(height=300, yaxis_title="cfm")
            apply_power_shading(fig_avl, service.records)
            st.plotly_chart(fig_avl, use_container_width=True)
        if co2_series or avl_series:
            power_shading_caption()

    with tab_stats:
        rows = []
        for field in TEMP_AVG_FIELDS + ("co2_reading", "relative_humidity", "avl", "capacity_load"):
            rows.append(
                {
                    "Sensor": label_for(field),
                    "Promedio": service.averages.get(field),
                    "Mediana": service.medians.get(field),
                    "Desv. std": service.stddevs.get(field),
                    "Mínimo": service.min_values.get(field),
                    "Máximo": service.max_values.get(field),
                }
            )
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def build_temperature_figure(
    frame: pd.DataFrame,
    title: str,
    color_column: str = "sensor_label",
    facet_column: str | None = None,
    power_records=None,
) -> go.Figure:
    if frame.empty:
        return go.Figure()

    if facet_column:
        fig = px.line(
            frame,
            x="timestamp",
            y="value",
            color=color_column,
            facet_col=facet_column,
            markers=False,
            title=title,
        )
        fig.update_layout(height=420, legend=dict(orientation="h", yanchor="bottom", y=1.08))
        fig.for_each_yaxis(lambda axis: axis.update(title_text="°C"))
        if power_records:
            apply_power_shading(fig, power_records)
        return fig

    fig = px.line(
        frame,
        x="timestamp",
        y="value",
        color=color_column,
        markers=False,
        title=title,
    )
    fig.update_layout(
        height=520,
        xaxis_title="Hora",
        yaxis_title="Temperatura (°C)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        hovermode="x unified",
    )
    if power_records:
        apply_power_shading(fig, power_records)
    return fig


def build_grouped_temperature_figure(
    records,
    fields: tuple[str, ...] | list[str],
    title: str,
) -> go.Figure:
    selected = set(fields)
    active_groups = [
        (group_name, tuple(field for field in group_fields if field in selected))
        for group_name, group_fields in TEMP_CHART_GROUPS.items()
        if any(field in selected for field in group_fields)
    ]
    if not active_groups:
        return go.Figure()

    frame = records_to_long_frame(records, fields)
    if frame.empty:
        return go.Figure()

    fig = make_subplots(
        rows=len(active_groups),
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.08,
        subplot_titles=[group_name for group_name, _ in active_groups],
    )

    palette = px.colors.qualitative.Set2
    for row_index, (_, group_fields) in enumerate(active_groups, start=1):
        group_frame = frame[frame["sensor"].isin(group_fields)]
        for color_index, sensor in enumerate(group_fields):
            sensor_frame = group_frame[group_frame["sensor"] == sensor]
            if sensor_frame.empty:
                continue
            fig.add_trace(
                go.Scatter(
                    x=sensor_frame["timestamp"],
                    y=sensor_frame["value"],
                    mode="lines",
                    name=label_for(sensor),
                    legendgroup=label_for(sensor),
                    showlegend=row_index == 1,
                    line=dict(color=palette[color_index % len(palette)]),
                ),
                row=row_index,
                col=1,
            )
        fig.update_yaxes(title_text="°C", row=row_index, col=1)

    fig.update_layout(height=max(260 * len(active_groups), 520), title=title, hovermode="x unified")
    fig.update_xaxes(title_text="Hora", row=len(active_groups), col=1)
    apply_power_shading(fig, records, subplot_rows=len(active_groups))
    return fig


def render_temperature_charts(services, days) -> None:
    st.subheader("Gráficos de temperatura")
    st.caption(
        "Visualice el comportamiento temporal de las temperaturas por servicio individual "
        "o consolidado por fecha de operación."
    )

    mode = st.radio(
        "Ver por",
        ["Servicio", "Fecha"],
        horizontal=True,
        help="Servicio: un traslado detectado. Fecha: todos los servicios del día en un solo gráfico.",
    )

    labels = {service.service_id: service_label(service) for service in services}
    day_options = [day_summary.day for day_summary in days]

    c1, c2, c3 = st.columns([2, 2, 2])
    with c1:
        selected_fields = st.multiselect(
            "Sensores a graficar",
            options=list(TEMP_CHART_FIELDS),
            default=["set_point", "temp_supply_1", "return_air", *CARGO_FIELDS],
            format_func=label_for,
        )
    with c2:
        chart_style = st.selectbox(
            "Estilo de gráfico",
            ["Todas las curvas juntas", "Paneles por grupo", "Un panel por sensor"],
        )
    with c3:
        show_markers = st.checkbox("Mostrar puntos de lectura", value=False)

    if not selected_fields:
        st.warning("Seleccione al menos un sensor de temperatura.")
        return

    if mode == "Servicio":
        default_service = st.session_state.get("selected_service_id") or services[-1].service_id
        service_ids = [service.service_id for service in services]
        if default_service not in service_ids:
            default_service = service_ids[-1]

        service_id = st.selectbox(
            "Servicio",
            options=service_ids,
            index=service_ids.index(default_service),
            format_func=lambda sid: labels[sid],
        )
        service = next(item for item in services if item.service_id == service_id)
        records = service.records
        title = f"Temperaturas · {labels[service_id]}"
        subtitle = (
            f"{service.valid_count} lecturas · {service.start.strftime('%d/%m/%Y %H:%M')} → "
            f"{service.end.strftime('%H:%M')} · duración {service.duration_hours:.1f} h"
        )
    else:
        default_day = st.session_state.get("selected_day", day_options[-1])
        if default_day not in day_options:
            default_day = day_options[-1]

        selected_day = st.date_input(
            "Fecha",
            value=default_day,
            min_value=day_options[0],
            max_value=day_options[-1],
        )
        if selected_day not in day_options:
            st.info("La fecha seleccionada no tiene operación registrada.")
            return

        day_services = services_for_day(services, selected_day)
        records = day_records(services, selected_day)
        title = f"Temperaturas · {selected_day.strftime('%d/%m/%Y')}"
        subtitle = f"{len(day_services)} servicio(s) · {len(records)} lecturas en el día"

    st.markdown(f"**{subtitle}**")
    power_records = records

    if chart_style == "Paneles por grupo":
        fig = build_grouped_temperature_figure(records, tuple(selected_fields), title)
        power_shading_caption()
        st.plotly_chart(fig, use_container_width=True)
    elif chart_style == "Un panel por sensor":
        frame = records_to_long_frame(records, selected_fields)
        if mode == "Fecha" and len(services_for_day(services, selected_day)) > 1:
            day_service_list = services_for_day(services, selected_day)
            frames = []
            for day_service in day_service_list:
                part = records_to_long_frame(
                    day_service.records,
                    selected_fields,
                    service_name=labels[day_service.service_id],
                )
                frames.append(part)
            frame = pd.concat(frames, ignore_index=True) if frames else frame
            fig = px.line(
                frame,
                x="timestamp",
                y="value",
                color="sensor_label",
                facet_col="sensor_label",
                facet_col_wrap=3,
                title=title,
            )
            fig.update_layout(height=700)
            fig.for_each_yaxis(lambda axis: axis.update(title_text="°C"))
        else:
            fig = px.line(
                frame,
                x="timestamp",
                y="value",
                facet_col="sensor_label",
                facet_col_wrap=3,
                color="sensor_label",
                title=title,
            )
            fig.update_layout(height=700, showlegend=False)
            fig.for_each_yaxis(lambda axis: axis.update(title_text="°C"))
        apply_power_shading(fig, power_records)
        power_shading_caption()
        st.plotly_chart(fig, use_container_width=True)
    else:
        if mode == "Fecha":
            day_service_list = services_for_day(services, selected_day)
            if len(day_service_list) > 1:
                split_by_service = st.checkbox(
                    "Separar curvas por servicio del día",
                    value=False,
                )
            else:
                split_by_service = False

            if split_by_service:
                frames = []
                for day_service in day_service_list:
                    part = records_to_long_frame(
                        day_service.records,
                        selected_fields,
                        service_name=labels[day_service.service_id],
                    )
                    frames.append(part)
                frame = pd.concat(frames, ignore_index=True)
                fig = build_temperature_figure(
                    frame,
                    title,
                    color_column="servicio",
                    facet_column="sensor_label" if len(selected_fields) > 3 else None,
                    power_records=power_records,
                )
            else:
                frame = records_to_long_frame(records, selected_fields)
                fig = build_temperature_figure(frame, title, power_records=power_records)
        else:
            frame = records_to_long_frame(records, selected_fields)
            fig = build_temperature_figure(frame, title, power_records=power_records)

        if show_markers:
            fig.update_traces(mode="lines+markers", marker=dict(size=4))
        power_shading_caption()
        st.plotly_chart(fig, use_container_width=True)

    summary_rows = []
    if mode == "Servicio":
        target = service
        summary_rows.append(
            {
                "Sensor": label_for(field),
                "Promedio": target.averages.get(field),
                "Mínimo": target.min_values.get(field),
                "Máximo": target.max_values.get(field),
            }
            for field in selected_fields
        )
    else:
        for field in selected_fields:
            values = [point["value"] for point in records_to_series(records, field)]
            if not values:
                continue
            summary_rows.append(
                {
                    "Sensor": label_for(field),
                    "Promedio": round(sum(values) / len(values), 2),
                    "Mínimo": round(min(values), 2),
                    "Máximo": round(max(values), 2),
                }
            )

    if summary_rows:
        st.markdown("#### Resumen del periodo seleccionado")
        st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)


def timeline_display_columns(frame: pd.DataFrame, show_deltas: bool) -> list[str]:
    hidden = {"timestamp", "servicio_id"}
    columns = [column for column in frame.columns if column not in hidden]
    if not show_deltas:
        columns = [column for column in columns if not column.startswith("Δ ")]
    return columns


def render_timeline_table_panel(
    services,
    selected_day,
    service_filter: int | None = None,
    key_prefix: str = "timeline",
) -> None:
    day_services = services_for_day(services, selected_day)
    if not day_services:
        st.info("No hay servicios registrados para este día.")
        return

    labels = {service.service_id: service_label(service) for service in day_services}

    c1, c2, c3, c4 = st.columns([2, 2, 2, 2])
    with c1:
        if service_filter is None:
            service_options: list[int | None] = [None, *[service.service_id for service in day_services]]
            picked_service = st.selectbox(
                "Filtrar servicio",
                options=service_options,
                format_func=lambda sid: "Todos los servicios del día" if sid is None else labels[sid],
                key=f"{key_prefix}_service_filter",
            )
        else:
            picked_service = service_filter
    with c2:
        show_deltas = st.checkbox(
            "Mostrar variación respecto a lectura anterior (Δ)",
            value=True,
            key=f"{key_prefix}_deltas",
        )
    with c3:
        table_fields = st.multiselect(
            "Columnas de sensores",
            options=list(TIMELINE_TABLE_FIELDS),
            default=list(TIMELINE_TABLE_FIELDS),
            format_func=label_for,
            key=f"{key_prefix}_fields",
        )
    with c4:
        chart_field = st.selectbox(
            "Sensor para gráfico de línea",
            options=[field for field in table_fields if field in TEMP_CHART_FIELDS] or list(TEMP_CHART_FIELDS),
            format_func=label_for,
            key=f"{key_prefix}_chart_field",
        )

    if not table_fields:
        st.warning("Seleccione al menos una columna de sensor.")
        return

    frame = build_day_timeline_dataframe(
        services,
        selected_day,
        service_id=picked_service,
        fields=table_fields,
        with_deltas=show_deltas,
    )
    if frame.empty:
        st.info("No hay lecturas para los filtros seleccionados.")
        return

    st.markdown(
        f"**{len(frame)} lecturas** en la línea de tiempo · "
        f"{selected_day.strftime('%d/%m/%Y')} · "
        f"{len(day_services) if picked_service is None else 1} servicio(s)"
    )

    chart_column = label_for(chart_field)
    if chart_column in frame.columns:
        if picked_service is not None:
            shade_service = next(item for item in day_services if item.service_id == picked_service)
            shade_records = records_on_day(shade_service.records, selected_day)
        else:
            shade_records = day_records(services, selected_day)

        chart_df = frame.dropna(subset=[chart_column])
        fig = px.line(
            chart_df,
            x="timestamp",
            y=chart_column,
            markers=True,
            title=f"Evolución de {chart_column} durante el día",
        )
        fig.update_layout(height=340, xaxis_title="Hora", yaxis_title=chart_column)
        apply_power_shading(fig, shade_records)
        power_shading_caption()
        st.plotly_chart(fig, use_container_width=True)

    display_cols = timeline_display_columns(frame, show_deltas)
    view = frame[display_cols].copy()

    for column in view.columns:
        if column.startswith("Δ "):
            view[column] = view[column].map(lambda value: "—" if pd.isna(value) else f"{value:+.2f}")

    st.markdown("#### Tabla cronológica de lecturas")
    st.caption(
        "Cada fila es una lectura en el tiempo. Las columnas Δ muestran cuánto cambió el valor "
        "respecto a la lectura anterior."
    )

    st.dataframe(
        view,
        use_container_width=True,
        hide_index=True,
        height=min(560, 80 + len(view) * 35),
        column_config={
            "#": st.column_config.NumberColumn("#", width="small"),
            "Fecha y hora": st.column_config.TextColumn("Fecha y hora", width="medium"),
            "Hora": st.column_config.TextColumn("Hora", width="small"),
            "Servicio": st.column_config.TextColumn("Servicio", width="small"),
        },
    )

    csv = frame[display_cols].to_csv(index=False).encode("utf-8")
    st.download_button(
        "Descargar tabla del día (CSV)",
        data=csv,
        file_name=f"pollitos_{selected_day.strftime('%Y%m%d')}.csv",
        mime="text/csv",
        key=f"{key_prefix}_download",
    )


def render_day_timeline(services, days) -> None:
    st.subheader("Evolución por día")
    st.caption(
        "Seleccione un día de operación y revise lectura por lectura cómo evolucionan "
        "temperaturas, zonas, CO₂ y ventilación en la línea de tiempo."
    )

    selected_day = day_navigator(days)
    render_timeline_table_panel(services, selected_day, key_prefix="day_timeline")


def render_explorer(services, days) -> None:
    st.subheader("Explorador por día y servicio")
    st.caption(
        "Seleccione un día de funcionamiento, revise los servicios detectados y profundice en cada traslado."
    )

    selected_day = day_navigator(days)
    day_services = services_for_day(services, selected_day)

    tab_resumen, tab_timeline = st.tabs(["Resumen del servicio", "Línea de tiempo del día"])

    with tab_resumen:
        service = render_service_cards(services, day_services)
        if service:
            render_service_detail_panel(service)

    with tab_timeline:
        render_timeline_table_panel(services, selected_day, key_prefix="explorer_timeline")


def render_cargo_table(services) -> None:
    st.subheader("Carga de pollos por servicio")
    st.caption(
        "Edite la cantidad de pollitos transportados en cada servicio. "
        "Los datos se guardan en `pollos_carga.json`."
    )

    cargo_data = load_cargo()
    only_missing = st.checkbox("Mostrar solo servicios sin cantidad registrada", value=False)

    rows = []
    for service in services:
        count = get_chicken_count(service, cargo_data)
        if only_missing and count is not None:
            continue
        rows.append(
            {
                "Servicio": service.service_id,
                "Inicio": service.start.strftime("%d/%m/%Y %H:%M"),
                "Fin": service.end.strftime("%d/%m/%Y %H:%M"),
                "Duración (h)": round(service.duration_hours, 1),
                "Cantidad pollos": count,
                "Notas": get_chicken_notes(service, cargo_data),
            }
        )

    if not rows:
        st.info("No hay servicios para mostrar con el filtro actual.")
        return

    edited = st.data_editor(
        pd.DataFrame(rows),
        use_container_width=True,
        hide_index=True,
        num_rows="fixed",
        column_config={
            "Servicio": st.column_config.NumberColumn("Servicio", disabled=True, width="small"),
            "Inicio": st.column_config.TextColumn("Inicio", disabled=True),
            "Fin": st.column_config.TextColumn("Fin", disabled=True),
            "Duración (h)": st.column_config.NumberColumn("Duración (h)", disabled=True, format="%.1f"),
            "Cantidad pollos": st.column_config.NumberColumn(
                "Cantidad pollos",
                min_value=0,
                step=1,
                format="%d",
                help="Número de pollitos transportados en el servicio",
            ),
            "Notas": st.column_config.TextColumn("Notas", width="large"),
        },
        key="cargo_editor",
    )

    save_col, info_col = st.columns([1, 3])
    with save_col:
        save_clicked = st.button("Guardar cantidades", type="primary")
    with info_col:
        registered = sum(1 for service in services if get_chicken_count(service, cargo_data) is not None)
        st.caption(f"{registered} de {len(services)} servicios con cantidad registrada.")

    if save_clicked:
        updated = load_cargo()
        for _, row in edited.iterrows():
            service = next(item for item in services if item.service_id == int(row["Servicio"]))
            cantidad = row["Cantidad pollos"]
            if pd.isna(cantidad):
                cantidad_value = None
            else:
                cantidad_value = int(cantidad)
            upsert_service_cargo(
                updated,
                service,
                cantidad_value,
                str(row.get("Notas") or ""),
            )
        save_cargo(updated)
        st.success("Cantidades guardadas correctamente.")
        st.rerun()


def render_zones(services) -> None:
    st.subheader("Temperaturas por zona de carga (pollitos)")
    st.caption("Las zonas 1 a 4 representan el ambiente donde viajan los pollitos.")

    labels = {service.service_id: service_label(service) for service in services}
    selected_ids = st.multiselect(
        "Servicios a analizar",
        options=[service.service_id for service in services],
        default=[services[-1].service_id, services[-2].service_id] if len(services) > 1 else [services[-1].service_id],
        format_func=lambda sid: labels[sid],
    )
    if not selected_ids:
        st.warning("Seleccione al menos un servicio.")
        return

    rows = []
    for service_id in selected_ids:
        service = next(item for item in services if item.service_id == service_id)
        for field in CARGO_FIELDS:
            rows.append(
                {
                    "Servicio": labels[service_id],
                    "Zona": label_for(field),
                    "Promedio": service.averages.get(field),
                }
            )

    chart_df = pd.DataFrame(rows)
    fig = px.bar(
        chart_df,
        x="Zona",
        y="Promedio",
        color="Servicio",
        barmode="group",
        title="Comparación de temperatura promedio por zona",
    )
    fig.update_layout(height=460, yaxis_title="Temperatura (°C)")
    st.plotly_chart(fig, use_container_width=True)

    heatmap_rows = []
    for service_id in selected_ids:
        service = next(item for item in services if item.service_id == service_id)
        heatmap_rows.append(
            {
                "Servicio": f"#{service_id:03d}",
                **{
                    label_for(field): service.averages.get(field)
                    for field in CARGO_FIELDS
                },
            }
        )
    heatmap_df = pd.DataFrame(heatmap_rows).set_index("Servicio")
    fig_heat = px.imshow(
        heatmap_df,
        text_auto=".1f",
        aspect="auto",
        color_continuous_scale="RdYlBu_r",
        title="Mapa térmico por servicio y zona",
    )
    fig_heat.update_layout(height=320)
    st.plotly_chart(fig_heat, use_container_width=True)


def render_co2(services, days) -> None:
    st.subheader("CO₂ y ventilación interior")
    st.caption(
        "El CO₂ refleja la carga de pollitos y qué tan ventilado estaba el furgón. "
        "Compare servicios para detectar variaciones entre traslados."
    )

    day_df = pd.DataFrame(
        [
            {
                "Fecha": day_summary.day,
                "CO₂ prom.": day_summary.avg_co2,
                "Ventilación prom.": day_summary.avg_avl,
                "Servicios": day_summary.service_count,
            }
            for day_summary in days
        ]
    )

    c1, c2 = st.columns(2)
    with c1:
        fig = px.scatter(
            day_df,
            x="Ventilación prom.",
            y="CO₂ prom.",
            size="Servicios",
            hover_data=["Fecha"],
            title="Relación ventilación vs CO₂ por día",
        )
        fig.update_layout(height=380)
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        fig2 = px.line(day_df.tail(60), x="Fecha", y="CO₂ prom.", markers=True, title="Tendencia de CO₂")
        fig2.update_layout(height=380)
        st.plotly_chart(fig2, use_container_width=True)

    labels = {service.service_id: service_label(service) for service in services}
    service_id = st.selectbox(
        "Detalle temporal de un servicio",
        options=[service.service_id for service in services],
        format_func=lambda sid: labels[sid],
        index=len(services) - 1,
    )
    service = next(item for item in services if item.service_id == service_id)
    co2_series = records_to_series(service.records, "co2_reading")
    if co2_series:
        co2_df = pd.DataFrame(co2_series)
        fig3 = px.line(co2_df, x="timestamp", y="value", title=f"CO₂ durante {labels[service_id]}")
        fig3.update_layout(height=320, yaxis_title="CO₂ (%)")
        apply_power_shading(fig3, service.records)
        power_shading_caption()
        st.plotly_chart(fig3, use_container_width=True)


def render_comparison(services) -> None:
    st.subheader("Comparar servicios")
    st.caption("Detecta cambios significativos entre traslados (temperaturas, zonas y CO₂).")

    labels = {service.service_id: service_label(service) for service in services}
    c1, c2 = st.columns(2)
    base_id = c1.selectbox(
        "Servicio base",
        options=[service.service_id for service in services],
        format_func=lambda sid: labels[sid],
        index=max(len(services) - 2, 0),
    )
    compare_options = [service.service_id for service in services if service.service_id != base_id]
    compare_id = c2.selectbox(
        "Servicio comparado",
        options=compare_options,
        format_func=lambda sid: labels[sid],
        index=max(len(compare_options) - 1, 0),
    )

    base = next(item for item in services if item.service_id == base_id)
    other = next(item for item in services if item.service_id == compare_id)
    rows = compare_services(base, other)
    df = pd.DataFrame(rows)
    df["campo"] = df["campo"].map(label_for)

    significant = df[df["significativo"]]
    st.metric("Cambios significativos", f"{len(significant)} / {len(df)}")

    display_df = df.rename(
        columns={
            "campo": "Sensor",
            "servicio_base": "Base",
            "servicio_comparado": "Comparado",
            "delta": "Delta",
            "significativo": "Significativo",
            "umbral": "Umbral",
        }
    )
    display_df["Significativo"] = display_df["Significativo"].map({True: "Sí", False: "No"})
    st.dataframe(display_df, use_container_width=True, hide_index=True)

    compare_fields = [
        "return_air",
        "temp_supply_1",
        *CARGO_FIELDS,
        "co2_reading",
    ]
    chart_rows = []
    for field in compare_fields:
        base_avg = base.averages.get(field)
        other_avg = other.averages.get(field)
        if base_avg is None or other_avg is None:
            continue
        chart_rows.append({"Sensor": label_for(field), "Servicio": "Base", "Promedio": base_avg})
        chart_rows.append({"Sensor": label_for(field), "Servicio": "Comparado", "Promedio": other_avg})

    if chart_rows:
        fig = px.bar(
            pd.DataFrame(chart_rows),
            x="Sensor",
            y="Promedio",
            color="Servicio",
            barmode="group",
            title="Diferencias de promedios entre servicios",
        )
        fig.update_layout(height=460)
        st.plotly_chart(fig, use_container_width=True)


def render_quality(stats) -> None:
    st.subheader("Calidad y limpieza de datos")
    total = stats["total_raw"]
    kept = stats["kept"]

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Registros originales", f"{total:,}")
    c2.metric("Registros válidos", f"{kept:,}")
    c3.metric("Descartados (lectura 0)", f"{stats['discarded_bad_zero']:,}")
    c4.metric("Servicios < 1 h descartados", f"{stats.get('discarded_short_duration', 0):,}")
    c5.metric("Inválidos núcleo", f"{stats['discarded_invalid_core']:,}")

    fig = go.Figure(
        data=[
            go.Pie(
                labels=["Válidos", "Lectura 0 en retorno/suministro", "Inválidos núcleo"],
                values=[kept, stats["discarded_bad_zero"], stats["discarded_invalid_core"]],
                hole=0.45,
            )
        ]
    )
    fig.update_layout(title="Resultado de limpieza", height=420)
    st.plotly_chart(fig, use_container_width=True)

    st.markdown(
        f"""
        **Reglas de validación (según instrucciones del sistema)**
        - Descartar registros con `return_air = 0` o `temp_supply_1 = 0`.
        - Validar cada sensor dentro de su rango operativo.
        - Un servicio continúa aunque cruce medianoche (ej. 14:00 → 03:00 del día siguiente).
        - Solo se abre un servicio nuevo si hay más de **{SERVICE_GAP_HOURS} horas** sin telemetría.
        - Se descartan traslados con duración total menor a **1 hora**.
        """
    )


def main() -> None:
    inject_css()

    if not DATA_FILE.exists():
        st.error(f"No se encontró el archivo de datos: {DATA_FILE}")
        st.stop()

    services, stats, days = get_data()
    if not services:
        st.warning("No hay servicios válidos después de la limpieza.")
        st.stop()

    init_session_state(days)
    page = sidebar_navigation(services, days)

    if page == "Inicio":
        render_home(services, stats, days)
    elif page == "Explorador por día":
        render_explorer(services, days)
    elif page == "Evolución por día":
        render_day_timeline(services, days)
    elif page == "Gráficos de temperatura":
        render_temperature_charts(services, days)
    elif page == "Carga de pollos":
        render_cargo_table(services)
    elif page == "Zonas de carga":
        render_zones(services)
    elif page == "CO₂ y ventilación":
        render_co2(services, days)
    elif page == "Comparar servicios":
        render_comparison(services)
    else:
        render_quality(stats)


if __name__ == "__main__":
    main()
