import { useEffect, useRef, useState } from "react";
import {
  Badge,
  Button,
  Grid,
  Group,
  NumberInput,
  Select,
  SimpleGrid,
  Stack,
  Switch,
  Text,
  TextInput,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";

import { api, formatGHz, wsUrl } from "../lib/api";
import { MetricCard } from "./MetricCard";
import { PlotCard } from "./PlotCard";
import { SectionCard } from "./SectionCard";

/** 内存最多保留最近 1 h；显示窗口再二次过滤。 */
const PLOT_BUFFER_KEEP_S = 3600;
const PLOT_WINDOW_STORAGE_KEY = "nv-live-plot-window-s-v1";
const PLOT_WINDOW_OPTIONS = [
  { value: "2", label: "2 s", seconds: 2 },
  { value: "10", label: "10 s", seconds: 10 },
  { value: "60", label: "60 s", seconds: 60 },
  { value: "300", label: "5 min", seconds: 300 },
  { value: "3600", label: "1 h", seconds: 3600 },
];
const MAX_BUFFER_POINTS = 50000;

function plotNumberOr(value, fallback = 0) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : fallback;
}

function loadPlotWindowSeconds() {
  if (typeof window === "undefined") {
    return 60;
  }
  try {
    const raw = window.localStorage.getItem(PLOT_WINDOW_STORAGE_KEY);
    const match = PLOT_WINDOW_OPTIONS.find((item) => item.value === String(raw));
    if (match) {
      return match.seconds;
    }
  } catch {
    // ignore
  }
  return 60;
}

function persistPlotWindowSeconds(seconds) {
  if (typeof window === "undefined") {
    return;
  }
  try {
    window.localStorage.setItem(PLOT_WINDOW_STORAGE_KEY, String(seconds));
  } catch {
    // ignore
  }
}

function appendTrackingPoint(previous, point) {
  const tEnd = plotNumberOr(point?.elapsed_s, NaN);
  const next = [...(Array.isArray(previous) ? previous : []), point];
  if (!Number.isFinite(tEnd)) {
    return next.length > MAX_BUFFER_POINTS ? next.slice(-MAX_BUFFER_POINTS) : next;
  }
  const kept = next.filter(
    (item) => tEnd - plotNumberOr(item?.elapsed_s, tEnd) <= PLOT_BUFFER_KEEP_S
  );
  return kept.length > MAX_BUFFER_POINTS ? kept.slice(-MAX_BUFFER_POINTS) : kept;
}

function slicePointsByWindow(points, windowSeconds) {
  const list = Array.isArray(points) ? points : [];
  if (!list.length) {
    return { points: [], xRange: undefined };
  }
  const tEnd = plotNumberOr(list[list.length - 1]?.elapsed_s, 0);
  const windowS = Math.max(1, plotNumberOr(windowSeconds, 60));
  const tStart = tEnd - windowS;
  const visible = list.filter((item) => plotNumberOr(item?.elapsed_s, -Infinity) >= tStart);
  return {
    points: visible,
    xRange: [Math.max(0, tStart), Math.max(tEnd, tStart + 1e-3)],
  };
}

/** Shared base; peak center is always FM 1f lobe–valley–lobe valley minimum. */
const TRACKING_FORM_BASE = {
  tracking_target: "complex_projection",
  independent_dc_channel_index: -1,
  probe_offset_hz: 250_000,
  sample_averages: 1,
  timing_report_interval_cycles: 10,
  record_enabled: true,
  record_interval_s: 1,
  record_label: "",
  kp: 0.45,
  ki_per_s: 0.03,
  kd_s: 0,
  derivative_filter_tau_s: 0.1,
  antiwindup_gain_per_s: 1,
  max_step_hz: 500_000,
  maximum_slew_hz_per_s: 10_000_000,
  integral_limit_hz: 1_000_000,
  lock_error_limit_hz: 1_500_000,
  minimum_depth_fraction: 0.15,
  relock_gain_ramp_samples: 5,
  saturation_loss_threshold: 5,
  calibration_points_each_side: 2,
  enable_velocity_prediction: true,
  velocity_filter_tau_s: 0.5,
  maximum_velocity_hz_per_s: 20_000_000,
  maximum_acceleration_hz_per_s2: 100_000_000,
  maximum_extrapolation_age_s: 1,
  maximum_delta_f_sigma_hz: 2_000_000,
  delta_f_min_hz: 0,
  delta_f_max_hz: 1_000_000_000,
  local_scan_points: 17,
  local_scan_initial_width_fraction: 1,
  local_scan_expansion_factor: 2,
  local_scan_max_expansions: 3,
  reacquire_identity_guard_fraction: 0.25,
  minimum_resolvable_separation_factor: 0.75,
  relock_cooldown_s: 0.1,
  max_tracking_duration_s: 0,
};

/** 稳健：默认更易进锁；不改变双瓣夹谷峰心定义。 */
const PRESET_ROBUST = {
  tracking_settle_ms: 5,
  minimum_complex_fit_r2: 0.5,
  orthogonal_limit_fraction: 0.8,
  maximum_error_fraction: 0.95,
  slope_ratio_min: 0.2,
  slope_ratio_max: 5,
  maximum_slope_angle_change_rad: 1.3,
  verify_interval_visits: 10,
  slope_verification_max_age_s: 25,
  bad_samples_to_suspect: 3,
  bad_samples_to_lose: 6,
  good_samples_to_lock: 2,
  minimum_peak_prominence_fraction: 0.03,
  peak_pair_ambiguity_score_ratio: 0.75,
  max_relock_attempts: 10,
};

/** 标准：历史默认量级。 */
const PRESET_STANDARD = {
  tracking_settle_ms: 3,
  minimum_complex_fit_r2: 0.7,
  orthogonal_limit_fraction: 0.5,
  maximum_error_fraction: 0.8,
  slope_ratio_min: 0.3,
  slope_ratio_max: 3,
  maximum_slope_angle_change_rad: 1,
  verify_interval_visits: 20,
  slope_verification_max_age_s: 10,
  bad_samples_to_suspect: 1,
  bad_samples_to_lose: 3,
  good_samples_to_lock: 3,
  minimum_peak_prominence_fraction: 0.05,
  peak_pair_ambiguity_score_ratio: 0.9,
  max_relock_attempts: 5,
};

/** 严格：干净信号、低误跟。 */
const PRESET_STRICT = {
  tracking_settle_ms: 3,
  minimum_complex_fit_r2: 0.85,
  orthogonal_limit_fraction: 0.4,
  maximum_error_fraction: 0.7,
  slope_ratio_min: 0.5,
  slope_ratio_max: 2,
  maximum_slope_angle_change_rad: 0.8,
  verify_interval_visits: 15,
  slope_verification_max_age_s: 8,
  bad_samples_to_suspect: 1,
  bad_samples_to_lose: 2,
  good_samples_to_lock: 4,
  minimum_peak_prominence_fraction: 0.08,
  peak_pair_ambiguity_score_ratio: 0.95,
  max_relock_attempts: 5,
};

const TRACKING_PRESETS = {
  robust: { label: "稳健（推荐）", searchSettleMs: 15, values: PRESET_ROBUST },
  standard: { label: "标准", searchSettleMs: 10, values: PRESET_STANDARD },
  strict: { label: "严格", searchSettleMs: 10, values: PRESET_STRICT },
};

/** 界面模式：只控制显示哪些控件，不改变数值。 */
const UI_MODE_STORAGE_KEY = "nv-current-tracking-ui-mode-v1";
const UI_MODES = {
  simple: { label: "简易（推荐）", level: 0 },
  tuning: { label: "调机", level: 1 },
  expert: { label: "专家", level: 2 },
};

