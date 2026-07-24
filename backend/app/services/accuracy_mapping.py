"""GB/T 20840.2 metering accuracy tables and ODMR current-frequency mapping.

Maps bus-current accuracy limits (ratio error) through Helmholtz scaling and
NV Zeeman splitting to microwave frequency lock tolerances.

Defaults match the lab platform:
- 1 A excitation -> 6.8 Gs at Helmholtz center
- 1 A excitation ~ 150 A equivalent bus current
- gamma/2pi = 28 GHz/T (room-temperature NV electron Zeeman)
- In = 3000 A (500 kV class metering reference)
"""

from __future__ import annotations

import csv
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Literal, Sequence


Quantity = Literal["delta_f", "branch"]
MappingMode = Literal["theoretical", "empirical"]


# GB/T 20840.2 / IEC 61869-2 measuring CT ratio-error limits (% of reading).
# Values are ± percent. Phase displacement is listed for completeness (minutes).
RATIO_ERROR_LIMITS: dict[str, list[tuple[float, float, float | None]]] = {
    # class: list of (I_percent_of_In, ratio_error_pm_percent, phase_error_pm_min)
    "0.1": [
        (5.0, 0.4, 15.0),
        (20.0, 0.2, 8.0),
        (100.0, 0.1, 5.0),
        (120.0, 0.1, 5.0),
    ],
    "0.2": [
        (5.0, 0.75, 30.0),
        (20.0, 0.35, 15.0),
        (100.0, 0.2, 10.0),
        (120.0, 0.2, 10.0),
    ],
    "0.2S": [
        (1.0, 0.75, 30.0),
        (5.0, 0.35, 15.0),
        (20.0, 0.2, 10.0),
        (100.0, 0.2, 10.0),
        (120.0, 0.2, 10.0),
    ],
    "0.5": [
        (5.0, 1.5, 90.0),
        (20.0, 0.75, 45.0),
        (100.0, 0.5, 30.0),
        (120.0, 0.5, 30.0),
    ],
    "0.5S": [
        (1.0, 1.5, 90.0),
        (5.0, 0.75, 45.0),
        (20.0, 0.5, 30.0),
        (100.0, 0.5, 30.0),
        (120.0, 0.5, 30.0),
    ],
    "1": [
        (5.0, 3.0, 180.0),
        (20.0, 1.5, 90.0),
        (100.0, 1.0, 60.0),
        (120.0, 1.0, 60.0),
    ],
}

PRIMARY_CLASSES: tuple[str, ...] = ("0.2", "0.2S")


