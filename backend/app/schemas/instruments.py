from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

# Shared linear-sweep defaults (start/stop/step → points). Used by state estimation
# and optional clients that compute N = round((stop - start) / step) + 1.
DEFAULT_FREQ_START_HZ = 2.68e9
DEFAULT_FREQ_STOP_HZ = 3.10e9
DEFAULT_FREQ_STEP_HZ = 10_000.0
MAX_LINEAR_SWEEP_POINTS = 100_001


def fill_step_from_points_dict(
    data: Any,
    *,
    start_key: str,
    stop_key: str,
    step_key: str,
    points_key: str,
    default_start: float = DEFAULT_FREQ_START_HZ,
    default_stop: float = DEFAULT_FREQ_STOP_HZ,
) -> Any:
    """Legacy payloads with only points: back-fill step from start/stop/points."""
    if not isinstance(data, dict):
        return data
    if data.get(step_key) is not None:
        return data
    start = float(data.get(start_key, default_start))
    stop = float(data.get(stop_key, default_stop))
    points = data.get(points_key)
    if points is not None and int(points) > 1 and stop > start:
        data = dict(data)
        data[step_key] = (stop - start) / (int(points) - 1)
    return data


def resolve_points_from_step(
    start_hz: float,
    stop_hz: float,
    step_hz: float,
    *,
    min_points: int = 2,
    max_points: int = MAX_LINEAR_SWEEP_POINTS,
    label: str = "扫频",
) -> int:
    """N = round((stop - start) / step) + 1."""
    span = float(stop_hz) - float(start_hz)
    if span <= 0:
        raise ValueError(f"{label}终点频率必须大于起点频率。")
    step = float(step_hz)
    if step <= 0:
        raise ValueError(f"{label}步进必须大于 0。")
    points = int(round(span / step)) + 1
    if points < min_points:
        points = min_points
    if points > max_points:
        raise ValueError(
            f"{label}步进过小导致点数 {points} 超过上限 {max_points}。"
            f"请增大步进或缩小跨度。"
        )
    return points


class LabOneServerConfig(BaseModel):
    server_host: str = "localhost"
    server_port: int = 8004
    hf2: bool = False


class LockinConnectRequest(LabOneServerConfig):
    serial: str = "dev1234"
    interface: str | None = None


class LockinChannelConfig(BaseModel):
    channel_index: int = Field(default=0, ge=0)
    demod_index: int = Field(default=0, ge=0)
    osc_index: int = Field(default=0, ge=0)
    input_index: int = Field(default=0, ge=0)
    enabled: bool = True
    input_signal: int = 0
    demod_freq_hz: float = 13_700.0
    time_constant_ms: float = 10.0
    low_pass_order: int = Field(default=4, ge=1, le=8)
    low_pass_bandwidth_hz: float = 6.922905799116954
    input_range_mv: float = 100.0
    input_impedance_50ohm: bool = False
    input_voltage_scaling: float = 1.0
    input_ac_coupling: bool = False
    input_differential: bool = False
    input_float: bool = False
    current_range_ma: float = 10.0
    current_scaling: float = 1.0
    current_float: bool = False
    phase_deg: float = 0.0
    harmonic: int = Field(default=1, ge=1, le=64)
    sinc_enabled: bool = False
    sample_rate_hz: float = 1_000.0
    trigger_mode: int = 0
    reference_source: Literal["internal", "external"] = "internal"
    external_reference_index: int = Field(default=0, ge=0)
    aux_output_channel: int = Field(default=0, ge=0)
    aux_output_offset_v: float = 0.0
    display_source: Literal["x_v", "y_v", "r_v"] = "r_v"


class MicrowaveConnectRequest(BaseModel):
    address: str = "TCPIP0::192.168.1.100::inst0::INSTR"
    timeout_ms: int = 3000