function loadUiMode() {
  if (typeof window === "undefined") {
    return "simple";
  }
  try {
    const stored = window.localStorage.getItem(UI_MODE_STORAGE_KEY);
    if (stored && UI_MODES[stored]) {
      return stored;
    }
  } catch {
    // ignore storage errors
  }
  return "simple";
}

function persistUiMode(mode) {
  if (typeof window === "undefined") {
    return;
  }
  try {
    window.localStorage.setItem(UI_MODE_STORAGE_KEY, mode);
  } catch {
    // ignore storage errors
  }
}

function uiModeLevel(mode) {
  return UI_MODES[mode]?.level ?? 0;
}

const DEFAULT_TRACKING_FORM = {
  ...TRACKING_FORM_BASE,
  ...PRESET_ROBUST,
};

const STAGE_LABELS = {
  setup: "启动检查",
  full_scan: "全频扫峰",
  calibrate: "复数标定",
  track: "闭环跟踪",
  local_reacquire: "局部重捕获",
  unknown: "未知阶段",
};

function formatTrackingFailure(payload) {
  const message = payload?.message || "后端返回未知错误。";
  const stage = payload?.failed_stage
    ? STAGE_LABELS[payload.failed_stage] || payload.failed_stage
    : "";
  const hint = payload?.hint || "";
  const code = payload?.error_code ? ` [${payload.error_code}]` : "";
  const head = stage ? `${stage}${code}：${message}` : `${message}${code}`;
  return hint ? `${head}\n建议：${hint}` : head;
}

function numberOr(value, fallback = 0) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : fallback;
}

function fitCalibration(points, splittingField) {
  const valid = (Array.isArray(points) ? points : [])
    .map((point) => ({
      x: Number(point?.[splittingField]),
      y: Number(point?.current_a),
    }))
    .filter((point) => Number.isFinite(point.x) && Number.isFinite(point.y));
  if (valid.length < 2) {
    return null;
  }
  const n = valid.length;
  const sumX = valid.reduce((sum, point) => sum + point.x, 0);
  const sumY = valid.reduce((sum, point) => sum + point.y, 0);
  const sumXX = valid.reduce((sum, point) => sum + point.x * point.x, 0);
  const sumXY = valid.reduce((sum, point) => sum + point.x * point.y, 0);
  const denominator = n * sumXX - sumX * sumX;
  if (Math.abs(denominator) < 1e-30) {
    return null;
  }
  const slope = (n * sumXY - sumX * sumY) / denominator;
  return {
    slope_a_per_hz: slope,
    intercept_a: (sumY - slope * sumX) / n,
    point_count: n,
  };
}

function formatCurrent(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return "--";
  }
  return Math.abs(numeric) >= 1
    ? `${numeric.toFixed(6)} A`
    : `${(numeric * 1e3).toFixed(3)} mA`;
}

function formatMHz(value) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? `${(numeric / 1e6).toFixed(6)} MHz` : "--";
}

function formatKHz(value) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? `${(numeric / 1e3).toFixed(3)} kHz` : "--";
}

function targetLabel(target) {
  if (target === "complex_projection") {
    return "复数投影";
  }
  if (target === "zero_crossing") {
    return "过零点";
  }
  if (target === "minimum") {
    return "最低点";
  }
  return "自动";
}

/** 输出 invalid_reason → 简短中文（简易/调机可读） */
function invalidReasonLabel(reason) {
  if (!reason) {
    return "等待锁定";
  }
  const map = {
    both_peaks_not_locked: "双峰未同时 LOCKED",
    peak_identity_invalid: "左右峰身份异常",
    delta_f_outside_physical_range: "Δf 超出物理范围",
    delta_f_uncertainty_too_large: "Δf 不确定度过大",
    current_outside_calibration_range: "Δf 超出标定范围",
    current_calibration_missing: "缺少电流标定（≥2 点）",
    full_reacquire: "正在全频重捕获",
    full_scan: "正在全频扫峰",
    calibrating_complex_models: "正在标定复数模型",
  };
  return map[reason] || String(reason);
}

function peakStateLabel(state) {
  if (!state) {
    return "--";
  }
  const map = {
    UNINITIALIZED: "未初始化",
    ACQUIRING: "捕获中",
    LOCKED: "已锁定",
    SUSPECT: "可疑",
    LOCAL_REACQUIRE: "局部重捕",
    LOST: "丢失",
  };
  return map[state] || state;
}

function lockLabel(state) {
  const labels = {
    idle: "待机",
    connecting: "连接中",
    acquiring: "扫描捕获",
    locked: "已锁定",
    warning: "锁定告警",
    relocking: "重新扫峰",
    error: "错误",
    stopped: "已停止",
  };
  return labels[state] || state || "待机";
}

function lockColor(state) {
  if (state === "locked") {
    return "teal";
  }
  if (state === "warning" || state === "relocking") {
    return "yellow";
  }
  if (state === "error") {
    return "red";
  }
  return "gray";
}

function timingBottleneckLabel(value) {
  const labels = {
    microwave_command_ms: "微波 SCPI 写频",
    settle_ms: "稳定等待",
    lock_wait_ms: "Zurich 设备锁等待",
    lockin_read_ms: "Zurich 单点读取",
    other_ms: "计算/调度/其他",
  };
  return labels[value] || "等待诊断";
}

function formatMs(value) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? `${numeric.toFixed(2)} ms` : "--";
}