@dataclass(frozen=True)
class PlatformParams:
    """Lab / standard mapping parameters."""

    kH_gs_per_a: float = 6.8
    """Helmholtz center field per ampere of excitation current (Gs/A)."""

    alpha_bus_per_exc: float = 150.0
    """Equivalent bus current per ampere of excitation (A_bus / A_exc)."""

    gamma_hz_per_t: float = 28.0e9
    """NV electron gyromagnetic ratio / 2pi (Hz/T)."""

    In_a: float = 3000.0
    """Rated primary bus current In (A)."""

    max_exc_a: float = 15.0
    """Maximum available excitation current on the small DC source (A)."""

    def gamma_mhz_per_g(self) -> float:
        # 1 T = 10_000 G; Hz/T -> MHz/G
        return self.gamma_hz_per_t / 1e6 / 1e4

    def dB_dI_bus_gs_per_a(self) -> float:
        return self.kH_gs_per_a / self.alpha_bus_per_exc

    def d_delta_f_dI_bus_khz_per_a(self) -> float:
        """Splitting sensitivity d(Δf)/dI_bus in kHz/A (theoretical, B∥=B)."""
        # Δf = 2 * gamma * B; B in G; gamma in MHz/G -> MHz/A * 1000 = kHz/A
        return 2.0 * self.gamma_mhz_per_g() * self.dB_dI_bus_gs_per_a() * 1e3

    def d_branch_f_dI_bus_khz_per_a(self) -> float:
        return 0.5 * self.d_delta_f_dI_bus_khz_per_a()

    def d_delta_f_dI_exc_mhz_per_a(self) -> float:
        return 2.0 * self.gamma_mhz_per_g() * self.kH_gs_per_a

    def d_branch_f_dI_exc_mhz_per_a(self) -> float:
        return self.gamma_mhz_per_g() * self.kH_gs_per_a

    def bus_from_exc(self, i_exc_a: float) -> float:
        return float(i_exc_a) * self.alpha_bus_per_exc

    def exc_from_bus(self, i_bus_a: float) -> float:
        return float(i_bus_a) / self.alpha_bus_per_exc

    def max_bus_a(self) -> float:
        return self.bus_from_exc(self.max_exc_a)

    def max_bus_percent_In(self) -> float:
        return 100.0 * self.max_bus_a() / self.In_a

    def as_public_dict(self) -> dict[str, float]:
        return {
            "kH_gs_per_a": self.kH_gs_per_a,
            "alpha_bus_per_exc": self.alpha_bus_per_exc,
            "gamma_hz_per_t": self.gamma_hz_per_t,
            "gamma_mhz_per_g": self.gamma_mhz_per_g(),
            "In_a": self.In_a,
            "max_exc_a": self.max_exc_a,
            "dB_dI_bus_gs_per_a": self.dB_dI_bus_gs_per_a(),
            "d_delta_f_dI_bus_khz_per_a": self.d_delta_f_dI_bus_khz_per_a(),
            "d_branch_f_dI_bus_khz_per_a": self.d_branch_f_dI_bus_khz_per_a(),
            "d_delta_f_dI_exc_mhz_per_a": self.d_delta_f_dI_exc_mhz_per_a(),
            "d_branch_f_dI_exc_mhz_per_a": self.d_branch_f_dI_exc_mhz_per_a(),
            "max_bus_a": self.max_bus_a(),
            "max_bus_percent_In": self.max_bus_percent_In(),
        }


@dataclass(frozen=True)
class RatioErrorRow:
    accuracy_class: str
    I_percent_In: float
    ratio_error_pm_percent: float
    phase_error_pm_min: float | None
    standard: str = "GB/T 20840.2"
    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AbsoluteErrorRow:
    accuracy_class: str
    I_percent_In: float
    I_bus_a: float
    ratio_error_pm_percent: float
    abs_error_pm_a: float
    I_exc_equivalent_a: float
    reachable_on_0_15A_platform: bool
    In_a: float
    standard: str = "GB/T 20840.2"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FreqToleranceRow:
    accuracy_class: str
    I_percent_In: float
    I_bus_a: float
    abs_error_pm_a: float
    delta_f_tol_khz: float
    branch_f_tol_khz: float
    worst_case_two_branch_sum_khz: float
    independent_rss_two_branch_khz: float
    I_exc_equivalent_a: float
    reachable_on_0_15A_platform: bool
    In_a: float
    d_delta_f_dI_bus_khz_per_a: float
    mapping_mode: str = "theoretical"
    standard: str = "GB/T 20840.2"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FreqToCurrentResult:
    delta_f_khz: float
    quantity: Quantity
    mode: MappingMode
    delta_I_bus_a: float
    delta_I_exc_a: float
    sensitivity_khz_per_a_bus: float
    slope_a_per_hz: float | None = None
    notes: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def ratio_error_table(
    classes: Sequence[str] | None = None,
) -> list[RatioErrorRow]:
    """Return segmented ratio-error limits for selected accuracy classes."""
    selected = tuple(classes) if classes is not None else tuple(RATIO_ERROR_LIMITS)
    rows: list[RatioErrorRow] = []
    for cls in selected:
        if cls not in RATIO_ERROR_LIMITS:
            raise KeyError(f"Unknown accuracy class: {cls}")
        for i_pct, ratio, phase in RATIO_ERROR_LIMITS[cls]:
            note = "primary for 500 kV metering analysis" if cls in PRIMARY_CLASSES else "reference"
            rows.append(
                RatioErrorRow(
                    accuracy_class=cls,
                    I_percent_In=i_pct,
                    ratio_error_pm_percent=ratio,
                    phase_error_pm_min=phase,
                    note=note,
                )
            )
    return rows


