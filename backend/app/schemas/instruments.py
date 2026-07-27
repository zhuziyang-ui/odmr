from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

# 全栈扫频默认：2.68–3.10 GHz，δf = 10 kHz → 42001 点
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
    """旧请求只有点数没有步进时，用起止与点数反推步进。"""
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
    """N = round((stop - start) / step) + 1。"""
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
            f"{label}步进过小导致点数 {points} 超过上限 {max_points}，"
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
    """微波源配置。扫频时以起点/终点/步进为输入，自动计算点数。

    点数公式：``N = round((stop - start) / step) + 1``（至少 2 点）。
    仪器实际步进为 ``(stop - start) / (N - 1)``（Keysight STAR/STOP/POIN）。
    """

    # Defaults: sweep 2.68–3.10 GHz with δf = 10 kHz → 42001 points
    mode: Literal["cw", "sweep"] = "sweep"
    frequency_hz: float = 2.87e9
    center_frequency_hz: float = 2.87e9
    sweep_start_hz: float = 2.68e9
    sweep_stop_hz: float = 3.10e9
    # 用户可调步进 (Hz)；点数由 model_validator 根据起止与步进重算
    sweep_step_hz: float = Field(default=10_000.0, gt=0.0)
    # 只读输出语义：由步进计算后写入，客户端也可省略
    sweep_points: int = Field(default=42001, ge=2, le=100001)
    dwell_ms: float = Field(default=5.0, ge=0.1)
    power_dbm: float = -10.0
    output_enabled: bool = False
    iq_enabled: bool = False
    fm_enabled: bool = False
    fm_source: Literal["internal", "external"] = "external"
    fm_deviation_hz: float = 100_000.0
    fm_rate_hz: float = 1_000.0
    lf_output_enabled: bool = False
    lf_output_source: Literal["monitor", "function1", "dc"] = "monitor"
    lf_output_amplitude_v: float = 1.0
    lf_output_offset_v: float = 0.0
    lf_output_load_ohm: Literal[50, 600, 1000000] = 1000000

    @model_validator(mode="before")
    @classmethod
    def _fill_step_from_legacy_points(cls, data: Any) -> Any:
        return fill_step_from_points_dict(
            data,
            start_key="sweep_start_hz",
            stop_key="sweep_stop_hz",
            step_key="sweep_step_hz",
            points_key="sweep_points",
        )

    @model_validator(mode="after")
    def _resolve_sweep_points_from_step(self) -> "MicrowaveConfigRequest":
        self.sweep_points = resolve_points_from_step(
            self.sweep_start_hz,
            self.sweep_stop_hz,
            self.sweep_step_hz,
            min_points=2,
            label="扫频",
        )
        self.center_frequency_hz = 0.5 * (
            float(self.sweep_start_hz) + float(self.sweep_stop_hz)
        )
        return self

    @property
    def effective_sweep_step_hz(self) -> float:
        """Keysight 线性扫在 STAR/STOP/POIN 下的实际步进。"""
        if self.sweep_points <= 1:
            return float(self.sweep_step_hz)
        return (float(self.sweep_stop_hz) - float(self.sweep_start_hz)) / (
            self.sweep_points - 1
        )


class ODMRRequest(BaseModel):
    """软件同步 ODMR：起止 + 步进(默认 10 kHz) → 自动算点数。"""

    scan_mode: Literal["software_sync", "aux_map"] = "software_sync"
    readout_source: Literal["x_v", "y_v", "r_v"] = "r_v"
    start_hz: float = Field(default=DEFAULT_FREQ_START_HZ)
    stop_hz: float = Field(default=DEFAULT_FREQ_STOP_HZ)
    step_hz: float = Field(default=DEFAULT_FREQ_STEP_HZ, gt=0.0)
    points: int = Field(default=42001, ge=3, le=MAX_LINEAR_SWEEP_POINTS)
    dwell_ms: float = Field(default=8.0, ge=0.1)
    averages: int = Field(default=4, ge=1, le=1000)
    aux_voltage_min_v: float = 0.0
    aux_voltage_max_v: float = 10.0
    aux_frequency_min_hz: float = DEFAULT_FREQ_START_HZ
    aux_frequency_max_hz: float = DEFAULT_FREQ_STOP_HZ

    @model_validator(mode="before")
    @classmethod
    def _fill_step_from_legacy_points(cls, data: Any) -> Any:
        return fill_step_from_points_dict(
            data,
            start_key="start_hz",
            stop_key="stop_hz",
            step_key="step_hz",
            points_key="points",
        )

    @model_validator(mode="after")
    def _resolve_points_from_step(self) -> "ODMRRequest":
        self.points = resolve_points_from_step(
            self.start_hz,
            self.stop_hz,
            self.step_hz,
            min_points=3,
            label="ODMR 扫频",
        )
        return self


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
    """电流扫描搜索：起止 + 步进(默认 10 kHz) → 自动算点数。"""

    channel_index: int = Field(default=0, ge=0)
    start_hz: float = Field(default=DEFAULT_FREQ_START_HZ)
    stop_hz: float = Field(default=DEFAULT_FREQ_STOP_HZ)
    search_step_hz: float = Field(default=DEFAULT_FREQ_STEP_HZ, gt=0.0)
    search_points: int = Field(default=42001, ge=11, le=MAX_LINEAR_SWEEP_POINTS)
    settle_ms: float = Field(default=30.0, ge=1.0)
    slope_fit_points: int = Field(default=9, ge=3, le=41)
    phase_target: Literal["x_v", "y_v", "auto"] = "auto"

    @model_validator(mode="before")
    @classmethod
    def _fill_step_from_legacy_points(cls, data: Any) -> Any:
        return fill_step_from_points_dict(
            data,
            start_key="start_hz",
            stop_key="stop_hz",
            step_key="search_step_hz",
            points_key="search_points",
        )

    @model_validator(mode="after")
    def _resolve_search_points_from_step(self) -> "CurrentScanRequest":
        self.search_points = resolve_points_from_step(
            self.start_hz,
            self.stop_hz,
            self.search_step_hz,
            min_points=11,
            label="电流搜索扫频",
        )
        return self


