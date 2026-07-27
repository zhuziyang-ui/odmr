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

const DEFAULT_SWEEP_STEP_HZ = 10_000;
const MAX_SWEEP_POINTS = 100_001;

/** 由起止与步进计算扫频点数：N = round((stop-start)/step) + 1 */
function computeSweepPoints(startHz, stopHz, stepHz) {
  const start = Number(startHz);
  const stop = Number(stopHz);
  const step = Number(stepHz);
  if (!Number.isFinite(start) || !Number.isFinite(stop) || !Number.isFinite(step)) {
    return { points: null, effectiveStepHz: null, error: "频率或步进无效" };
  }
  if (!(stop > start)) {
    return { points: null, effectiveStepHz: null, error: "终点必须大于起点" };
  }
  if (!(step > 0)) {
    return { points: null, effectiveStepHz: null, error: "步进必须大于 0" };
  }
  const span = stop - start;
  let points = Math.round(span / step) + 1;
  if (points < 2) {
    points = 2;
  }
  if (points > MAX_SWEEP_POINTS) {
    return {
      points: null,
      effectiveStepHz: null,
      error: `点数 ${points} 超过上限 ${MAX_SWEEP_POINTS}，请增大步进`,
    };
  }
  return {
    points,
    effectiveStepHz: span / (points - 1),
    error: null,
  };
}

function deriveStepFromConfig(config) {
  if (!config) {
    return DEFAULT_SWEEP_STEP_HZ;
  }
  const explicit = Number(config.sweep_step_hz);
  if (Number.isFinite(explicit) && explicit > 0) {
    return explicit;
  }
  const start = Number(config.sweep_start_hz);
  const stop = Number(config.sweep_stop_hz);
  const points = Number(config.sweep_points);
  if (Number.isFinite(start) && Number.isFinite(stop) && stop > start && points > 1) {
    return (stop - start) / (points - 1);
  }
  return DEFAULT_SWEEP_STEP_HZ;
}

function normalizeMicrowaveForm(config) {
  if (!config) {
    return null;
  }
  const sweep_step_hz = deriveStepFromConfig(config);
  const computed = computeSweepPoints(
    config.sweep_start_hz,
    config.sweep_stop_hz,
    sweep_step_hz
  );
  return {
    ...config,
    sweep_step_hz,
    sweep_points: computed.points ?? config.sweep_points ?? 2,
  };
}

function formatStepHz(stepHz) {
  const value = Number(stepHz);
  if (!Number.isFinite(value)) {
    return "--";
  }
  if (Math.abs(value) >= 1e6) {
    return `${(value / 1e6).toFixed(3)} MHz`;
  }
  if (Math.abs(value) >= 1e3) {
    return `${(value / 1e3).toFixed(3)} kHz`;
  }
  return `${value.toFixed(1)} Hz`;
}