def abs_current_error_table(
    params: PlatformParams | None = None,
    classes: Sequence[str] | None = None,
) -> list[AbsoluteErrorRow]:
    """Absolute bus-current error |δI| = (ε/100) * (p/100) * In at each test point."""
    params = params or PlatformParams()
    selected = tuple(classes) if classes is not None else PRIMARY_CLASSES
    rows: list[AbsoluteErrorRow] = []
    for cls in selected:
        for i_pct, ratio, _phase in RATIO_ERROR_LIMITS[cls]:
            i_bus = params.In_a * (i_pct / 100.0)
            abs_err = i_bus * (ratio / 100.0)
            i_exc = params.exc_from_bus(i_bus)
            rows.append(
                AbsoluteErrorRow(
                    accuracy_class=cls,
                    I_percent_In=i_pct,
                    I_bus_a=i_bus,
                    ratio_error_pm_percent=ratio,
                    abs_error_pm_a=abs_err,
                    I_exc_equivalent_a=i_exc,
                    reachable_on_0_15A_platform=i_exc <= params.max_exc_a + 1e-12,
                    In_a=params.In_a,
                )
            )
    return rows


def freq_tolerance_table(
    params: PlatformParams | None = None,
    classes: Sequence[str] | None = None,
    *,
    mode: MappingMode = "theoretical",
    empirical_slope_a_per_hz: float | None = None,
) -> list[FreqToleranceRow]:
    """Map absolute current errors to Δf / single-branch frequency tolerances."""
    params = params or PlatformParams()
    abs_rows = abs_current_error_table(params, classes=classes)
    if mode == "theoretical":
        s_delta = params.d_delta_f_dI_bus_khz_per_a()
    else:
        if empirical_slope_a_per_hz is None or empirical_slope_a_per_hz == 0:
            raise ValueError("empirical mode requires non-zero slope_a_per_hz (A/Hz)")
        # Default empirical slope is I_exc = a * Δf_Hz + b.
        # δI_bus = α |a| δ(Δf_Hz)  =>  δ(Δf)_kHz / δI_bus = 1 / (α |a| 1e3)
        s_delta = 1.0 / (
            abs(empirical_slope_a_per_hz) * params.alpha_bus_per_exc * 1e3
        )

    rows: list[FreqToleranceRow] = []
    for row in abs_rows:
        delta_tol = row.abs_error_pm_a * s_delta
        branch_tol = 0.5 * delta_tol
        rows.append(
            FreqToleranceRow(
                accuracy_class=row.accuracy_class,
                I_percent_In=row.I_percent_In,
                I_bus_a=row.I_bus_a,
                abs_error_pm_a=row.abs_error_pm_a,
                delta_f_tol_khz=delta_tol,
                branch_f_tol_khz=branch_tol,
                worst_case_two_branch_sum_khz=2.0 * branch_tol,
                independent_rss_two_branch_khz=math.sqrt(2.0) * branch_tol,
                I_exc_equivalent_a=row.I_exc_equivalent_a,
                reachable_on_0_15A_platform=row.reachable_on_0_15A_platform,
                In_a=row.In_a,
                d_delta_f_dI_bus_khz_per_a=s_delta,
                mapping_mode=mode,
            )
        )
    return rows