class MicrowaveConfigRequest(BaseModel):
    mode: Literal["cw", "sweep"] = "sweep"
    # How instrument LIST/STEP sweep runs when mode=sweep:
    # - trigger: arm single-shot (INIT:CONT OFF); use Trigger API/button for one pass
    # - free: free-run continuous sweep (INIT:CONT ON) after apply
    sweep_run_mode: Literal["trigger", "free"] = "trigger"
    frequency_hz: float = 2.87e9
    center_frequency_hz: float = 2.87e9
    sweep_start_hz: float = 2.82e9
    sweep_stop_hz: float = 2.92e9
    # Primary user input for sweep density; points are derived from start/stop/step.
    sweep_step_hz: float = Field(default=10_000.0, gt=0.0)
    # Derived/output field used by Keysight SCPI and ODMR sync. Recomputed from step on apply.
    sweep_points: int = Field(default=10001, ge=2, le=65535)
    dwell_ms: float = Field(default=5.0, ge=0.1)
    power_dbm: float = 18.0
    output_enabled: bool = False
    iq_enabled: bool = False
    fm_enabled: bool = False
    fm_source: Literal["internal", "external"] = "external"
    fm_deviation_hz: float = 3_000_000.0
    fm_rate_hz: float = 10_000.0
    lf_output_enabled: bool = False
    lf_output_source: Literal["monitor", "function1", "dc"] = "monitor"
    lf_output_amplitude_v: float = 1.0
    lf_output_offset_v: float = 0.0
    lf_output_load_ohm: Literal[50, 600, 1000000] = 1000000


class ODMRRequest(BaseModel):
    scan_mode: Literal["software_sync", "aux_map"] = "software_sync"
    readout_source: Literal["x_v", "y_v", "r_v"] = "r_v"
    start_hz: float = Field(default=2.83e9)
    stop_hz: float = Field(default=2.91e9)
    points: int = Field(default=161, ge=3, le=2001)
    dwell_ms: float = Field(default=8.0, ge=0.1)
    averages: int = Field(default=4, ge=1, le=1000)
    aux_voltage_min_v: float = 0.0
    aux_voltage_max_v: float = 10.0
    aux_frequency_min_hz: float = 2.82e9
    aux_frequency_max_hz: float = 2.92e9


class SensitivityRequest(BaseModel):
    channel_index: int = Field(default=0, ge=0)
    search_center_hz: float = 2.87e9
    search_span_hz: float = Field(default=20e6, gt=0)
    search_points: int = Field(default=121, ge=11, le=4001)
    settle_ms: float = Field(default=30.0, ge=1.0)
    slope_fit_points: int = Field(default=9, ge=3, le=41)
    asd_duration_s: float = Field(default=5.0, ge=1.0, le=120.0)
    asd_min_frequency_hz: float = Field(default=1.0, ge=0.0)
    phase_target: Literal["x_v", "y_v", "auto"] = "auto"
    cos_alpha: float = Field(default=1.0, gt=0.0, le=1.0)
    gamma_hz_per_t: float = Field(default=28e9, gt=0.0)


class CurrentScanRequest(BaseModel):
    channel_index: int = Field(default=0, ge=0)
    start_hz: float = Field(default=2.83e9)
    stop_hz: float = Field(default=2.91e9)
    # Align with linear-sweep helper / frontend MAX (10 kHz over ~80 MHz → 8001 pts).
    search_points: int = Field(default=121, ge=11, le=MAX_LINEAR_SWEEP_POINTS)
    settle_ms: float = Field(default=30.0, ge=1.0)
    slope_fit_points: int = Field(default=9, ge=3, le=41)
    phase_target: Literal["x_v", "y_v", "auto"] = "auto"