export function CurrentTrackingPanel({
  currentForm,
  onCurrentFormChange,
  onSyncFromMicrowave,
  onUseDefaultResonance,
  calibrationPoints,
  onAddPhysicalCalibrationPoint,
  lockinConnected,
  microwaveConnected,
  measurementBusy,
}) {
  const [form, setForm] = useState(DEFAULT_TRACKING_FORM);
  const [sensitivityPreset, setSensitivityPreset] = useState("robust");
  const [uiMode, setUiMode] = useState(loadUiMode);
  const [plotWindowS, setPlotWindowS] = useState(loadPlotWindowSeconds);
  const [selectedPair, setSelectedPair] = useState(null);
  const [configConfirmed, setConfigConfirmed] = useState(false);
  const [isTracking, setIsTracking] = useState(false);
  const [lockState, setLockState] = useState("idle");
  const [statusText, setStatusText] = useState("等待启动");
  const [activeTarget, setActiveTarget] = useState("complex_projection");
  const [points, setPoints] = useState([]);
  const [latestPoint, setLatestPoint] = useState(null);
  const [relockCount, setRelockCount] = useState(0);
  const [warningReasons, setWarningReasons] = useState([]);
  const [capabilityWarning, setCapabilityWarning] = useState("");
  const [dcIndependent, setDcIndependent] = useState(false);
  const [knownCurrentA, setKnownCurrentA] = useState(null);
  const [timingDiagnostics, setTimingDiagnostics] = useState(null);
  const [recordingStatus, setRecordingStatus] = useState(null);
  const [isDownloadingRecording, setIsDownloadingRecording] = useState(false);

  const applySensitivityPreset = (presetKey) => {
    const preset = TRACKING_PRESETS[presetKey] || TRACKING_PRESETS.robust;
    setSensitivityPreset(presetKey);
    setForm((previous) => ({
      ...previous,
      ...preset.values,
    }));
    setConfigConfirmed(false);
    if (currentForm && onCurrentFormChange) {
      onCurrentFormChange({
        ...currentForm,
        settle_ms: preset.searchSettleMs,
      });
    }
  };

  const changeUiMode = (mode) => {
    const next = UI_MODES[mode] ? mode : "simple";
    setUiMode(next);
    persistUiMode(next);
    // 仅改可见性，不清「配置已确认」、不改数值
  };

  const showTuning = uiModeLevel(uiMode) >= 1;
  const showExpert = uiModeLevel(uiMode) >= 2;

  const markConfigDirty = () => setConfigConfirmed(false);

  const patchForm = (updater) => {
    markConfigDirty();
    setForm(updater);
  };

  const confirmCurrentConfig = () => {
    if (!currentForm) {
      notifications.show({
        color: "red",
        title: "无法确认",
        message: "捕获范围表单尚未就绪。",
      });
      return false;
    }
    const startHz = numberOr(currentForm.start_hz, NaN);
    const stopHz = numberOr(currentForm.stop_hz, NaN);
    const searchPoints = Math.round(numberOr(currentForm.search_points, 0));
    const settleMs = numberOr(currentForm.settle_ms, NaN);
    if (!(Number.isFinite(startHz) && Number.isFinite(stopHz) && stopHz > startHz)) {
      notifications.show({
        color: "red",
        title: "参数无效",
        message: "起始频率必须小于终止频率。",
      });
      return false;
    }
    if (!(searchPoints >= 11)) {
      notifications.show({
        color: "red",
        title: "参数无效",
        message: "搜索点数至少为 11。",
      });
      return false;
    }
    if (!(settleMs > 0)) {
      notifications.show({
        color: "red",
        title: "参数无效",
        message: "初始扫频稳定等待必须大于 0。",
      });
      return false;
    }
    if (!(numberOr(form.probe_offset_hz) > 0)) {
      notifications.show({
        color: "red",
        title: "参数无效",
        message: "复数模型/斜率探测偏移必须大于 0。",
      });
      return false;
    }
    if (form.bad_samples_to_lose < form.bad_samples_to_suspect) {
      notifications.show({
        color: "red",
        title: "参数无效",
        message: "进入重捕获的坏样本数不能小于进入可疑的坏样本数。",
      });
      return false;
    }
    if (!(form.slope_ratio_max > form.slope_ratio_min)) {
      notifications.show({
        color: "red",
        title: "参数无效",
        message: "斜率比上限必须大于下限。",
      });
      return false;
    }
    setConfigConfirmed(true);
    notifications.show({
      color: "teal",
      title: "配置已确认",
      message: `捕获 ${(startHz / 1e9).toFixed(4)}–${(stopHz / 1e9).toFixed(4)} GHz，${searchPoints} 点，驻留 ${settleMs.toFixed(1)} ms；灵敏度预设=${TRACKING_PRESETS[sensitivityPreset]?.label || sensitivityPreset}`,
    });
    return true;
  };
  const socketRef = useRef(null);

  useEffect(
    () => () => {
      socketRef.current?.close();
      socketRef.current = null;
    },
    []
  );

  useEffect(() => {
    let active = true;
    api.currentTrackingRecordingStatus()
      .then((result) => {
        if (active && result?.data?.session_id) {
          setRecordingStatus(result.data);
        }
      })
      .catch(() => {
        // 没有历史记录或后端尚未启动时保持空状态。
      });
    return () => {
      active = false;
    };
  }, []);

  const updateNumber = (field, minimum = 0) => (value) => {
    patchForm((previous) => ({
      ...previous,
      [field]: Math.max(minimum, numberOr(value, previous[field])),
    }));
  };

  const physicalCalibrationPoints = (Array.isArray(calibrationPoints) ? calibrationPoints : [])
    .filter((point) => point?.source === "physical_peak_tracking");
  const minimumCalibration = fitCalibration(
    physicalCalibrationPoints,
    "resonance_splitting_hz"
  );
  const calibrationSplittings = physicalCalibrationPoints
    .map((point) => Number(point?.resonance_splitting_hz))
    .filter((value) => Number.isFinite(value));
  const calibrationDeltaMinHz = calibrationSplittings.length
    ? Math.min(...calibrationSplittings)
    : null;
  const calibrationDeltaMaxHz = calibrationSplittings.length
    ? Math.max(...calibrationSplittings)
    : null;
  const canConvertSelectedTarget = Boolean(minimumCalibration);

  const closeSocket = () => {
    const socket = socketRef.current;
    socketRef.current = null;
    if (socket && socket.readyState < WebSocket.CLOSING) {
      socket.close();
    }
  };

  const startTracking = () => {
    if (measurementBusy || isTracking) {
      notifications.show({
        color: "yellow",
        title: "已有任务运行",
        message: "请先停止当前测量任务。",
      });
      return;
    }
    if (!lockinConnected || !microwaveConnected) {
      notifications.show({
        color: "red",
        title: "设备未连接",
        message: "PID 双峰跟踪需要同时连接锁相和微波源。",
      });
      return;
    }
    if (!configConfirmed) {
      notifications.show({
        color: "yellow",
        title: "请先确认配置",
        message: "修改参数后需点击「确认配置」，校验通过后再启动跟踪。",
      });
      return;
    }
    if (!canConvertSelectedTarget) {
      notifications.show({
        color: "yellow",
        title: "将只输出峰位和 Δf",
        message: "当前缺少至少 2 个物理峰心电流标定点；跟踪可以启动，但电流会保持 invalid。",
      });
    }

    closeSocket();
    setPoints([]);
    setLatestPoint(null);
    setRelockCount(0);
    setWarningReasons([]);
    setCapabilityWarning("");
    setTimingDiagnostics(null);
    setRecordingStatus(null);
    setSelectedPair(null);
    setLockState("connecting");
    setStatusText("正在连接跟踪通道");
    const socket = new WebSocket(wsUrl("/measurement/current/tracking/ws"));
    socketRef.current = socket;

    socket.onopen = () => {
      setIsTracking(true);
      socket.send(
        JSON.stringify({
          ...form,
          channel_index: currentForm.channel_index,
          start_hz: currentForm.start_hz,
          stop_hz: currentForm.stop_hz,
          search_points: currentForm.search_points,
          search_settle_ms: currentForm.settle_ms,
          minimum_calibration_slope_a_per_hz:
            minimumCalibration?.slope_a_per_hz ?? null,
          minimum_calibration_intercept_a:
            minimumCalibration?.intercept_a ?? null,
          calibration_delta_f_min_hz: calibrationDeltaMinHz,
          calibration_delta_f_max_hz: calibrationDeltaMaxHz,
        })
      );
    };

    socket.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        if (payload.type === "current_tracking_started") {
          setLockState("acquiring");
          setRecordingStatus(payload.recording || null);
          setStatusText("正在初始扫描并捕获左右共振峰");
        } else if (payload.type === "current_tracking_capability") {
          const warning = payload.warning || "";
          setDcIndependent(Boolean(payload.dc_independent));
          setCapabilityWarning(warning);
          if (warning) {
            notifications.show({
              color: "yellow",
              title: "峰存在性能力告警",
              message: warning,
            });
          }
        } else if (payload.type === "current_tracking_state") {
          const state = payload.global_state || "";
          setLockState(state === "FULL_REACQUIRE" ? "relocking" : "acquiring");
          setStatusText(
            state === "FULL_REACQUIRE"
              ? "输出已标记无效，正在全频段重捕获"
              : state === "CALIBRATE"
                ? "正在标定左右峰复数 b/g 模型"
                : "正在执行完整 FM R 双瓣谷扫频"
          );
        } else if (payload.type === "current_tracking_pair_selected") {
          setSelectedPair({
            left_center_hz: payload.left_center_hz,
            right_center_hz: payload.right_center_hz,
            separation_hz: payload.separation_hz,
            selection_rule: payload.selection_rule,
          });
          setStatusText(
            `已选双瓣谷心：左 ${formatGHz(payload.left_center_hz)} / 右 ${formatGHz(payload.right_center_hz)}（规则：双瓣夹谷最低点）`
          );
        } else if (payload.type === "current_tracking_models_calibrated") {
          setActiveTarget("complex_projection");
          setDcIndependent(Boolean(payload.dc_independent));
          setLockState("acquiring");
          setStatusText("复数模型已标定，等待连续有效样本确认锁定");
        } else if (payload.type === "current_tracking_local_reacquire") {
          if (payload.stage === "start") {
            setLockState("relocking");
            setStatusText(`${payload.peak_id === "left" ? "左峰" : "右峰"}正在局部重捕获`);
          } else if (payload.stage === "success") {
            setLockState("acquiring");
            setStatusText("局部重捕获成功，正在无扰渐升 PID 增益");
          } else if (payload.stage === "failed") {
            setLockState("relocking");
            setStatusText("局部重捕获失败，即将进行全频段重扫");
          }
        } else if (payload.type === "current_tracking_slope_verification") {
          if (!payload.valid) {
            setLockState("warning");
            setStatusText(`${payload.peak_id === "left" ? "左峰" : "右峰"}实时复数斜率验证失败`);
          }
        } else if (payload.type === "current_tracking_timing") {
          setTimingDiagnostics(payload.timing || null);
        } else if (payload.type === "current_tracking_recording") {
          setRecordingStatus(payload.recording || null);
        } else if (payload.type === "current_tracking_acquiring") {
          setLockState(payload.reason === "initial" ? "acquiring" : "relocking");
          setStatusText(payload.reason === "initial" ? "正在扫描双峰" : "失锁后正在重新扫峰");
        } else if (payload.type === "current_tracking_target_fallback") {
          setStatusText(payload.message || "已切换跟踪目标");
          notifications.show({
            color: "yellow",
            title: "自动降级",
            message: payload.message || "过零点质量不足，改用最低点跟踪。",
          });
        } else if (payload.type === "current_tracking_locked") {
          setLockState("locked");
          setActiveTarget(payload.tracking_target || "auto");
          setRelockCount(numberOr(payload.relock_count, 0));
          setWarningReasons([]);
          setStatusText(payload.reason === "reacquired" ? "重扫成功，双峰已重新锁定" : "双峰已锁定");
          setLatestPoint((previous) => ({
            ...(previous || {}),
            left_frequency_hz: payload.left_frequency_hz,
            right_frequency_hz: payload.right_frequency_hz,
            splitting_hz: payload.splitting_hz,
            tracking_target: payload.tracking_target,
          }));
          if (payload.reason === "reacquired") {
            notifications.show({
              color: "teal",
              title: "重新锁定",
              message: `第 ${numberOr(payload.relock_count, 0)} 次重扫成功。`,
            });
          }
        } else if (payload.type === "current_tracking_point") {
          const point = payload.point || {};
          setLockState(point.valid ? "locked" : point.global_state === "FULL_REACQUIRE" ? "relocking" : "warning");
          setActiveTarget(point.tracking_target || "complex_projection");
          setLatestPoint(point);
          setRelockCount(numberOr(point.relock_count, 0));
          setWarningReasons(point.valid || !point.invalid_reason ? [] : [point.invalid_reason]);
          setStatusText(point.valid ? "双峰可靠锁定，输出有效" : `输出无效：${point.invalid_reason || "等待锁定"}`);
          setPoints((previous) => appendTrackingPoint(previous, point));
        } else if (payload.type === "current_tracking_lock_warning") {
          setLockState("warning");
          setWarningReasons(Array.isArray(payload.reasons) ? payload.reasons : []);
          setStatusText(
            `锁定质量告警 ${numberOr(payload.consecutive_invalid_cycles, 0)}/${numberOr(payload.lost_lock_cycles, 0)}`
          );
        } else if (payload.type === "current_tracking_lock_lost") {
          setLockState("relocking");
          setRelockCount(numberOr(payload.relock_count, 0));
          setWarningReasons(Array.isArray(payload.reasons) ? payload.reasons : []);
          setStatusText("双峰失锁，正在自动重新扫峰");
          notifications.show({
            color: "orange",
            title: "检测到失锁",
            message: (payload.reasons || []).join("；") || "正在自动重扫。",
          });
        } else if (
          payload.type === "current_tracking_complete" ||
          payload.type === "current_tracking_cancelled"
        ) {
          setIsTracking(false);
          setLockState("stopped");
          setRecordingStatus(payload.result?.recording || recordingStatus);
          setStatusText(
            payload.type === "current_tracking_cancelled" ? "跟踪已停止" : "跟踪时长结束"
          );
          closeSocket();
        } else if (payload.type === "current_tracking_error") {
          setIsTracking(false);
          setLockState("error");
          const detail = formatTrackingFailure(payload);
          setStatusText(detail.replace(/\n/g, " · "));
          notifications.show({
            color: "red",
            title: payload.failed_stage
              ? `PID 跟踪失败 · ${STAGE_LABELS[payload.failed_stage] || payload.failed_stage}`
              : "PID 跟踪失败",
            message: detail,
            autoClose: 12000,
          });
          closeSocket();
        }
      } catch {
        // 忽略格式不完整的帧，下一帧仍可继续跟踪。
      }
    };

    socket.onerror = () => {
      setLockState("error");
      setStatusText("跟踪 WebSocket 连接异常");
    };
    socket.onclose = () => {
      if (socketRef.current === socket) {
        socketRef.current = null;
        setIsTracking(false);
        setLockState("error");
        setStatusText("跟踪连接意外断开");
        api.currentTrackingRecordingStatus()
          .then((result) => setRecordingStatus(result?.data || null))
          .catch(() => {});
      }
    };
  };

  const stopTracking = async () => {
    try {
      setStatusText("正在请求停止");
      await api.stopCurrent();
    } catch (error) {
      notifications.show({
        color: "red",
        title: "停止失败",
        message: error instanceof Error ? error.message : "未知错误",
      });
    }
  };

  const updateCurrentNumber = (field, minimum = null, integer = false) => (value) => {
    markConfigDirty();
    const previousValue = currentForm?.[field];
    let numeric = numberOr(value, previousValue);
    if (integer) {
      numeric = Math.round(numeric);
    }
    if (minimum !== null) {
      numeric = Math.max(minimum, numeric);
    }
    onCurrentFormChange?.({
      ...currentForm,
      [field]: numeric,
    });
  };

  const downloadRecording = async () => {
    try {
      setIsDownloadingRecording(true);
      const result = await api.downloadCurrentTrackingRecording(
        recordingStatus?.session_id || ""
      );
      const url = URL.createObjectURL(result.blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = result.filename;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
      const statusResult = await api.currentTrackingRecordingStatus(
        recordingStatus?.session_id || ""
      );
      setRecordingStatus(statusResult?.data || recordingStatus);
      notifications.show({
        color: "teal",
        title: "Excel 已生成",
        message: "下载内容是截至当前时刻的 1 秒聚合数据快照。",
      });
    } catch (error) {
      notifications.show({
        color: "red",
        title: "导出失败",
        message: error instanceof Error ? error.message : "未知错误",
      });
    } finally {
      setIsDownloadingRecording(false);
    }
  };

  const addPhysicalCalibrationPoint = () => {
    const currentA = Number(knownCurrentA);
    const splittingHz = Number(latestPoint?.splitting_hz);
    const peaksLocked =
      latestPoint?.left_state === "LOCKED" && latestPoint?.right_state === "LOCKED";
    if (!Number.isFinite(currentA)) {
      notifications.show({ color: "red", title: "缺少已知电流", message: "请先输入标定电流值。" });
      return;
    }
    if (!peaksLocked || !Number.isFinite(splittingHz) || splittingHz <= 0) {
      notifications.show({
        color: "yellow",
        title: "物理峰心尚未可靠锁定",
        message: "只有左右峰均为 LOCKED 时才能写入物理峰心标定。",
      });
      return;
    }
    onAddPhysicalCalibrationPoint?.({
      current_a: currentA,
      resonance_splitting_hz: splittingHz,
      left_resonance_hz: Number(latestPoint.left_frequency_hz),
      right_resonance_hz: Number(latestPoint.right_frequency_hz),
      delta_f_sigma_hz: Number(latestPoint.delta_f_sigma_hz),
    });
    setKnownCurrentA(null);
    notifications.show({
      color: "teal",
      title: "已加入物理峰心标定",
      message: `${formatCurrent(currentA)} ↔ ${formatMHz(splittingHz)}。达到 2 点后请重新启动跟踪以加载新标定。`,
    });
  };

  const plotSlice = slicePointsByWindow(points, plotWindowS);
  const plotPoints = plotSlice.points;
  const plotXRange = plotSlice.xRange;
  const elapsed = plotPoints.map((point) => numberOr(point.elapsed_s));
  const leftGHz = plotPoints.map((point) => numberOr(point.left_frequency_hz) / 1e9);
  const rightGHz = plotPoints.map((point) => numberOr(point.right_frequency_hz) / 1e9);
  const currentMa = plotPoints.map((point) => numberOr(point.estimated_current_a, NaN) * 1e3);

  const changePlotWindow = (value) => {
    const match = PLOT_WINDOW_OPTIONS.find((item) => item.value === String(value));
    const seconds = match?.seconds ?? 60;
    setPlotWindowS(seconds);
    persistPlotWindowSeconds(seconds);
  };
  const leftPid = latestPoint?.left_pid || {};
  const rightPid = latestPoint?.right_pid || {};
  const saturated = Boolean(leftPid.saturated || rightPid.saturated);
  const latestUpdateRateHz =
    points.length >= 2
      ? 1 /
        Math.max(
          1e-9,
          numberOr(points[points.length - 1]?.elapsed_s) -
            numberOr(points[points.length - 2]?.elapsed_s)
        )
      : NaN;

  return (
    <SectionCard
      title="PID 闭环双峰连续跟踪"
      description="峰心定义（不可改）：FM 1f 双瓣夹谷的最低谷底。用「界面模式」控制显示多少参数；用「灵敏度预设」控制门限松紧。两者独立，隐藏参数仍会按当前值提交。"
      badge={lockLabel(lockState)}
    >
      <Group mb="md">
        <Badge color={lockColor(lockState)} variant="light">
          {statusText}
        </Badge>
        {warningReasons.length ? (
          <Text c="orange" size="sm">{warningReasons.join("；")}</Text>
        ) : null}
      </Group>
      {capabilityWarning ? (
        <Text c="yellow" size="sm" mb="md">{capabilityWarning}</Text>
      ) : null}
      {selectedPair ? (
        <Text c="teal" size="sm" mb="md">
          当前候选双瓣谷心：{formatGHz(selectedPair.left_center_hz)} /{" "}
          {formatGHz(selectedPair.right_center_hz)}
          {Number.isFinite(Number(selectedPair.separation_hz))
            ? `，Δf ${formatMHz(selectedPair.separation_hz)}`
            : ""}
          （selection_rule={selectedPair.selection_rule || "fm_lobe_valley_lobe_minima"}）
        </Text>
      ) : null}

      <SimpleGrid cols={{ base: 1, md: 2 }} mb="md">
        <Select
          label="界面模式"
          description="只控制显示多少参数，不改数值。日常用简易即可。"
          value={uiMode}
          disabled={isTracking}
          data={Object.entries(UI_MODES).map(([value, item]) => ({
            value,
            label: item.label,
          }))}
          onChange={(value) => changeUiMode(value || "simple")}
        />
        <Select
          label="灵敏度预设"
          description="稳健更易进锁；严格更抗误跟。均不改变双瓣夹谷峰心定义。"
          value={sensitivityPreset}
          disabled={isTracking}
          data={Object.entries(TRACKING_PRESETS).map(([value, item]) => ({
            value,
            label: item.label,
          }))}
          onChange={(value) => applySensitivityPreset(value || "robust")}
        />
      </SimpleGrid>
      <Text c="dimmed" size="sm" mb="md">
        {uiMode === "simple"
          ? "当前为简易模式：只显示捕获范围与启停。需要拧 PID / R² 时请切到「调机」；找峰门槛等请用「专家」。"
          : uiMode === "tuning"
            ? "当前为调机模式：可调驻留、PID、锁定门限。隐藏参数仍用当前数值提交。"
            : "当前为专家模式：显示全部参数。显著度/歧义只过滤候选，峰心仍是双瓣夹谷的最低谷。"}
      </Text>

      <Text fw={600} mb="xs">初始双峰捕获范围</Text>
      <SimpleGrid cols={{ base: 1, md: 2, xl: 4 }}>
        {showTuning ? (
          <NumberInput
            label="锁相通道"
            value={currentForm.channel_index}
            disabled={isTracking}
            min={0}
            onChange={updateCurrentNumber("channel_index", 0, true)}
          />
        ) : null}
        <NumberInput
          label="起始频率 (Hz)"
          value={currentForm.start_hz}
          disabled={isTracking}
          onChange={updateCurrentNumber("start_hz")}
        />
        <NumberInput
          label="终止频率 (Hz)"
          value={currentForm.stop_hz}
          disabled={isTracking}
          onChange={updateCurrentNumber("stop_hz")}
        />
        <NumberInput
          label="搜索点数"
          value={currentForm.search_points}
          disabled={isTracking}
          min={11}
          onChange={updateCurrentNumber("search_points", 11, true)}
        />
        <NumberInput
          label="初始扫频稳定等待 (ms)"
          value={currentForm.settle_ms}
          disabled={isTracking}
          min={0.1}
          onChange={updateCurrentNumber("settle_ms", 0.1)}
        />
        {showTuning ? (
          <NumberInput
            label="独立 DC/峰存在性通道 (-1=未配置)"
            value={form.independent_dc_channel_index}
            disabled={isTracking}
            min={-1}
            onChange={(value) =>
              patchForm((previous) => ({
                ...previous,
                independent_dc_channel_index: Math.max(
                  -1,
                  Math.round(numberOr(value, previous.independent_dc_channel_index))
                ),
              }))
            }
          />
        ) : null}
        {showTuning ? (
          <NumberInput
            label="复数模型/斜率探测偏移 (Hz)"
            value={form.probe_offset_hz}
            disabled={isTracking}
            onChange={updateNumber("probe_offset_hz", 1)}
          />
        ) : null}
        {showTuning ? (
          <NumberInput
            label="每点稳定等待 (ms)"
            value={form.tracking_settle_ms}
            disabled={isTracking}
            onChange={updateNumber("tracking_settle_ms", 0.1)}
          />
        ) : null}
        {showTuning ? (
          <NumberInput
            label="每点平均次数"
            value={form.sample_averages}
            disabled={isTracking}
            min={1}
            onChange={(value) =>
              patchForm((previous) => ({
                ...previous,
                sample_averages: Math.max(1, Math.round(numberOr(value, previous.sample_averages))),
              }))
            }
          />
        ) : null}
        {showExpert ? (
          <NumberInput
            label="耗时分析报告间隔 (周期)"
            value={form.timing_report_interval_cycles}
            disabled={isTracking}
            min={1}
            onChange={(value) =>
              patchForm((previous) => ({
                ...previous,
                timing_report_interval_cycles: Math.max(
                  1,
                  Math.round(numberOr(value, previous.timing_report_interval_cycles))
                ),
              }))
            }
          />
        ) : null}
      </SimpleGrid>

      {showTuning ? (
        <>
          <Text fw={600} mt="md" mb="xs">
            PID 与锁定门限
          </Text>
          <SimpleGrid cols={{ base: 1, md: 2, xl: 4 }}>
            <NumberInput label="Kp" value={form.kp} disabled={isTracking} onChange={updateNumber("kp")} />
            <NumberInput
              label="Ki (1/s)"
              value={form.ki_per_s}
              disabled={isTracking}
              onChange={updateNumber("ki_per_s")}
            />
            {showExpert ? (
              <NumberInput
                label="Kd (s)"
                value={form.kd_s}
                disabled={isTracking}
                onChange={updateNumber("kd_s")}
              />
            ) : null}
            {showExpert ? (
              <NumberInput
                label="微分滤波时间常数 (s)"
                value={form.derivative_filter_tau_s}
                disabled={isTracking}
                min={0}
                onChange={updateNumber("derivative_filter_tau_s")}
              />
            ) : null}
            {showExpert ? (
              <NumberInput
                label="抗饱和反算增益 (1/s)"
                value={form.antiwindup_gain_per_s}
                disabled={isTracking}
                min={0}
                onChange={updateNumber("antiwindup_gain_per_s")}
              />
            ) : null}
            <NumberInput
              label="单周期最大校正 (Hz)"
              value={form.max_step_hz}
              disabled={isTracking}
              onChange={updateNumber("max_step_hz", 1)}
            />
            {showExpert ? (
              <NumberInput
                label="最大变化率 (Hz/s)"
                value={form.maximum_slew_hz_per_s}
                disabled={isTracking}
                onChange={updateNumber("maximum_slew_hz_per_s", 1)}
              />
            ) : null}
            {showExpert ? (
              <NumberInput
                label="积分项限幅 (Hz)"
                value={form.integral_limit_hz}
                disabled={isTracking}
                onChange={updateNumber("integral_limit_hz")}
              />
            ) : null}
            <NumberInput
              label="失锁偏差阈值 (Hz)"
              value={form.lock_error_limit_hz}
              disabled={isTracking}
              onChange={updateNumber("lock_error_limit_hz", 1)}
            />
            <NumberInput
              label="复数模型最小 R²"
              value={form.minimum_complex_fit_r2}
              disabled={isTracking}
              min={0}
              max={1}
              onChange={updateNumber("minimum_complex_fit_r2")}
            />
            {showExpert ? (
              <NumberInput
                label="正交残差限值比例"
                value={form.orthogonal_limit_fraction}
                disabled={isTracking}
                min={0.001}
                onChange={updateNumber("orthogonal_limit_fraction", 0.001)}
              />
            ) : null}
            {showExpert ? (
              <NumberInput
                label="实时斜率验证间隔 (每峰访问数)"
                value={form.verify_interval_visits}
                disabled={isTracking}
                min={1}
                onChange={(value) =>
                  patchForm((previous) => ({
                    ...previous,
                    verify_interval_visits: Math.max(
                      1,
                      Math.round(numberOr(value, previous.verify_interval_visits))
                    ),
                  }))
                }
              />
            ) : null}
            <NumberInput
              label="进入可疑的坏样本数"
              value={form.bad_samples_to_suspect}
              disabled={isTracking}
              min={1}
              onChange={(value) =>
                patchForm((previous) => ({
                  ...previous,
                  bad_samples_to_suspect: Math.max(
                    1,
                    Math.round(numberOr(value, previous.bad_samples_to_suspect))
                  ),
                }))
              }
            />
            <NumberInput
              label="进入重捕获的坏样本数"
              value={form.bad_samples_to_lose}
              disabled={isTracking}
              min={1}
              onChange={(value) =>
                patchForm((previous) => ({
                  ...previous,
                  bad_samples_to_lose: Math.max(
                    1,
                    Math.round(numberOr(value, previous.bad_samples_to_lose))
                  ),
                }))
              }
            />
            <NumberInput
              label="确认锁定的好样本数"
              value={form.good_samples_to_lock}
              disabled={isTracking}
              min={1}
              onChange={(value) =>
                patchForm((previous) => ({
                  ...previous,
                  good_samples_to_lock: Math.max(
                    1,
                    Math.round(numberOr(value, previous.good_samples_to_lock))
                  ),
                }))
              }
            />
            <NumberInput
              label="最大自动重扫次数 (0=不限)"
              value={form.max_relock_attempts}
              disabled={isTracking}
              min={0}
              onChange={(value) =>
                patchForm((previous) => ({
                  ...previous,
                  max_relock_attempts: Math.max(
                    0,
                    Math.round(numberOr(value, previous.max_relock_attempts))
                  ),
                }))
              }
            />
            {showExpert ? (
              <NumberInput
                label="最长跟踪时间 (s，0=连续)"
                value={form.max_tracking_duration_s}
                disabled={isTracking}
                onChange={updateNumber("max_tracking_duration_s")}
              />
            ) : null}
          </SimpleGrid>
        </>
      ) : null}

      {showExpert ? (
        <Stack gap="sm" mt="md">
          <Text fw={600}>专家：找峰门槛 / 斜率验证 / 局部重扫</Text>
          <Text c="dimmed" size="sm">
            显著度与歧义比只决定「候选是否够格」；峰心始终是双瓣之间的最低谷，不会改成任意极小值。
          </Text>
          <SimpleGrid cols={{ base: 1, md: 2, xl: 4 }}>
            <NumberInput
              label="峰瓣显著度相对阈值"
              description="minimum_peak_prominence_fraction"
              value={form.minimum_peak_prominence_fraction}
              disabled={isTracking}
              min={0}
              max={1}
              step={0.01}
              decimalScale={3}
              onChange={updateNumber("minimum_peak_prominence_fraction")}
            />
            <NumberInput
              label="双峰配对歧义比"
              description="越接近 1 越严；并列时仍拒绝猜测"
              value={form.peak_pair_ambiguity_score_ratio}
              disabled={isTracking}
              min={0.01}
              max={1}
              step={0.01}
              decimalScale={3}
              onChange={updateNumber("peak_pair_ambiguity_score_ratio", 0.01)}
            />
            <NumberInput
              label="Δf 物理下限 (Hz)"
              value={form.delta_f_min_hz}
              disabled={isTracking}
              min={0}
              onChange={updateNumber("delta_f_min_hz")}
            />
            <NumberInput
              label="Δf 物理上限 (Hz)"
              value={form.delta_f_max_hz}
              disabled={isTracking}
              min={1}
              onChange={updateNumber("delta_f_max_hz", 1)}
            />
            <NumberInput
              label="可分辨间距系数"
              value={form.minimum_resolvable_separation_factor}
              disabled={isTracking}
              min={0}
              step={0.05}
              decimalScale={3}
              onChange={updateNumber("minimum_resolvable_separation_factor")}
            />
            <NumberInput
              label="线性区误差比例"
              value={form.maximum_error_fraction}
              disabled={isTracking}
              min={0.01}
              max={1}
              step={0.05}
              decimalScale={3}
              onChange={updateNumber("maximum_error_fraction", 0.01)}
            />
            <NumberInput
              label="峰深度比例门限"
              value={form.minimum_depth_fraction}
              disabled={isTracking}
              min={0}
              max={1}
              step={0.05}
              decimalScale={3}
              onChange={updateNumber("minimum_depth_fraction")}
            />
            <NumberInput
              label="斜率比下限"
              value={form.slope_ratio_min}
              disabled={isTracking}
              min={0.01}
              step={0.05}
              decimalScale={3}
              onChange={updateNumber("slope_ratio_min", 0.01)}
            />
            <NumberInput
              label="斜率比上限"
              value={form.slope_ratio_max}
              disabled={isTracking}
              min={0.1}
              step={0.1}
              decimalScale={3}
              onChange={updateNumber("slope_ratio_max", 0.1)}
            />
            <NumberInput
              label="斜率相位变化上限 (rad)"
              value={form.maximum_slope_angle_change_rad}
              disabled={isTracking}
              min={0.1}
              step={0.1}
              decimalScale={3}
              onChange={updateNumber("maximum_slope_angle_change_rad", 0.1)}
            />
            <NumberInput
              label="斜率验证最大时效 (s)"
              value={form.slope_verification_max_age_s}
              disabled={isTracking}
              min={0.1}
              onChange={updateNumber("slope_verification_max_age_s", 0.1)}
            />
            <NumberInput
              label="局部重扫点数"
              value={form.local_scan_points}
              disabled={isTracking}
              min={7}
              onChange={(value) =>
                patchForm((previous) => ({
                  ...previous,
                  local_scan_points: Math.max(7, Math.round(numberOr(value, previous.local_scan_points))),
                }))
              }
            />
            <NumberInput
              label="局部初宽 / FWHM"
              value={form.local_scan_initial_width_fraction}
              disabled={isTracking}
              min={0.1}
              step={0.1}
              decimalScale={3}
              onChange={updateNumber("local_scan_initial_width_fraction", 0.1)}
            />
            <NumberInput
              label="局部扩窗倍数"
              value={form.local_scan_expansion_factor}
              disabled={isTracking}
              min={1.01}
              step={0.1}
              decimalScale={3}
              onChange={updateNumber("local_scan_expansion_factor", 1.01)}
            />
            <NumberInput
              label="局部最大扩窗次数"
              value={form.local_scan_max_expansions}
              disabled={isTracking}
              min={1}
              onChange={(value) =>
                patchForm((previous) => ({
                  ...previous,
                  local_scan_max_expansions: Math.max(
                    1,
                    Math.round(numberOr(value, previous.local_scan_max_expansions))
                  ),
                }))
              }
            />
            <NumberInput
              label="身份保护带 / FWHM"
              value={form.reacquire_identity_guard_fraction}
              disabled={isTracking}
              min={0}
              step={0.05}
              decimalScale={3}
              onChange={updateNumber("reacquire_identity_guard_fraction")}
            />
          </SimpleGrid>
        </Stack>
      ) : null}

      <Group mt="md">
        <Button
          variant="light"
          color="gray"
          onClick={() => {
            markConfigDirty();
            onSyncFromMicrowave?.();
          }}
          disabled={isTracking}
        >
          从微波页同步
        </Button>
        <Button
          variant="light"
          color="gray"
          onClick={() => {
            markConfigDirty();
            onUseDefaultResonance?.();
          }}
          disabled={isTracking}
        >
          回到 2.87 GHz 默认范围
        </Button>
        <Button
          color="cyan"
          variant={configConfirmed ? "light" : "filled"}
          onClick={confirmCurrentConfig}
          disabled={isTracking}
        >
          确认配置
        </Button>
        <Badge variant="light" color={configConfirmed ? "teal" : "yellow"}>
          {configConfirmed ? "配置已确认" : "配置未确认"}
        </Badge>
        <Badge variant="light" color="gray">
          {UI_MODES[uiMode]?.label || uiMode}
        </Badge>
        <Text c="dimmed" size="sm">
          局部重扫会自动扩大，但不会超过这里设置的起止频率。启动跟踪前请先确认配置。
        </Text>
      </Group>

      <SimpleGrid cols={{ base: 1, md: 3 }} mt="lg">
        <Switch
          label="保存长期电流数据"
          description="后台每秒聚合，CSV 增量落盘并可导出 Excel"
          checked={form.record_enabled}
          disabled={isTracking}
          onChange={(event) =>
            patchForm((previous) => ({
              ...previous,
              record_enabled: event.currentTarget.checked,
            }))
          }
        />
        <NumberInput
          label="保存间隔 (s)"
          description="13 小时建议保持 1 s"
          value={form.record_interval_s}
          disabled={isTracking || !form.record_enabled}
          min={0.1}
          max={3600}
          decimalScale={1}
          onChange={updateNumber("record_interval_s", 0.1)}
        />
        <TextInput
          label="实验标签"
          description="会写入文件名和参数表"
          value={form.record_label}
          disabled={isTracking || !form.record_enabled}
          maxLength={80}
          placeholder="例如 coil_2A_13h"
          onChange={(event) =>
            patchForm((previous) => ({
              ...previous,
              record_label: event.currentTarget.value,
            }))
          }
        />
      </SimpleGrid>

      <Group mt="lg">
        <Button
          color="cyan"
          onClick={startTracking}
          loading={lockState === "connecting" || lockState === "acquiring"}
          disabled={measurementBusy || isTracking || !configConfirmed}
        >
          启动 PID 双峰跟踪
        </Button>
        <Button color="red" variant="light" onClick={stopTracking} disabled={!isTracking}>
          停止连续跟踪
        </Button>
        <Button
          variant="light"
          color="blue"
          onClick={downloadRecording}
          loading={isDownloadingRecording}
          disabled={!recordingStatus?.download_available}
        >
          下载 Excel 快照
        </Button>
        {form.record_enabled || recordingStatus?.session_id ? (
          <Badge
            variant="light"
            color={recordingStatus?.status === "recording" ? "teal" : "gray"}
          >
            已保存 {numberOr(recordingStatus?.rows_written, 0)} 点
          </Badge>
        ) : null}
        <Badge variant="light" color={minimumCalibration ? "teal" : "gray"}>
          物理峰心标定 {minimumCalibration?.point_count || 0} 点
        </Badge>
        <Badge variant="light" color={dcIndependent ? "teal" : "yellow"}>
          {dcIndependent ? "独立峰存在性观测" : "FM R 双瓣谷 + 周期 b/g 验证"}
        </Badge>
        <Badge variant="light" color="gray">电流幅值模式</Badge>
      </Group>

      <Group mt="md" align="end">
        <NumberInput
          label="当前已知标定电流 (A)"
          value={knownCurrentA}
          onChange={setKnownCurrentA}
          placeholder="例如 0.01"
          w={240}
        />
        <Button variant="light" onClick={addPhysicalCalibrationPoint}>
          将当前物理峰心 Δf 加入标定
        </Button>
      </Group>

      <Text fw={600} mt="lg" mb="xs">
        实时输出
        <Text span c="dimmed" size="sm" ml="sm" fw={400}>
          {uiMode === "simple"
            ? "简易：锁定状态 · 电流 · Δf · 峰位"
            : uiMode === "tuning"
              ? "调机：结果 + 下发频率 / PID 摘要"
              : "专家：结果 + PID + 时间瓶颈"}
        </Text>
      </Text>
      <SimpleGrid cols={{ base: 1, md: 2, xl: uiMode === "simple" ? 5 : 6 }} mt="xs">
        <MetricCard
          label="锁定状态"
          value={`${peakStateLabel(latestPoint?.left_state)} / ${peakStateLabel(latestPoint?.right_state)}`}
          hint={
            latestPoint?.valid
              ? "双峰 LOCKED，输出有效"
              : invalidReasonLabel(latestPoint?.invalid_reason)
          }
        />
        <MetricCard
          label="实时电流"
          value={formatCurrent(latestPoint?.estimated_current_a)}
          hint={
            latestPoint?.valid
              ? saturated
                ? "有效；PID 输出已限幅"
                : "I = a·Δf + b（标定）"
              : `无效：${invalidReasonLabel(latestPoint?.invalid_reason)}`
          }
        />
        <MetricCard
          label="实时劈裂 Δf"
          value={formatMHz(latestPoint?.splitting_hz)}
          hint={
            Number.isFinite(Number(latestPoint?.delta_f_sigma_hz))
              ? `fR−fL · σ ${formatKHz(latestPoint.delta_f_sigma_hz)}`
              : "fR − fL"
          }
        />
        <MetricCard
          label="左峰 fL"
          value={Number.isFinite(Number(latestPoint?.left_frequency_hz)) ? formatGHz(latestPoint.left_frequency_hz) : "--"}
          hint={`鉴频误差 ${formatKHz(latestPoint?.left_error_hz)}`}
        />
        <MetricCard
          label="右峰 fR"
          value={Number.isFinite(Number(latestPoint?.right_frequency_hz)) ? formatGHz(latestPoint.right_frequency_hz) : "--"}
          hint={`鉴频误差 ${formatKHz(latestPoint?.right_error_hz)}`}
        />
        {showTuning ? (
          <MetricCard
            label="更新速率"
            value={
              Number.isFinite(latestUpdateRateHz)
                ? `${latestUpdateRateHz.toFixed(2)} Hz`
                : "--"
            }
            hint={`自动重扫 ${relockCount} 次`}
          />
        ) : null}
        {showExpert ? (
          <MetricCard
            label="实际目标"
            value={targetLabel(latestPoint?.tracking_target || activeTarget)}
            hint="跟踪算法目标（现为复数投影）"
          />
        ) : null}
      </SimpleGrid>

      {showTuning ? (
        <SimpleGrid cols={{ base: 1, md: 2, xl: 4 }} mt="md">
          <MetricCard
            label="左下发频率"
            value={Number.isFinite(Number(leftPid.applied_hz)) ? formatGHz(leftPid.applied_hz) : "--"}
            hint={
              showExpert
                ? `P ${formatKHz(leftPid.p_hz)} / I ${formatKHz(leftPid.i_hz)} / D ${formatKHz(leftPid.d_hz)}`
                : `命令微波 · I ${formatKHz(leftPid.i_hz)}${leftPid.saturated ? " · 限幅" : ""}`
            }
          />
          <MetricCard
            label="右下发频率"
            value={Number.isFinite(Number(rightPid.applied_hz)) ? formatGHz(rightPid.applied_hz) : "--"}
            hint={
              showExpert
                ? `P ${formatKHz(rightPid.p_hz)} / I ${formatKHz(rightPid.i_hz)} / D ${formatKHz(rightPid.d_hz)}`
                : `命令微波 · I ${formatKHz(rightPid.i_hz)}${rightPid.saturated ? " · 限幅" : ""}`
            }
          />
          {showExpert ? (
            <MetricCard
              label="左积分 / 正交"
              value={formatKHz(leftPid.i_hz)}
              hint={leftPid.saturated ? "混合抗饱和生效" : `q ${formatKHz(latestPoint?.left_q_hz)}`}
            />
          ) : null}
          {showExpert ? (
            <MetricCard
              label="右积分 / 正交"
              value={formatKHz(rightPid.i_hz)}
              hint={rightPid.saturated ? "混合抗饱和生效" : `q ${formatKHz(latestPoint?.right_q_hz)}`}
            />
          ) : null}
        </SimpleGrid>
      ) : null}

      {showExpert ? (
        <>
          <Text fw={600} mt="lg">
            跟踪时间瓶颈分析
          </Text>
          <SimpleGrid cols={{ base: 1, md: 2, xl: 4 }} mt="xs">
            <MetricCard
              label="自动判定瓶颈"
              value={timingBottleneckLabel(timingDiagnostics?.bottleneck)}
              hint={
                Number.isFinite(Number(timingDiagnostics?.stage_share?.[timingDiagnostics?.bottleneck]))
                  ? `占采集时间 ${(Number(timingDiagnostics.stage_share[timingDiagnostics.bottleneck]) * 100).toFixed(1)}%`
                  : "累计首个闭环周期后开始分析"
              }
            />
            <MetricCard
              label="实测双峰更新率"
              value={
                Number.isFinite(Number(timingDiagnostics?.measured_update_rate_hz))
                  ? `${Number(timingDiagnostics.measured_update_rate_hz).toFixed(2)} Hz`
                  : "--"
              }
              hint={`周期 P50 ${formatMs(timingDiagnostics?.cycle_median_ms)} / P95 ${formatMs(timingDiagnostics?.cycle_p95_ms)}`}
            />
            <MetricCard
              label="微波 SCPI 写频"
              value={formatMs(timingDiagnostics?.stage_mean_ms?.microwave_command_ms)}
              hint="每个频点的 VISA resource.write 耗时"
            />
            <MetricCard
              label="显式稳定等待"
              value={formatMs(timingDiagnostics?.stage_mean_ms?.settle_ms)}
              hint={`配置 ${formatMs(timingDiagnostics?.configured_tracking_settle_ms)} / 实际下限 ${formatMs(timingDiagnostics?.effective_settle_ms)}`}
            />
            <MetricCard
              label="Zurich 设备锁等待"
              value={formatMs(timingDiagnostics?.stage_mean_ms?.lock_wait_ms)}
              hint={
                timingDiagnostics?.background_sampler_running
                  ? `后台 poll 开启，记录窗 ${formatMs(timingDiagnostics?.background_poll_recording_ms)}`
                  : "后台 poll 未运行"
              }
            />
            <MetricCard
              label="Zurich 单点读取"
              value={formatMs(timingDiagnostics?.stage_mean_ms?.lockin_read_ms)}
              hint="demod.sample() 调用耗时"
            />
            <MetricCard
              label="单频点采集"
              value={formatMs(timingDiagnostics?.acquisition_median_ms)}
              hint={`P95 ${formatMs(timingDiagnostics?.acquisition_p95_ms)}`}
            />
            <MetricCard
              label="实际锁相配置"
              value={
                Number.isFinite(Number(timingDiagnostics?.device_bandwidth_hz ?? timingDiagnostics?.lockin_bandwidth_hz))
                  ? `${Number(timingDiagnostics?.device_bandwidth_hz ?? timingDiagnostics?.lockin_bandwidth_hz).toFixed(2)} Hz`
                  : "--"
              }
              hint={`Demod ${timingDiagnostics?.demod_index ?? "--"} / τ ${formatMs(timingDiagnostics?.device_time_constant_ms ?? timingDiagnostics?.lockin_time_constant_ms)} / ${timingDiagnostics?.device_filter_order ?? timingDiagnostics?.lockin_filter_order ?? "--"} 阶${timingDiagnostics?.filter_cache_mismatch ? "；后端缓存不一致" : ""}`}
            />
          </SimpleGrid>
        </>
      ) : null}

      <Group mt="lg" justify="space-between" align="end">
        <Text fw={600}>实时曲线</Text>
        <Select
          label="显示窗口"
          description="频率与电流图共用；内存最多保留最近 1 h"
          value={String(plotWindowS)}
          data={PLOT_WINDOW_OPTIONS.map((item) => ({
            value: item.value,
            label: item.label,
          }))}
          onChange={changePlotWindow}
          w={160}
          allowDeselect={false}
        />
      </Group>
      <Grid mt="sm">
        <Grid.Col span={{ base: 12, xl: 7 }}>
          <Stack gap="xs">
            <Text fw={600}>左右共振频率</Text>
            <PlotCard
              traces={[
                {
                  name: "fL",
                  x: elapsed,
                  y: leftGHz,
                  lineColor: "#64e4c2",
                  hovertemplate: "%{x:.3f} s<br>fL=%{y:.9f} GHz<extra></extra>",
                },
                {
                  name: "fR",
                  x: elapsed,
                  y: rightGHz,
                  lineColor: "#ffb86c",
                  hovertemplate: "%{x:.3f} s<br>fR=%{y:.9f} GHz<extra></extra>",
                },
              ]}
              xTitle="Elapsed Time (s)"
              yTitle="Frequency (GHz)"
              xRange={plotXRange}
              uirevision={`current-pid-frequency-${plotWindowS}`}
            />
          </Stack>
        </Grid.Col>
        <Grid.Col span={{ base: 12, xl: 5 }}>
          <Stack gap="xs">
            <Text fw={600}>实时换算电流</Text>
            <PlotCard
              traces={[
                {
                  name: "Current",
                  x: elapsed,
                  y: currentMa,
                  lineColor: "#8ab4ff",
                  hovertemplate: "%{x:.3f} s<br>I=%{y:.6f} mA<extra></extra>",
                },
              ]}
              xTitle="Elapsed Time (s)"
              yTitle="Current (mA)"
              xRange={plotXRange}
              uirevision={`current-pid-current-${plotWindowS}`}
            />
          </Stack>
        </Grid.Col>
      </Grid>
    </SectionCard>
  );
}