def delta_f_khz_to_delta_I_a(
    delta_f_khz: float,
    *,
    quantity: Quantity = "delta_f",
    params: PlatformParams | None = None,
    mode: MappingMode = "theoretical",
    empirical_slope_a_per_hz: float | None = None,
    empirical_current_is_excitation: bool = True,
) -> FreqToCurrentResult:
    """Convert a frequency error (kHz) into bus / excitation current error (A).

    Empirical mode uses the dual-peak calibration ``I = a*Δf_Hz + b``.
    By default ``I`` is the lab excitation current (DC source amperes); bus
    current is then ``α * I_exc``.  Set ``empirical_current_is_excitation=False``
    if the stored slope already maps to bus amperes.
    """
    params = params or PlatformParams()
    df = abs(float(delta_f_khz))

    if mode == "empirical":
        if empirical_slope_a_per_hz is None:
            raise ValueError("empirical mode requires slope_a_per_hz")
        slope = abs(float(empirical_slope_a_per_hz))
        # δI_cal from δ(Δf); single-branch error maps as 2× if the other branch is perfect
        df_hz = df * 1e3
        if quantity == "delta_f":
            di_cal = slope * df_hz
        else:
            di_cal = slope * (2.0 * df_hz)

        if empirical_current_is_excitation:
            di_exc = di_cal
            di_bus = di_cal * params.alpha_bus_per_exc
            # sensitivity of bus current vs splitting in kHz
            sens = (
                1.0 / (slope * params.alpha_bus_per_exc * 1e3)
                if slope and quantity == "delta_f"
                else 0.5 / (slope * params.alpha_bus_per_exc * 1e3)
                if slope
                else float("inf")
            )
            notes = "empirical I=a*Δf+b with I=excitation; I_bus=α*I_exc"
        else:
            di_bus = di_cal
            di_exc = di_cal / params.alpha_bus_per_exc
            sens = (
                1.0 / (slope * 1e3)
                if slope and quantity == "delta_f"
                else 0.5 / (slope * 1e3)
                if slope
                else float("inf")
            )
            notes = "empirical I=a*Δf+b with I already in bus amperes"

        return FreqToCurrentResult(
            delta_f_khz=df,
            quantity=quantity,
            mode=mode,
            delta_I_bus_a=di_bus,
            delta_I_exc_a=di_exc,
            sensitivity_khz_per_a_bus=sens,
            slope_a_per_hz=slope,
            notes=notes,
        )

    if quantity == "delta_f":
        sens = params.d_delta_f_dI_bus_khz_per_a()
    elif quantity == "branch":
        sens = params.d_branch_f_dI_bus_khz_per_a()
    else:
        raise ValueError(f"unknown quantity: {quantity}")

    di_bus = df / sens
    di_exc = di_bus / params.alpha_bus_per_exc
    return FreqToCurrentResult(
        delta_f_khz=df,
        quantity=quantity,
        mode=mode,
        delta_I_bus_a=di_bus,
        delta_I_exc_a=di_exc,
        sensitivity_khz_per_a_bus=sens,
        notes="theoretical Helmholtz + Zeeman chain, B_parallel=B",
    )


def delta_I_a_to_delta_f_khz(
    delta_I_bus_a: float,
    *,
    quantity: Quantity = "delta_f",
    params: PlatformParams | None = None,
    mode: MappingMode = "theoretical",
    empirical_slope_a_per_hz: float | None = None,
    empirical_current_is_excitation: bool = True,
) -> float:
    """Inverse of delta_f_khz_to_delta_I_a (input is bus-current error)."""
    params = params or PlatformParams()
    di_bus = abs(float(delta_I_bus_a))
    if mode == "empirical":
        if empirical_slope_a_per_hz is None or empirical_slope_a_per_hz == 0:
            raise ValueError("empirical mode requires non-zero slope_a_per_hz")
        slope = abs(empirical_slope_a_per_hz)
        di_cal = (
            di_bus / params.alpha_bus_per_exc
            if empirical_current_is_excitation
            else di_bus
        )
        if quantity == "delta_f":
            return (di_cal / slope) / 1e3
        return (di_cal / slope) / 2e3

    if quantity == "delta_f":
        return di_bus * params.d_delta_f_dI_bus_khz_per_a()
    if quantity == "branch":
        return di_bus * params.d_branch_f_dI_bus_khz_per_a()
    raise ValueError(f"unknown quantity: {quantity}")


def max_pitch_angle_deg(ratio_error_fraction: float) -> float:
    """Geometric |θ| upper bound from B_parallel = B0 * cos(θ) projection error.

    Relative error ε = 1 - cos(θ).  For small θ, ε ≈ θ²/2.
    """
    eps = abs(float(ratio_error_fraction))
    if eps <= 0:
        return 0.0
    if eps >= 1:
        return 90.0
    return math.degrees(math.acos(1.0 - eps))