class CurrentTrackingRequest(BaseModel):
    channel_index: int = Field(default=0, ge=0)
    independent_dc_channel_index: int = Field(default=-1, ge=-1)
    tracking_target: Literal["complex_projection"] = "complex_projection"
    start_hz: float = Field(default=2.83e9)
    stop_hz: float = Field(default=2.91e9)
    # Full-scan search density: same cap as state-estimation / frontend linear sweep.
    search_points: int = Field(default=121, ge=11, le=MAX_LINEAR_SWEEP_POINTS)
    # Defaults = 稳健 preset: looser noise thresholds, same lobe–valley–lobe peak definition.
    search_settle_ms: float = Field(default=15.0, ge=0.1, le=5000.0)
    probe_offset_hz: float = Field(default=250_000.0, gt=0.0)
    tracking_settle_ms: float = Field(default=5.0, ge=0.1, le=5000.0)
    sample_averages: int = Field(default=1, ge=1, le=100)
    timing_report_interval_cycles: int = Field(default=10, ge=1, le=10000)
    record_enabled: bool = True
    record_interval_s: float = Field(default=1.0, ge=0.1, le=3600.0)
    record_label: str = Field(default="", max_length=80)
    kp: float = Field(default=0.45, ge=0.0, le=100.0)
    ki_per_s: float = Field(default=0.03, ge=0.0, le=1000.0)
    kd_s: float = Field(default=0.0, ge=0.0, le=1000.0)
    derivative_filter_tau_s: float = Field(default=0.1, ge=0.0, le=60.0)
    antiwindup_gain_per_s: float = Field(default=1.0, ge=0.0, le=1000.0)
    max_step_hz: float = Field(default=500_000.0, gt=0.0)
    maximum_slew_hz_per_s: float = Field(default=10_000_000.0, gt=0.0)
    integral_limit_hz: float = Field(default=1_000_000.0, ge=0.0)
    lock_error_limit_hz: float = Field(default=1_500_000.0, gt=0.0)
    minimum_complex_fit_r2: float = Field(default=0.5, ge=0.0, le=1.0)
    slope_epsilon: float = Field(default=1e-30, gt=0.0)
    orthogonal_limit_fraction: float = Field(default=0.8, gt=0.0)
    maximum_error_fraction: float = Field(default=0.95, gt=0.0, le=1.0)
    minimum_depth_fraction: float = Field(default=0.15, ge=0.0, le=1.0)
    slope_ratio_min: float = Field(default=0.2, gt=0.0)
    slope_ratio_max: float = Field(default=5.0, gt=0.0)
    maximum_slope_angle_change_rad: float = Field(default=1.3, gt=0.0)
    verify_interval_visits: int = Field(default=10, ge=1, le=100000)
    slope_verification_max_age_s: float = Field(default=25.0, gt=0.0)
    bad_samples_to_suspect: int = Field(default=3, ge=1, le=1000)
    bad_samples_to_lose: int = Field(default=6, ge=1, le=1000)
    good_samples_to_lock: int = Field(default=2, ge=1, le=1000)
    relock_gain_ramp_samples: int = Field(default=5, ge=1, le=1000)
    saturation_loss_threshold: int = Field(default=5, ge=1, le=1000)
    calibration_points_each_side: int = Field(default=2, ge=1, le=10)
    enable_velocity_prediction: bool = True
    velocity_filter_tau_s: float = Field(default=0.5, ge=0.0, le=60.0)
    maximum_velocity_hz_per_s: float = Field(default=20_000_000.0, gt=0.0)
    maximum_acceleration_hz_per_s2: float = Field(default=100_000_000.0, gt=0.0)
    maximum_extrapolation_age_s: float = Field(default=1.0, gt=0.0, le=60.0)
    maximum_delta_f_sigma_hz: float = Field(default=2_000_000.0, gt=0.0)
    delta_f_min_hz: float = Field(default=0.0, ge=0.0)
    delta_f_max_hz: float = Field(default=1_000_000_000.0, gt=0.0)
    local_scan_points: int = Field(default=17, ge=7, le=501)
    local_scan_initial_width_fraction: float = Field(default=1.0, gt=0.0)
    local_scan_expansion_factor: float = Field(default=2.0, gt=1.0)
    local_scan_max_expansions: int = Field(default=3, ge=1, le=20)
    reacquire_identity_guard_fraction: float = Field(default=0.25, ge=0.0, le=2.0)
    minimum_resolvable_separation_factor: float = Field(default=0.75, ge=0.0, le=10.0)
    minimum_peak_prominence_fraction: float = Field(default=0.03, ge=0.0, le=1.0)
    peak_pair_ambiguity_score_ratio: float = Field(default=0.75, gt=0.0, le=1.0)
    relock_cooldown_s: float = Field(default=0.1, ge=0.0, le=60.0)
    max_relock_attempts: int = Field(default=10, ge=0, le=1000)
    max_tracking_duration_s: float = Field(default=0.0, ge=0.0, le=604800.0)
    minimum_calibration_slope_a_per_hz: float | None = None
    minimum_calibration_intercept_a: float | None = None
    calibration_delta_f_min_hz: float | None = None
    calibration_delta_f_max_hz: float | None = None
    current_polarity_mode: Literal["magnitude", "signed_external"] = "magnitude"


class ApiResponse(BaseModel):
    success: bool
    message: str
    data: dict[str, Any] = Field(default_factory=dict)
