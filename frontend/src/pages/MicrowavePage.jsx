import { useEffect, useMemo, useRef, useState } from "react";
import {
  Button,
  Grid,
  Group,
  NumberInput,
  Select,
  SimpleGrid,
  Stack,
  Switch,
  Text,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";

import { MetricCard } from "../components/MetricCard";
import { SectionCard } from "../components/SectionCard";
import { useDashboard } from "../hooks/useDashboard";
import { api, formatGHz } from "../lib/api";

const LF_OUTPUT_SOURCE_OPTIONS = [
  { value: "monitor", label: "跟随 FM 内部函数" },
  { value: "function1", label: "独立 Function 1" },
  { value: "dc", label: "DC" },
];

const LF_OUTPUT_LOAD_OPTIONS = [
  { value: "50", label: "50 Ohm" },
  { value: "600", label: "600 Ohm" },
  { value: "1000000", label: "1 MOhm" },
];

const MAX_SWEEP_POINTS = 65535;
const DEFAULT_SWEEP_STEP_HZ = 10_000;

function toFiniteNumber(value, fallback = 0) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

/** Match backend InstrumentManager.compute_sweep_points. */
export function computeSweepPoints(startHz, stopHz, stepHz, maxPoints = MAX_SWEEP_POINTS) {
  const start = toFiniteNumber(startHz, NaN);
  const stop = toFiniteNumber(stopHz, NaN);
  const step = toFiniteNumber(stepHz, NaN);
  if (!Number.isFinite(start) || !Number.isFinite(stop) || !Number.isFinite(step)) {
    return { ok: false, error: "扫频起点、终点和步进必须是有限数值。", points: 0, actualStepHz: 0 };
  }
  if (!(step > 0)) {
    return { ok: false, error: "扫频步进必须大于 0。", points: 0, actualStepHz: 0 };
  }
  if (!(stop > start)) {
    return { ok: false, error: "扫频终点必须大于起点。", points: 0, actualStepHz: 0 };
  }
  const span = stop - start;
  let points = Math.round(span / step) + 1;
  points = Math.max(2, points);
  if (points > maxPoints) {
    return {
      ok: false,
      error: `按步进 ${step} Hz 计算得到 ${points} 个扫频点，超过上限 ${maxPoints}。请增大步进或缩小扫频范围。`,
      points,
      actualStepHz: span / (points - 1),
    };
  }
  return {
    ok: true,
    error: "",
    points,
    actualStepHz: span / (points - 1),
  };
}

function formatStepHz(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return "--";
  }
  if (Math.abs(numeric) >= 1e6) {
    return `${(numeric / 1e6).toFixed(3)} MHz`;
  }
  if (Math.abs(numeric) >= 1e3) {
    return `${(numeric / 1e3).toFixed(3)} kHz`;
  }
  return `${numeric.toFixed(3)} Hz`;
}

function formatElapsedSeconds(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric) || numeric < 0) {
    return "--";
  }
  if (numeric < 60) {
    return `${numeric.toFixed(2)} s`;
  }
  const minutes = Math.floor(numeric / 60);
  const seconds = numeric - minutes * 60;
  return `${minutes}m ${seconds.toFixed(1)}s`;
}

function sweepTriggerStatusLabel(status) {
  if (status === "free_running") {
    return "Free 连续中";
  }
  if (status === "armed") {
    return "已武装（待触发）";
  }
  if (status === "running" || status === "cancelling") {
    return status === "cancelling" ? "正在中止" : "单次扫频中";
  }
  if (status === "completed") {
    return "已完成";
  }
  if (status === "cancelled") {
    return "已中止";
  }
  if (status === "error") {
    return "失败";
  }
  return "空闲";
}

const SWEEP_RUN_MODE_OPTIONS = [
  { value: "trigger", label: "Trigger 单次扫频" },
  { value: "free", label: "Free 连续扫频" },
];