def pitch_angle_budget_table(
    classes: Sequence[str] | None = None,
) -> list[dict[str, Any]]:
    """Pitch-angle geometric budget for each accuracy class / current percent point."""
    rows: list[dict[str, Any]] = []
    selected = tuple(classes) if classes is not None else PRIMARY_CLASSES
    for cls in selected:
        for i_pct, ratio, _phase in RATIO_ERROR_LIMITS[cls]:
            frac = ratio / 100.0
            th = max_pitch_angle_deg(frac)
            # recommended fine step: resolve ~1/10 of the geometric window, floor 0.1°
            fine_step = max(0.1, round(th / 20.0, 2))
            rows.append(
                {
                    "accuracy_class": cls,
                    "I_percent_In": i_pct,
                    "ratio_error_pm_percent": ratio,
                    "max_pitch_angle_deg_1_minus_cos": th,
                    "recommended_fine_step_deg": 0.1 if th <= 6.0 else fine_step,
                    "note": "projection-only bound; use 0.1° near pass/fail boundary",
                }
            )
    return rows


def recommended_exc_currents_for_standard_points(
    params: PlatformParams | None = None,
    classes: Sequence[str] = PRIMARY_CLASSES,
) -> list[dict[str, Any]]:
    """Excitation currents that map standard bus %In points onto the Helmholtz bench."""
    params = params or PlatformParams()
    seen: set[tuple[float, float]] = set()
    out: list[dict[str, Any]] = []
    for cls in classes:
        for i_pct, ratio, _ in RATIO_ERROR_LIMITS[cls]:
            key = (i_pct, ratio)
            if key in seen:
                continue
            seen.add(key)
            i_bus = params.In_a * i_pct / 100.0
            i_exc = params.exc_from_bus(i_bus)
            out.append(
                {
                    "I_percent_In": i_pct,
                    "I_bus_a": i_bus,
                    "I_exc_a": i_exc,
                    "ratio_error_ref_0.2S_or_0.2_percent": ratio,
                    "reachable": i_exc <= params.max_exc_a + 1e-12,
                }
            )
    out.sort(key=lambda r: r["I_percent_In"])
    return out


def write_csv(path: Path | str, rows: Iterable[dict[str, Any]]) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    materialised = [dict(r) for r in rows]
    if not materialised:
        path.write_text("", encoding="utf-8-sig")
        return path
    fieldnames: list[str] = []
    for row in materialised:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(materialised)
    return path


def export_standard_csvs(
    out_dir: Path | str,
    params: PlatformParams | None = None,
    *,
    include_all_classes: bool = True,
) -> dict[str, Path]:
    """Write the three primary CSVs (plus optional full-class / angle budget tables)."""
    params = params or PlatformParams()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    primary = PRIMARY_CLASSES if not include_all_classes else tuple(RATIO_ERROR_LIMITS)
    in_tag = f"In{int(params.In_a)}A"

    paths: dict[str, Path] = {}
    paths["ratio_error_limits"] = write_csv(
        out_dir / "gb20840_2_ratio_error_limits.csv",
        (r.as_dict() for r in ratio_error_table(primary)),
    )
    paths["abs_current_error"] = write_csv(
        out_dir / f"gb20840_2_abs_current_error_{in_tag}.csv",
        (r.as_dict() for r in abs_current_error_table(params, classes=PRIMARY_CLASSES)),
    )
    paths["freq_tolerance"] = write_csv(
        out_dir / f"gb20840_2_freq_tolerance_{in_tag}.csv",
        (r.as_dict() for r in freq_tolerance_table(params, classes=PRIMARY_CLASSES)),
    )
    paths["pitch_angle_budget"] = write_csv(
        out_dir / "pitch_angle_geometric_budget.csv",
        pitch_angle_budget_table(PRIMARY_CLASSES),
    )
    paths["platform_exc_points"] = write_csv(
        out_dir / f"platform_exc_for_standard_points_{in_tag}.csv",
        recommended_exc_currents_for_standard_points(params),
    )
    paths["platform_params"] = write_csv(
        out_dir / "platform_params.csv",
        [params.as_public_dict()],
    )
    return paths