export default function MicrowavePage() {
  const { data, refresh, error, loading } = useDashboard(2000);
  const [form, setForm] = useState(null);
  const [isDirty, setIsDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const hasHydratedRef = useRef(false);

  useEffect(() => {
    if (!data?.microwave?.config) {
      return;
    }
    if (!hasHydratedRef.current || !isDirty) {
      setForm(normalizeMicrowaveForm(data.microwave.config));
      setIsDirty(false);
      hasHydratedRef.current = true;
    }
  }, [data, isDirty]);

  const sweepCalc = useMemo(() => {
    if (!form) {
      return { points: null, effectiveStepHz: null, error: null };
    }
    return computeSweepPoints(form.sweep_start_hz, form.sweep_stop_hz, form.sweep_step_hz);
  }, [form]);

  const updateForm = (changes) => {
    setIsDirty(true);
    setForm((prev) => {
      const next = { ...prev, ...changes };
      const calc = computeSweepPoints(
        next.sweep_start_hz,
        next.sweep_stop_hz,
        next.sweep_step_hz
      );
      if (calc.points != null) {
        next.sweep_points = calc.points;
        next.center_frequency_hz =
          0.5 * (Number(next.sweep_start_hz) + Number(next.sweep_stop_hz));
      }
      return next;
    });
  };

  const save = async (nextForm = form, successMessage = "微波参数已保存") => {
    if (!nextForm) {
      return;
    }
    const calc = computeSweepPoints(
      nextForm.sweep_start_hz,
      nextForm.sweep_stop_hz,
      nextForm.sweep_step_hz
    );
    if (calc.error) {
      notifications.show({
        color: "red",
        title: "扫频参数无效",
        message: calc.error,
      });
      return;
    }
    const payload = {
      ...nextForm,
      sweep_points: calc.points,
      center_frequency_hz:
        0.5 * (Number(nextForm.sweep_start_hz) + Number(nextForm.sweep_stop_hz)),
    };
    setSaving(true);
    try {
      const result = await api.saveMicrowave(payload);
      const serverMessage =
        result?.message ||
        (data?.microwave?.connected
          ? "已下发到 Keysight 微波源"
          : "已保存到后端（微波源未连接）");
      notifications.show({
        color: "teal",
        title: successMessage,
        message: `${serverMessage}${
          payload.mode === "sweep"
            ? ` | 点数 ${calc.points} | 步进 ${formatStepHz(payload.sweep_step_hz)}`
            : ""
        }`,
      });
      setIsDirty(false);
      await refresh();
    } catch (err) {
      notifications.show({
        color: "red",
        title: "保存失败",
        message: err instanceof Error ? err.message : "未知错误",
      });
    } finally {
      setSaving(false);
    }
  };

  const revertChanges = () => {
    if (!data?.microwave?.config) {
      return;
    }
    setForm(normalizeMicrowaveForm(data.microwave.config));
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

  const connected = Boolean(data.microwave?.connected);

  return (
    <Stack gap="lg">
      <div>
        <Text className="eyebrow">Step 3</Text>
        <Text className="page-title">微波源模式与调制设置</Text>
        <Text c="dimmed" maw={860}>
          扫频：填写起点、终点与步进，程序自动计算点数。点击「应用当前配置」会保存到后端；
          已连接时通过 SCPI 同步到 Keysight（:FREQ:STAR / :FREQ:STOP / :SWE:POIN）。
        </Text>
      </div>

      <SimpleGrid cols={{ base: 1, md: 4 }}>
        <MetricCard
          label="微波地址"
          value={connected ? data.microwave.address : "未连接"}
          hint={data.microwave.idn || "等待连接"}
        />
        <MetricCard
          label="工作模式"
          value={form.mode === "cw" ? "定频" : "扫频"}
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
          hint={
            sweepCalc.points != null
              ? `${sweepCalc.points} 点 | 步进 ${formatStepHz(form.sweep_step_hz)} | dwell ${Number(form.dwell_ms).toFixed(1)} ms`
              : sweepCalc.error || "参数无效"
          }
        />
        <MetricCard
          label="LF OUT"
          value={form.lf_output_enabled ? "已开启" : "未开启"}
          hint={
            form.lf_output_source === "monitor"
              ? "跟随 FM Function1"
              : form.lf_output_source === "function1"
                ? "独立 Function1"
                : "DC"
          }
        />
      </SimpleGrid>

      <Grid gutter="lg">
        <Grid.Col span={{ base: 12, xl: 7 }}>
          <SectionCard
            title="基础模式"
            description="扫频：起点 + 终点 + 步进 → 自动算点数并下发 Keysight。定频时只写 :FREQ。"
            badge={isDirty ? "有未保存修改" : connected ? "已连接" : "未连接"}
          >
            <SimpleGrid cols={{ base: 1, md: 2 }}>
              <Select
                label="模式"
                value={form.mode}
                onChange={(value) => updateForm({ mode: value || "sweep" })}
                data={[
                  { value: "cw", label: "定频" },
                  { value: "sweep", label: "扫频" },
                ]}
              />
              <NumberInput
                label="功率 (dBm)"
                value={form.power_dbm}
                onChange={(value) => updateForm({ power_dbm: Number(value) || 0 })}
              />
              <NumberInput
                label="定频频率 (Hz)"
                value={form.frequency_hz}
                onChange={(value) => updateForm({ frequency_hz: Number(value) || 0 })}
                disabled={form.mode !== "cw"}
              />
              <NumberInput
                label="中心频率 (Hz)"
                description="扫频模式下由起止自动取中点"
                value={form.center_frequency_hz}
                onChange={(value) => updateForm({ center_frequency_hz: Number(value) || 0 })}
                disabled={form.mode === "sweep"}
              />
              <NumberInput
                label="扫频起点 (Hz)"
                value={form.sweep_start_hz}
                onChange={(value) => updateForm({ sweep_start_hz: Number(value) || 0 })}
                disabled={form.mode !== "sweep"}
              />
              <NumberInput
                label="扫频终点 (Hz)"
                value={form.sweep_stop_hz}
                onChange={(value) => updateForm({ sweep_stop_hz: Number(value) || 0 })}
                disabled={form.mode !== "sweep"}
              />
              <NumberInput
                label="扫频步进 δf (Hz)"
                description="可调；默认 10000（10 kHz）"
                value={form.sweep_step_hz}
                min={1}
                step={1000}
                onChange={(value) =>
                  updateForm({ sweep_step_hz: Number(value) > 0 ? Number(value) : DEFAULT_SWEEP_STEP_HZ })
                }
                disabled={form.mode !== "sweep"}
              />
              <NumberInput
                label="扫频点数（自动计算）"
                description={
                  sweepCalc.error
                    ? sweepCalc.error
                    : sweepCalc.effectiveStepHz != null
                      ? `仪器有效步进 ≈ ${formatStepHz(sweepCalc.effectiveStepHz)}`
                      : "N = round((终点−起点)/步进) + 1"
                }
                value={sweepCalc.points ?? form.sweep_points}
                readOnly
                disabled
              />
              <NumberInput
                label="驻留时间 (ms)"
                value={form.dwell_ms}
                onChange={(value) => updateForm({ dwell_ms: Number(value) || 0 })}
                disabled={form.mode !== "sweep"}
              />
            </SimpleGrid>

            {form.mode === "sweep" && (
              <Text size="sm" c={sweepCalc.error ? "red" : "dimmed"} mt="md">
                {sweepCalc.error
                  ? `无法计算点数：${sweepCalc.error}`
                  : `计算结果：${sweepCalc.points} 点 | 请求步进 ${formatStepHz(form.sweep_step_hz)} | 有效步进 ${formatStepHz(sweepCalc.effectiveStepHz)} | 跨度 ${formatGHz(form.sweep_stop_hz - form.sweep_start_hz)}`}
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
                <Switch
                  checked={form.output_enabled}
                  onChange={(event) => updateForm({ output_enabled: event.currentTarget.checked })}
                  label="RF 输出"
                />
                <Switch
                  checked={form.iq_enabled}
                  onChange={(event) => updateForm({ iq_enabled: event.currentTarget.checked })}
                  label="IQ 输出"
                />
                <Switch
                  checked={form.fm_enabled}
                  onChange={(event) => updateForm({ fm_enabled: event.currentTarget.checked })}
                  label="FM 调制"
                />
                <Switch
                  checked={form.lf_output_enabled}
                  onChange={(event) => updateForm({ lf_output_enabled: event.currentTarget.checked })}
                  label="LF OUT 输出"
                />
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
                <Button
                  onClick={() => save()}
                  loading={saving}
                  disabled={form.mode === "sweep" && Boolean(sweepCalc.error)}
                >
                  {connected ? "应用配置并同步到 Keysight" : "应用当前配置"}
                </Button>
                <Button variant="light" color="gray" onClick={revertChanges} disabled={!isDirty}>
                  撤销修改
                </Button>
                <Button variant="light" color="cyan" onClick={reloadFromDevice}>
                  从设备重载
                </Button>
              </Group>
              {!connected && (
                <Text size="sm" c="orange">
                  微波源未连接：点击应用只会写入后端状态。请先在设备页连接 Keysight，再点应用以同步 STAR/STOP/POIN。
                </Text>
              )}
              <Group>
                <Button
                  variant="light"
                  color="teal"
                  onClick={() => setRfOutput(true)}
                  disabled={form.output_enabled || saving}
                >
                  RF 打开
                </Button>
                <Button
                  variant="light"
                  color="red"
                  onClick={() => setRfOutput(false)}
                  disabled={!form.output_enabled || saving}
                >
                  RF 关闭
                </Button>
              </Group>
            </Stack>
          </SectionCard>
        </Grid.Col>
      </Grid>
    </Stack>
  );
}