export default function MicrowavePage() {
  const { data, refresh, error, loading } = useDashboard(2000);
  const [form, setForm] = useState(null);
  const [isDirty, setIsDirty] = useState(false);
  const [triggerBusy, setTriggerBusy] = useState(false);
  const [localSweepElapsedS, setLocalSweepElapsedS] = useState(0);
  const hasHydratedRef = useRef(false);
  const sweepLocalStartMsRef = useRef(null);

  useEffect(() => {
    if (!data?.microwave?.config) {
      return;
    }
    if (!hasHydratedRef.current || !isDirty) {
      const config = data.microwave.config;
      setForm({
        ...config,
        sweep_step_hz: toFiniteNumber(config.sweep_step_hz, DEFAULT_SWEEP_STEP_HZ),
        sweep_run_mode: config.sweep_run_mode === "free" ? "free" : "trigger",
      });
      setIsDirty(false);
      hasHydratedRef.current = true;
    }
  }, [data, isDirty]);

  const sweepInfo = useMemo(() => {
    if (!form) {
      return { ok: false, error: "", points: 0, actualStepHz: 0 };
    }
    return computeSweepPoints(form.sweep_start_hz, form.sweep_stop_hz, form.sweep_step_hz);
  }, [form]);

  const updateForm = (changes) => {
    setIsDirty(true);
    setForm((prev) => ({ ...prev, ...changes }));
  };

  const sweepTrigger = data?.microwave?.sweep_trigger || {};
  const isFreeRunning = sweepTrigger.status === "free_running";
  const isSingleShotRunning =
    sweepTrigger.status === "running" || sweepTrigger.status === "cancelling";
  const sweepRunning =
    Boolean(sweepTrigger.running) || isSingleShotRunning || isFreeRunning;
  const sweepRunMode = form?.sweep_run_mode === "free" ? "free" : "trigger";

  useEffect(() => {
    if (!sweepRunning) {
      sweepLocalStartMsRef.current = null;
      if (Number.isFinite(Number(sweepTrigger.elapsed_s))) {
        setLocalSweepElapsedS(Number(sweepTrigger.elapsed_s));
      }
      return undefined;
    }
    if (sweepLocalStartMsRef.current == null) {
      const backendElapsedMs = toFiniteNumber(sweepTrigger.elapsed_s, 0) * 1000;
      sweepLocalStartMsRef.current = performance.now() - backendElapsedMs;
    }
    const tick = () => {
      const startMs = sweepLocalStartMsRef.current;
      if (startMs == null) {
        return;
      }
      setLocalSweepElapsedS((performance.now() - startMs) / 1000);
    };
    tick();
    const timerId = window.setInterval(tick, 100);
    const pollId = window.setInterval(() => {
      refresh();
    }, 500);
    return () => {
      window.clearInterval(timerId);
      window.clearInterval(pollId);
    };
  }, [sweepRunning, refresh, sweepTrigger.elapsed_s, sweepTrigger.status]);

  const save = async (nextForm = form, successMessage = null, { silent = false } = {}) => {
    if (!nextForm) {
      return { success: false, message: "表单为空" };
    }
    const computed = computeSweepPoints(
      nextForm.sweep_start_hz,
      nextForm.sweep_stop_hz,
      nextForm.sweep_step_hz
    );
    if (!computed.ok) {
      notifications.show({
        color: "red",
        title: "参数无效",
        message: computed.error,
      });
      return { success: false, message: computed.error };
    }

    const payload = {
      ...nextForm,
      sweep_step_hz: toFiniteNumber(nextForm.sweep_step_hz, DEFAULT_SWEEP_STEP_HZ),
      sweep_points: computed.points,
      sweep_run_mode: nextForm.sweep_run_mode === "free" ? "free" : "trigger",
    };

    try {
      const response = await api.saveMicrowave(payload);
      if (response?.success === false) {
        if (!silent) {
          notifications.show({
            color: "red",
            title: "同步失败",
            message: response.message || "未能将参数写入 Keysight 微波源",
          });
        }
        // Still refresh so UI shows backend-cached values (points already recomputed).
        if (response?.data?.config) {
          setForm({
            ...response.data.config,
            sweep_step_hz: toFiniteNumber(response.data.config.sweep_step_hz, DEFAULT_SWEEP_STEP_HZ),
            sweep_run_mode: response.data.config.sweep_run_mode === "free" ? "free" : "trigger",
          });
          setIsDirty(false);
        }
        await refresh();
        return { success: false, message: response.message || "同步失败", response };
      }

      const points = response?.data?.config?.sweep_points ?? computed.points;
      const stepHz = response?.data?.config?.sweep_step_hz ?? payload.sweep_step_hz;
      const runMode = payload.sweep_run_mode === "free" ? "Free 连续" : "Trigger 单次";
      const defaultSuccess =
        successMessage ||
        `已同步到 Keysight：${runMode}，扫频 ${points} 点，步进 ${formatStepHz(stepHz)}`;
      if (!silent) {
        notifications.show({ color: "teal", title: "应用成功", message: defaultSuccess });
      }
      setIsDirty(false);
      if (response?.data?.config) {
        setForm({
          ...response.data.config,
          sweep_step_hz: toFiniteNumber(response.data.config.sweep_step_hz, DEFAULT_SWEEP_STEP_HZ),
          sweep_run_mode: response.data.config.sweep_run_mode === "free" ? "free" : "trigger",
        });
      }
      await refresh();
      return { success: true, message: defaultSuccess, response };
    } catch (err) {
      const message = err instanceof Error ? err.message : "未知错误";
      if (!silent) {
        notifications.show({
          color: "red",
          title: "保存失败",
          message,
        });
      }
      return { success: false, message };
    }
  };

  const triggerSingleSweep = async () => {
    if (!form || !sweepInfo.ok) {
      return;
    }
    if (!data?.microwave?.connected) {
      notifications.show({
        color: "red",
        title: "未连接",
        message: "请先连接 Keysight 微波源",
      });
      return;
    }
    if (sweepRunMode === "free") {
      notifications.show({
        color: "yellow",
        title: "当前为 Free 模式",
        message: "请先切换到 Trigger 单次扫频并应用配置，或使用「中止扫频」后切换。",
      });
      return;
    }
    if (sweepRunning) {
      notifications.show({
        color: "yellow",
        title: "扫频进行中",
        message: isFreeRunning
          ? "Free 连续扫频运行中，请先中止"
          : "请等待当前单次扫频结束，或先中止",
      });
      return;
    }

    setTriggerBusy(true);
    try {
      let formToUse = form;
      if (isDirty || form.sweep_run_mode !== "trigger") {
        formToUse = { ...form, sweep_run_mode: "trigger" };
        const saved = await save(formToUse, null, { silent: true });
        if (!saved.success) {
          notifications.show({
            color: "red",
            title: "无法触发",
            message: saved.message || "请先成功应用当前配置",
          });
          return;
        }
      }

      const response = await api.triggerMicrowaveSweep();
      if (response?.success === false) {
        notifications.show({
          color: "red",
          title: "触发失败",
          message: response.message || "无法启动单次扫频",
        });
        await refresh();
        return;
      }
      sweepLocalStartMsRef.current = performance.now();
      setLocalSweepElapsedS(0);
      notifications.show({
        color: "teal",
        title: "已触发单次扫频",
        message: response.message || "仪器将扫一轮后自动停止",
      });
      await refresh();
    } catch (err) {
      notifications.show({
        color: "red",
        title: "触发失败",
        message: err instanceof Error ? err.message : "未知错误",
      });
    } finally {
      setTriggerBusy(false);
    }
  };

  const stopSingleSweep = async () => {
    setTriggerBusy(true);
    try {
      const response = await api.stopMicrowaveSweep();
      notifications.show({
        color: response?.success === false ? "red" : "yellow",
        title: response?.success === false ? "中止失败" : "已请求中止",
        message: response?.message || "",
      });
      await refresh();
    } catch (err) {
      notifications.show({
        color: "red",
        title: "中止失败",
        message: err instanceof Error ? err.message : "未知错误",
      });
    } finally {
      setTriggerBusy(false);
    }
  };

  const revertChanges = () => {
    if (!data?.microwave?.config) {
      return;
    }
    const config = data.microwave.config;
    setForm({
      ...config,
      sweep_step_hz: toFiniteNumber(config.sweep_step_hz, DEFAULT_SWEEP_STEP_HZ),
      sweep_run_mode: config.sweep_run_mode === "free" ? "free" : "trigger",
    });
    setIsDirty(false);
  };

  const reloadFromDevice = async () => {
    setIsDirty(false);
    await refresh();
    notifications.show({
      color: "teal",
      title: "已重载",
      message: "微波页参数已从后端状态重新同步",
    });
  };

  const setRfOutput = async (enabled) => {
    const nextForm = { ...form, output_enabled: enabled };
    setForm(nextForm);
    await save(nextForm, enabled ? "RF 输出已打开" : "RF 输出已关闭");
  };

  const applyAuxReferencePreset = () => {
    updateForm({
      fm_enabled: true,
      fm_source: "external",
      fm_rate_hz: 10000,
      lf_output_enabled: true,
      lf_output_source: "function1",
      lf_output_amplitude_v: Number(form.lf_output_amplitude_v ?? 1) || 1,
      lf_output_offset_v: 0,
      lf_output_load_ohm: 1000000,
    });
    notifications.show({
      color: "teal",
      title: "已填入实验预设",
      message: "已设置为 FM Source = Ext1，并从 LF OUT 输出 Function1 10 kHz 调制信号",
    });
  };

  if (!data || !form) {
    return (
      <Stack gap="md">
        <Text className="page-title">微波源模式与调制设置</Text>
        <Text c="dimmed">{error || (loading ? "正在加载微波源数据..." : "微波源数据为空")}</Text>
      </Stack>
    );
  }

  const pointsLabel = sweepInfo.ok ? String(sweepInfo.points) : "--";
  const stepHint = sweepInfo.ok
    ? `${pointsLabel} points | step ${formatStepHz(form.sweep_step_hz)} (实际 ${formatStepHz(sweepInfo.actualStepHz)}) | ${Number(form.dwell_ms).toFixed(1)} ms`
    : sweepInfo.error || "扫频参数无效";

  return (
    <Stack gap="lg">
      <div>
        <Text className="eyebrow">Step 3</Text>
        <Text className="page-title">微波源模式与调制设置</Text>
        <Text c="dimmed" maw={860}>
          扫频由起点、终点和步进（默认 10 kHz）决定，程序自动计算点数。点击「应用当前配置」会把参数同步到已连接的 Keysight 微波源。
        </Text>
      </div>

      <SimpleGrid cols={{ base: 1, md: 4 }}>
        <MetricCard
          label="微波地址"
          value={data.microwave.connected ? data.microwave.address : "未连接"}
          hint={data.microwave.idn || "等待连接"}
        />
        <MetricCard
          label="工作模式"
          value={
            form.mode === "cw"
              ? "定频"
              : sweepRunMode === "free"
                ? "扫频 · Free"
                : "扫频 · Trigger"
          }
          hint={form.output_enabled ? "RF 输出开启" : "RF 输出关闭"}
        />
        <MetricCard
          label="载波频率"
          value={formatGHz(form.mode === "cw" ? form.frequency_hz : form.center_frequency_hz)}
          hint={`${Number(form.power_dbm).toFixed(1)} dBm`}
        />
        <MetricCard
          label="扫频范围"
          value={`${formatGHz(form.sweep_start_hz)} - ${formatGHz(form.sweep_stop_hz)}`}
          hint={stepHint}
        />
        <MetricCard
          label="计算扫频点数"
          value={pointsLabel}
          hint={
            sweepInfo.ok
              ? `步进 ${formatStepHz(form.sweep_step_hz)} → 实际 ${formatStepHz(sweepInfo.actualStepHz)}`
              : sweepInfo.error || "—"
          }
        />
        <MetricCard
          label="LF OUT"
          value={form.lf_output_enabled ? "已开启" : "未开启"}
          hint={form.lf_output_source === "monitor" ? "跟随 FM Function1" : form.lf_output_source === "function1" ? "独立 Function1" : "DC"}
        />
      </SimpleGrid>

      <Grid gutter="lg">
        <Grid.Col span={{ base: 12, xl: 7 }}>
          <SectionCard
            title="基础模式"
            description="支持定频/扫频；扫频还可选 Trigger 单次或 Free 连续。输入起点/终点/步进，点数由程序计算；ODMR 页可复用这些参数。"
            badge={isDirty ? "有未保存修改" : "已同步"}
          >
            <SimpleGrid cols={{ base: 1, md: 2 }}>
              <Select
                label="模式"
                value={form.mode}
                onChange={(value) => updateForm({ mode: value || "sweep" })}
                data={[
                  { value: "sweep", label: "扫频" },
                  { value: "cw", label: "定频（备选）" },
                ]}
              />
              <Select
                label="扫频运行模式"
                description={
                  form.mode !== "sweep"
                    ? "仅在扫频模式下生效"
                    : sweepRunMode === "free"
                      ? "应用后仪器 INIT:CONT ON，循环扫频"
                      : "应用后武装单次扫频，需点 Trigger 启动一轮"
                }
                value={sweepRunMode}
                onChange={(value) => updateForm({ sweep_run_mode: value === "free" ? "free" : "trigger" })}
                data={SWEEP_RUN_MODE_OPTIONS}
                disabled={form.mode !== "sweep"}
              />
              <NumberInput label="功率 (dBm)" value={form.power_dbm} onChange={(value) => updateForm({ power_dbm: Number(value) || 0 })} />
              <NumberInput label="定频频率 (Hz)" value={form.frequency_hz} onChange={(value) => updateForm({ frequency_hz: Number(value) || 0 })} />
              <NumberInput label="中心频率 (Hz)" value={form.center_frequency_hz} onChange={(value) => updateForm({ center_frequency_hz: Number(value) || 0 })} />
              <NumberInput
                label="扫频起点 (Hz)"
                value={form.sweep_start_hz}
                onChange={(value) => updateForm({ sweep_start_hz: Number(value) || 0 })}
              />
              <NumberInput
                label="扫频终点 (Hz)"
                value={form.sweep_stop_hz}
                onChange={(value) => updateForm({ sweep_stop_hz: Number(value) || 0 })}
              />
              <NumberInput
                label="扫频步进 (Hz)"
                description="默认 10 kHz。点数 = round((终点-起点)/步进) + 1"
                value={form.sweep_step_hz ?? DEFAULT_SWEEP_STEP_HZ}
                min={1}
                step={1000}
                onChange={(value) =>
                  updateForm({ sweep_step_hz: Math.max(1, toFiniteNumber(value, DEFAULT_SWEEP_STEP_HZ)) })
                }
              />
              <NumberInput
                label="计算扫频点数"
                description={
                  sweepInfo.ok
                    ? `实际步进 ≈ ${formatStepHz(sweepInfo.actualStepHz)}`
                    : sweepInfo.error || "根据起点/终点/步进自动计算"
                }
                value={sweepInfo.ok ? sweepInfo.points : undefined}
                readOnly
                disabled
              />
              <NumberInput label="驻留时间 (ms)" value={form.dwell_ms} onChange={(value) => updateForm({ dwell_ms: Number(value) || 0 })} />
            </SimpleGrid>
            {!sweepInfo.ok && sweepInfo.error ? (
              <Text c="red" size="sm" mt="sm">
                {sweepInfo.error}
              </Text>
            ) : (
              <Text c="dimmed" size="sm" mt="sm">
                当前将采用 {pointsLabel} 个扫频点
                {sweepInfo.ok
                  ? `（请求步进 ${formatStepHz(form.sweep_step_hz)}，仪器等间隔实际步进 ${formatStepHz(sweepInfo.actualStepHz)}）`
                  : ""}
                。
                {form.mode === "sweep"
                  ? sweepRunMode === "free"
                    ? " 运行模式：Free 连续（应用配置后立即循环扫频）。"
                    : " 运行模式：Trigger 单次（应用后武装，需点「触发单次扫频」）。"
                  : ""}
              </Text>
            )}
          </SectionCard>
        </Grid.Col>

        <Grid.Col span={{ base: 12, xl: 5 }}>
          <SectionCard
            title="输出与调制"
            description="统一管理 RF、IQ、FM 和 LF OUT。要把 10 kHz 同时送去锁相 Aux In 1 并用于 FM，推荐用“跟随 FM 内部函数”。"
            badge="输出控制"
          >
            <Stack gap="md">
              <SimpleGrid cols={2}>
                <Switch checked={form.output_enabled} onChange={(event) => updateForm({ output_enabled: event.currentTarget.checked })} label="RF 输出" />
                <Switch checked={form.iq_enabled} onChange={(event) => updateForm({ iq_enabled: event.currentTarget.checked })} label="IQ 输出" />
                <Switch checked={form.fm_enabled} onChange={(event) => updateForm({ fm_enabled: event.currentTarget.checked })} label="FM 调制" />
                <Switch checked={form.lf_output_enabled} onChange={(event) => updateForm({ lf_output_enabled: event.currentTarget.checked })} label="LF OUT 输出" />
              </SimpleGrid>

              <Select
                label="FM 源"
                value={form.fm_source}
                onChange={(value) => updateForm({ fm_source: value || "external" })}
                data={[
                  { value: "internal", label: "内部" },
                  { value: "external", label: "外部" },
                ]}
              />
              <NumberInput
                label="FM 偏移 (Hz)"
                value={form.fm_deviation_hz}
                onChange={(value) => updateForm({ fm_deviation_hz: Number(value) || 0 })}
                disabled={!form.fm_enabled}
              />
              <NumberInput
                label="FM 速率 (Hz)"
                value={form.fm_rate_hz}
                onChange={(value) => updateForm({ fm_rate_hz: Number(value) || 0 })}
                disabled={!form.fm_enabled}
              />
              <Select
                label="LF OUT 源"
                value={form.lf_output_source}
                onChange={(value) => updateForm({ lf_output_source: value || "monitor" })}
                data={LF_OUTPUT_SOURCE_OPTIONS}
                disabled={!form.lf_output_enabled}
              />
              <NumberInput
                label="LF OUT 幅度 (V)"
                value={form.lf_output_amplitude_v}
                onChange={(value) => updateForm({ lf_output_amplitude_v: Number(value) || 0 })}
                disabled={!form.lf_output_enabled}
              />
              <NumberInput
                label="LF OUT 偏置 (V)"
                value={form.lf_output_offset_v}
                onChange={(value) => updateForm({ lf_output_offset_v: Number(value) || 0 })}
                disabled={!form.lf_output_enabled}
              />
              <Select
                label="LF OUT 负载"
                value={String(form.lf_output_load_ohm ?? 1000000)}
                onChange={(value) => updateForm({ lf_output_load_ohm: Number(value) || 1000000 })}
                data={LF_OUTPUT_LOAD_OPTIONS}
                disabled={!form.lf_output_enabled}
              />

              <Button variant="light" color="cyan" onClick={applyAuxReferencePreset}>
                一键设置 10 kHz FM + Aux1 参考输出
              </Button>

              <Group mt="sm">
                <Button onClick={() => save()} disabled={!sweepInfo.ok}>
                  应用当前配置
                </Button>
                <Button variant="light" color="gray" onClick={revertChanges} disabled={!isDirty}>
                  撤销修改
                </Button>
                <Button variant="light" color="cyan" onClick={reloadFromDevice}>
                  从设备重载
                </Button>
              </Group>
              <Group>
                <Button variant="light" color="teal" onClick={() => setRfOutput(true)} disabled={form.output_enabled || !sweepInfo.ok || sweepRunning}>
                  RF 打开
                </Button>
                <Button variant="light" color="red" onClick={() => setRfOutput(false)} disabled={!form.output_enabled || !sweepInfo.ok || sweepRunning}>
                  RF 关闭
                </Button>
              </Group>

              <Stack gap="xs" mt="md">
                <Text fw={600} size="sm">
                  仪器扫频控制
                </Text>
                <Text c="dimmed" size="sm">
                  {sweepRunMode === "free"
                    ? "Free 模式：点击「应用当前配置」后仪器连续循环扫频（INIT:CONT ON）。可用「中止扫频」停止。与 ODMR 软件逐点扫不同。"
                    : "Trigger 模式：应用配置后武装单次扫频；点「触发单次扫频」扫一轮后自动停止。有未保存修改时会先自动应用再触发。"}
                </Text>
                <Group>
                  <Button
                    color="cyan"
                    loading={triggerBusy && !sweepRunning}
                    disabled={
                      !data.microwave.connected ||
                      !sweepInfo.ok ||
                      sweepRunning ||
                      triggerBusy ||
                      form.mode !== "sweep" ||
                      sweepRunMode === "free"
                    }
                    onClick={triggerSingleSweep}
                  >
                    触发单次扫频
                  </Button>
                  <Button
                    color="red"
                    variant="light"
                    loading={triggerBusy && sweepRunning}
                    disabled={!sweepRunning || triggerBusy}
                    onClick={stopSingleSweep}
                  >
                    中止扫频
                  </Button>
                </Group>
                <SimpleGrid cols={{ base: 1, sm: 2 }}>
                  <MetricCard
                    label="扫频状态"
                    value={sweepTriggerStatusLabel(sweepTrigger.status)}
                    hint={
                      sweepTrigger.message ||
                      (data.microwave.connected
                        ? sweepRunMode === "free"
                          ? "应用配置以启动 Free 连续扫频"
                          : "等待触发"
                        : "未连接")
                    }
                  />
                  <MetricCard
                    label={isFreeRunning ? "已运行时长" : "已用 / 预计"}
                    value={
                      isFreeRunning
                        ? formatElapsedSeconds(localSweepElapsedS)
                        : `${formatElapsedSeconds(sweepRunning ? localSweepElapsedS : sweepTrigger.elapsed_s)} / ${formatElapsedSeconds(sweepTrigger.estimated_duration_s || (sweepInfo.ok ? sweepInfo.points * Math.min(Math.max(Number(form.dwell_ms) / 1000, 0.005), 1) + 0.2 : 0))}`
                    }
                    hint={
                      sweepInfo.ok
                        ? isFreeRunning
                          ? `连续循环 · ${sweepTrigger.points || sweepInfo.points} 点 × ${Number(form.dwell_ms).toFixed(1)} ms`
                          : `${sweepTrigger.points || sweepInfo.points} 点 × ${Number(form.dwell_ms).toFixed(1)} ms`
                        : "—"
                    }
                  />
                </SimpleGrid>
              </Stack>

              {!data.microwave.connected ? (
                <Text c="orange" size="sm">
                  微波源未连接：点击「应用当前配置」不会写入 Keysight，请先在设备页连接。
                </Text>
              ) : null}
            </Stack>
          </SectionCard>
        </Grid.Col>
      </Grid>
    </Stack>
  );
}