class CurrentTrackingRequest(BaseModel):
    """双峰跟踪初始全扫：起止 + 步进(默认 10 kHz) → 自动算 search_points。"""

    channel_index: int = Field(default=0, ge=0)
    independent_dc_channel_index: int = Field(default=-1, ge=-1)
    tracking_target: Literal["complex_projection"] = "complex_projection"
    start_hz: float = Field(default=DEFAULT_FREQ_START_HZ)
    stop_hz: float = Field(default=DEFAULT_FREQ_STOP_HZ)
    search_step_hz: float = Field(default=DEFAULT_FREQ_STEP_HZ, gt=0.0)
    search_points: int = Field(default=42001, ge=11, le=MAX_LINEAR_SWEEP_POINTS)
    search_settle_ms: float = Field(default=10.0, ge=0.1, le=5000.0)
    probe_offset_hz: float = Field(default=250_000.0, gt=0.0)
    tracking_settle_ms: float = Field(default=3.0, ge=0.1, le=5000.0)
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
    minimum_complex_fit_r2: float = Field(default=0.7, ge=0.0, le=1.0)
    slope_epsilon: float = Field(default=1e-30, gt=0.0)
    orthogonal_limit_fraction: float = Field(default=0.5, gt=0.0)
    maximum_error_fraction: float = Field(default=0.8, gt=0.0, le=1.0)
    minimum_depth_fraction: float = Field(default=0.15, ge=0.0, le=1.0)
    slope_ratio_min: float = Field(default=0.3, gt=0.0)
    slope_ratio_max: float = Field(default=3.0, gt=0.0)
    maximum_slope_angle_change_rad: float = Field(default=1.0, gt=0.0)
    verify_interval_visits: int = Field(default=20, ge=1, le=100000)
    slope_verification_max_age_s: float = Field(default=10.0, gt=0.0)
    bad_samples_to_suspect: int = Field(default=1, ge=1, le=1000)
    bad_samples_to_lose: int = Field(default=3, ge=1, le=1000)
    good_samples_to_lock: int = Field(default=3, ge=1, le=1000)
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
    minimum_peak_prominence_fraction: float = Field(default=0.05, ge=0.0, le=1.0)
    peak_pair_ambiguity_score_ratio: float = Field(default=0.9, gt=0.0, le=1.0)
    relock_cooldown_s: float = Field(default=0.1, ge=0.0, le=60.0)
    max_relock_attempts: int = Field(default=5, ge=0, le=1000)
    max_tracking_duration_s: float = Field(default=0.0, ge=0.0, le=604800.0)
    minimum_calibration_slope_a_per_hz: float | None = None
    minimum_calibration_intercept_a: float | None = None
    calibration_delta_f_min_hz: float | None = None
    calibration_delta_f_max_hz: float | None = None
    current_polarity_mode: Literal["magnitude", "signed_external"] = "magnitude"

    @model_validator(mode="before")
    @classmethod
    def _fill_step_from_legacy_points(cls, data: Any) -> Any:
        return fill_step_from_points_dict(
            data,
            start_key="start_hz",
            stop_key="stop_hz",
            step_key="search_step_hz",
            points_key="search_points",
        )

    @model_validator(mode="after")
    def _resolve_search_points_from_step(self) -> "CurrentTrackingRequest":
        self.search_points = resolve_points_from_step(
            self.start_hz,
            self.stop_hz,
            self.search_step_hz,
            min_points=11,
            label="电流跟踪搜索扫频",
        )
        return self


class ApiResponse(BaseModel):
    success: bool
    message: str
    data: dict[str, Any] = Field(default_factory=dict)
