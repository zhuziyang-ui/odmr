"""HTTP API for GB/T 20840.2 accuracy tables and ODMR frequency-current mapping."""

from __future__ import annotations

import csv
import io
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.app.services.accuracy_mapping import (
    PRIMARY_CLASSES,
    PlatformParams,
    abs_current_error_table,
    delta_f_khz_to_delta_I_a,
    export_standard_csvs,
    freq_tolerance_table,
    max_pitch_angle_deg,
    pitch_angle_budget_table,
    ratio_error_table,
    recommended_exc_currents_for_standard_points,
)

router = APIRouter(prefix="/api/accuracy", tags=["accuracy"])


class PlatformParamsBody(BaseModel):
    kH_gs_per_a: float = Field(6.8, gt=0)
    alpha_bus_per_exc: float = Field(150.0, gt=0)
    gamma_hz_per_t: float = Field(28e9, gt=0)
    In_a: float = Field(3000.0, gt=0)
    max_exc_a: float = Field(15.0, gt=0)


class MapRequest(BaseModel):
    df_khz: float = Field(..., description="Frequency error magnitude in kHz")
    quantity: Literal["delta_f", "branch"] = "delta_f"
    mode: Literal["theoretical", "empirical"] = "theoretical"
    slope_a_per_hz: float | None = None
    empirical_current_is_excitation: bool = True
    params: PlatformParamsBody = Field(default_factory=PlatformParamsBody)
    compare_standard: bool = True


class TablesRequest(BaseModel):
    params: PlatformParamsBody = Field(default_factory=PlatformParamsBody)
    classes: list[str] = Field(default_factory=lambda: list(PRIMARY_CLASSES))
    include_reference_classes: bool = True


def _to_params(body: PlatformParamsBody) -> PlatformParams:
    return PlatformParams(
        kH_gs_per_a=body.kH_gs_per_a,
        alpha_bus_per_exc=body.alpha_bus_per_exc,
        gamma_hz_per_t=body.gamma_hz_per_t,
        In_a=body.In_a,
        max_exc_a=body.max_exc_a,
    )


def _rows_to_dicts(rows: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        if hasattr(row, "as_dict"):
            out.append(row.as_dict())
        elif isinstance(row, dict):
            out.append(row)
        else:
            out.append(dict(row))
    return out


@router.get("/defaults")
async def get_defaults() -> dict[str, Any]:
    params = PlatformParams()
    return {
        "params": params.as_public_dict(),
        "primary_classes": list(PRIMARY_CLASSES),
        "quantity_options": [
            {"value": "delta_f", "label": "劈裂 Δf = f+ − f−"},
            {"value": "branch", "label": "单支 f± 锁定误差"},
        ],
        "mode_options": [
            {"value": "theoretical", "label": "理论链 (Helmholtz + Zeeman)"},
            {"value": "empirical", "label": "经验标定 I = a·Δf + b"},
        ],
    }


@router.post("/map")
async def map_frequency_to_current(body: MapRequest) -> dict[str, Any]:
    params = _to_params(body.params)
    try:
        mapped = delta_f_khz_to_delta_I_a(
            body.df_khz,
            quantity=body.quantity,
            params=params,
            mode=body.mode,
            empirical_slope_a_per_hz=body.slope_a_per_hz,
            empirical_current_is_excitation=body.empirical_current_is_excitation,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    payload: dict[str, Any] = {
        "result": mapped.as_dict(),
        "platform": params.as_public_dict(),
    }

    if body.compare_standard:
        comparisons = []
        for row in abs_current_error_table(params, classes=PRIMARY_CLASSES):
            comparisons.append(
                {
                    "accuracy_class": row.accuracy_class,
                    "I_percent_In": row.I_percent_In,
                    "I_bus_a": row.I_bus_a,
                    "abs_error_limit_a": row.abs_error_pm_a,
                    "delta_I_bus_a": mapped.delta_I_bus_a,
                    "within_limit": mapped.delta_I_bus_a <= row.abs_error_pm_a + 1e-15,
                    "margin_a": row.abs_error_pm_a - mapped.delta_I_bus_a,
                    "reachable_on_platform": row.reachable_on_0_15A_platform,
                }
            )
        payload["standard_comparison"] = comparisons

    return payload


@router.post("/tables")
async def get_tables(body: TablesRequest) -> dict[str, Any]:
    params = _to_params(body.params)
    classes = list(body.classes) if body.classes else list(PRIMARY_CLASSES)
    if body.include_reference_classes:
        # Keep primary first, then common reference classes for the full ratio table.
        ordered = []
        for cls in ["0.1", "0.2", "0.2S", "0.5", "0.5S", "1"]:
            if cls not in ordered:
                ordered.append(cls)
        ratio_classes = ordered
    else:
        ratio_classes = classes

    try:
        return {
            "platform": params.as_public_dict(),
            "ratio_error_limits": _rows_to_dicts(ratio_error_table(ratio_classes)),
            "abs_current_error": _rows_to_dicts(
                abs_current_error_table(params, classes=classes)
            ),
            "freq_tolerance": _rows_to_dicts(
                freq_tolerance_table(params, classes=classes)
            ),
            "pitch_angle_budget": pitch_angle_budget_table(classes),
            "platform_exc_points": recommended_exc_currents_for_standard_points(
                params, classes=classes
            ),
            "pitch_angle_0_2_percent_deg": max_pitch_angle_deg(0.002),
            "pitch_angle_0_5_percent_deg": max_pitch_angle_deg(0.005),
        }
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/pitch-angle")
async def pitch_angle(
    ratio_error_percent: float = Query(0.2, gt=0, description="Allowed ratio error in percent"),
) -> dict[str, float]:
    frac = ratio_error_percent / 100.0
    return {
        "ratio_error_percent": ratio_error_percent,
        "max_pitch_angle_deg": max_pitch_angle_deg(frac),
    }


@router.post("/export-csv/{table_name}")
async def export_csv(table_name: str, body: TablesRequest) -> StreamingResponse:
    """Download one table as CSV (UTF-8 BOM for Excel)."""
    tables = await get_tables(body)
    key_map = {
        "ratio_error_limits": "ratio_error_limits",
        "abs_current_error": "abs_current_error",
        "freq_tolerance": "freq_tolerance",
        "pitch_angle_budget": "pitch_angle_budget",
        "platform_exc_points": "platform_exc_points",
        "platform_params": None,
    }
    if table_name not in key_map:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown table '{table_name}'. Choose from: {list(key_map)}",
        )

    if table_name == "platform_params":
        rows = [tables["platform"]]
    else:
        rows = tables[key_map[table_name]]

    if not rows:
        raise HTTPException(status_code=404, detail="Empty table")

    buffer = io.StringIO()
    # Excel-friendly BOM
    buffer.write("\ufeff")
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)

    filename = f"{table_name}.csv"
    data = buffer.getvalue().encode("utf-8")
    return StreamingResponse(
        io.BytesIO(data),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/export-all")
async def export_all_to_disk(body: TablesRequest) -> dict[str, Any]:
    """Write standard CSVs under data/standards (same as CLI)."""
    from pathlib import Path

    params = _to_params(body.params)
    out_dir = Path(__file__).resolve().parents[3] / "data" / "standards"
    paths = export_standard_csvs(out_dir, params)
    return {
        "out_dir": str(out_dir),
        "files": {name: str(path) for name, path in paths.items()},
    }
