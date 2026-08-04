import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Alert,
  Badge,
  Button,
  Code,
  Grid,
  Group,
  NumberInput,
  ScrollArea,
  Select,
  SimpleGrid,
  Stack,
  Table,
  Text,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import {
  IconDownload,
  IconInfoCircle,
  IconPlayerPlay,
  IconRefresh,
  IconTableExport,
} from "@tabler/icons-react";

import { MetricCard } from "../components/MetricCard";
import { SectionCard } from "../components/SectionCard";
import { api } from "../lib/api";

const DEFAULT_PARAMS = {
  kH_gs_per_a: 6.8,
  alpha_bus_per_exc: 150,
  gamma_hz_per_t: 28e9,
  In_a: 3000,
  max_exc_a: 15,
};

function fmt(value, digits = 4) {
  const n = Number(value);
  if (!Number.isFinite(n)) return "--";
  return n.toFixed(digits);
}

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

function DataTable({ rows, columns, empty = "暂无数据" }) {
  if (!rows?.length) {
    return (
      <Text c="dimmed" size="sm">
        {empty}
      </Text>
    );
  }
  return (
    <ScrollArea type="auto" offsetScrollbars>
      <Table striped highlightOnHover withTableBorder withColumnBorders stickyHeader>
        <Table.Thead>
          <Table.Tr>
            {columns.map((col) => (
              <Table.Th key={col.key}>{col.label}</Table.Th>
            ))}
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {rows.map((row, index) => (
            <Table.Tr key={index}>
              {columns.map((col) => (
                <Table.Td key={col.key}>
                  {col.render ? col.render(row) : String(row[col.key] ?? "")}
                </Table.Td>
              ))}
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </ScrollArea>
  );
}

export default function AccuracyPage() {
  const [params, setParams] = useState(DEFAULT_PARAMS);
  const [dfKhz, setDfKhz] = useState(50);
  const [quantity, setQuantity] = useState("delta_f");
  const [mode, setMode] = useState("theoretical");
  const [slope, setSlope] = useState(null);
  const [mapResult, setMapResult] = useState(null);
  const [comparisons, setComparisons] = useState([]);
  const [tables, setTables] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const payloadParams = useMemo(
    () => ({
      kH_gs_per_a: Number(params.kH_gs_per_a),
      alpha_bus_per_exc: Number(params.alpha_bus_per_exc),
      gamma_hz_per_t: Number(params.gamma_hz_per_t),
      In_a: Number(params.In_a),
      max_exc_a: Number(params.max_exc_a),
    }),
    [params]
  );

  const tablesPayload = useMemo(
    () => ({
      params: payloadParams,
      classes: ["0.2", "0.2S"],
      include_reference_classes: true,
    }),
    [payloadParams]
  );

  const setParam = (key) => (value) =>
    setParams((prev) => ({ ...prev, [key]: value === "" || value == null ? prev[key] : value }));

  const loadTables = useCallback(async () => {
    setBusy(true);
    setError("");
    try {
      const data = await api.accuracyTables(tablesPayload);
      setTables(data);
    } catch (err) {
      setError(err.message || String(err));
      notifications.show({
        color: "red",
        title: "加载标准表失败",
        message: err.message || String(err),
      });
    } finally {
      setBusy(false);
    }
  }, [tablesPayload]);

  useEffect(() => {
    loadTables();
  }, [loadTables]);

  const runMap = async () => {
    setBusy(true);
    setError("");
    try {
      const data = await api.accuracyMap({
        df_khz: Number(dfKhz),
        quantity,
        mode,
        slope_a_per_hz: mode === "empirical" ? Number(slope) : null,
        empirical_current_is_excitation: true,
        params: payloadParams,
        compare_standard: true,
      });
      setMapResult(data.result);
      setComparisons(data.standard_comparison || []);
      notifications.show({
        color: "teal",
        title: "映射完成",
        message: `δI_bus = ${fmt(data.result.delta_I_bus_a, 6)} A`,
      });
    } catch (err) {
      setError(err.message || String(err));
      notifications.show({
        color: "red",
        title: "映射失败",
        message: err.message || String(err),
      });
    } finally {
      setBusy(false);
    }
  };

  const exportOne = async (tableName) => {
    try {
      const { blob, filename } = await api.accuracyExportCsv(tableName, tablesPayload);
      downloadBlob(blob, filename);
      notifications.show({ color: "teal", title: "已下载", message: filename });
    } catch (err) {
      notifications.show({
        color: "red",
        title: "导出失败",
        message: err.message || String(err),
      });
    }
  };

  const exportAllDisk = async () => {
    try {
      const data = await api.accuracyExportAll(tablesPayload);
      notifications.show({
        color: "teal",
        title: "已写入磁盘",
        message: data.out_dir,
      });
    } catch (err) {
      notifications.show({
        color: "red",
        title: "写入失败",
        message: err.message || String(err),
      });
    }
  };

  const platform = tables?.platform;

  return (
    <Stack gap="lg">
      <SectionCard
        title="CT 准确度 / ODMR 频率映射"
        description="GB/T 20840.2 计量级 0.2 / 0.2S → 母线电流误差 → 塞曼 Δf / 单支 f± 容限。可在本页完成参数配置、δf→δI 换算、标准表查看与 CSV 导出。"
        badge="本地工具"
      >
        <Alert icon={<IconInfoCircle size={16} />} color="cyan" variant="light">
          默认：In=3000 A，1 A 激励 ≡ 6.8 Gs ≡ 150 A 母线，γ/2π=28 GHz/T。
          0–15 A 平台仅覆盖到约 75% In（2250 A），100%/120% 标准点不可在小源上直接验证。
        </Alert>
      </SectionCard>

      {error ? (
        <Alert color="red" title="错误">
          <Code block>{error}</Code>
        </Alert>
      ) : null}

      <Grid gutter="lg">
        <Grid.Col span={{ base: 12, lg: 5 }}>
          <SectionCard title="平台参数" description="修改后点“刷新标准表”或“计算映射”。">
            <SimpleGrid cols={2} spacing="md">
              <NumberInput label="In (A)" value={params.In_a} onChange={setParam("In_a")} min={1} decimalScale={1} />
              <NumberInput
                label="kH (Gs/A_exc)"
                value={params.kH_gs_per_a}
                onChange={setParam("kH_gs_per_a")}
                min={0.001}
                decimalScale={4}
              />
              <NumberInput
                label="α (A_bus / A_exc)"
                value={params.alpha_bus_per_exc}
                onChange={setParam("alpha_bus_per_exc")}
                min={0.001}
                decimalScale={3}
              />
              <NumberInput
                label="γ/2π (Hz/T)"
                value={params.gamma_hz_per_t}
                onChange={setParam("gamma_hz_per_t")}
                min={1}
                decimalScale={0}
              />
              <NumberInput
                label="最大激励 (A)"
                value={params.max_exc_a}
                onChange={setParam("max_exc_a")}
                min={0.1}
                decimalScale={2}
              />
            </SimpleGrid>
            <Group mt="md">
              <Button leftSection={<IconRefresh size={16} />} loading={busy} onClick={loadTables}>
                刷新标准表
              </Button>
              <Button
                variant="light"
                leftSection={<IconTableExport size={16} />}
                onClick={exportAllDisk}
              >
                写入 data/standards
              </Button>
            </Group>
          </SectionCard>
        </Grid.Col>

        <Grid.Col span={{ base: 12, lg: 7 }}>
          <SectionCard
            title="频率偏差 → 电流误差"
            description="输入闭环锁定后的频率偏差（kHz），换算母线/激励电流误差，并对照 0.2 / 0.2S 限值。"
          >
            <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="md">
              <NumberInput
                label="频率偏差 δf (kHz)"
                value={dfKhz}
                onChange={(v) => setDfKhz(v === "" || v == null ? 0 : v)}
                min={0}
                decimalScale={6}
              />
              <Select
                label="频率量"
                value={quantity}
                onChange={(v) => setQuantity(v || "delta_f")}
                data={[
                  { value: "delta_f", label: "劈裂 Δf = f+ − f−" },
                  { value: "branch", label: "单支 f± 锁定" },
                ]}
              />
              <Select
                label="映射模式"
                value={mode}
                onChange={(v) => setMode(v || "theoretical")}
                data={[
                  { value: "theoretical", label: "理论 (Helmholtz + Zeeman)" },
                  { value: "empirical", label: "经验 I = a·Δf + b" },
                ]}
              />
              <NumberInput
                label="经验斜率 a (A/Hz)"
                description="经验模式必填；标定电流默认为激励电流"
                value={slope}
                onChange={setSlope}
                disabled={mode !== "empirical"}
                decimalScale={12}
                placeholder="例如 2.6e-8"
              />
            </SimpleGrid>
            <Group mt="md">
              <Button
                leftSection={<IconPlayerPlay size={16} />}
                loading={busy}
                onClick={runMap}
              >
                计算映射
              </Button>
            </Group>

            {mapResult ? (
              <SimpleGrid cols={{ base: 1, sm: 3 }} mt="lg">
                <MetricCard
                  label="δI 母线"
                  value={`${fmt(mapResult.delta_I_bus_a, 6)} A`}
                  hint={mapResult.notes}
                />
                <MetricCard
                  label="δI 激励"
                  value={`${fmt(mapResult.delta_I_exc_a, 6)} A`}
                  hint={`灵敏度 ${fmt(mapResult.sensitivity_khz_per_a_bus, 3)} kHz/A_bus`}
                />
                <MetricCard
                  label="输入 δf"
                  value={`${fmt(mapResult.delta_f_khz, 3)} kHz`}
                  hint={`${mapResult.quantity} / ${mapResult.mode}`}
                />
              </SimpleGrid>
            ) : null}
          </SectionCard>
        </Grid.Col>
      </Grid>

      {platform ? (
        <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }}>
          <MetricCard
            label="d(Δf)/dI_bus"
            value={`${fmt(platform.d_delta_f_dI_bus_khz_per_a, 3)} kHz/A`}
          />
          <MetricCard
            label="d(f±)/dI_bus"
            value={`${fmt(platform.d_branch_f_dI_bus_khz_per_a, 3)} kHz/A`}
          />
          <MetricCard
            label="平台最大母线"
            value={`${fmt(platform.max_bus_a, 1)} A`}
            hint={`${fmt(platform.max_bus_percent_In, 1)} % In`}
          />
          <MetricCard
            label="0.2% 几何俯仰上界"
            value={`${fmt(tables.pitch_angle_0_2_percent_deg, 2)} °`}
            hint="1−cosθ 模型"
          />
        </SimpleGrid>
      ) : null}

      {comparisons.length ? (
        <SectionCard title="与 GB/T 20840.2 绝对误差限对比" badge="0.2 / 0.2S">
          <DataTable
            rows={comparisons}
            columns={[
              { key: "accuracy_class", label: "等级" },
              {
                key: "I_percent_In",
                label: "%In",
                render: (r) => fmt(r.I_percent_In, 1),
              },
              {
                key: "I_bus_a",
                label: "I_bus (A)",
                render: (r) => fmt(r.I_bus_a, 1),
              },
              {
                key: "abs_error_limit_a",
                label: "限值 ±A",
                render: (r) => fmt(r.abs_error_limit_a, 4),
              },
              {
                key: "delta_I_bus_a",
                label: "本次 δI (A)",
                render: (r) => fmt(r.delta_I_bus_a, 6),
              },
              {
                key: "margin_a",
                label: "裕度 (A)",
                render: (r) => fmt(r.margin_a, 6),
              },
              {
                key: "within_limit",
                label: "判定",
                render: (r) => (
                  <Badge color={r.within_limit ? "teal" : "red"}>
                    {r.within_limit ? "OK" : "FAIL"}
                  </Badge>
                ),
              },
              {
                key: "reachable_on_platform",
                label: "0–15A 可达",
                render: (r) => (r.reachable_on_platform ? "Y" : "N"),
              },
            ]}
          />
        </SectionCard>
      ) : null}

      <SectionCard
        title="分段准确度与频率容限表"
        description="主用 0.2 / 0.2S；比值差表附带参考等级。可下载单表 CSV。"
      >
        <Group mb="md" gap="sm">
          <Button
            size="xs"
            variant="light"
            leftSection={<IconDownload size={14} />}
            onClick={() => exportOne("ratio_error_limits")}
          >
            比值差 CSV
          </Button>
          <Button
            size="xs"
            variant="light"
            leftSection={<IconDownload size={14} />}
            onClick={() => exportOne("abs_current_error")}
          >
            绝对电流误差 CSV
          </Button>
          <Button
            size="xs"
            variant="light"
            leftSection={<IconDownload size={14} />}
            onClick={() => exportOne("freq_tolerance")}
          >
            频率容限 CSV
          </Button>
          <Button
            size="xs"
            variant="light"
            leftSection={<IconDownload size={14} />}
            onClick={() => exportOne("pitch_angle_budget")}
          >
            俯仰预算 CSV
          </Button>
          <Button
            size="xs"
            variant="light"
            leftSection={<IconDownload size={14} />}
            onClick={() => exportOne("platform_exc_points")}
          >
            激励点 CSV
          </Button>
        </Group>

        <Stack gap="xl">
          <div>
            <Text fw={700} mb="sm">
              允许绝对电流误差（In 相关）
            </Text>
            <DataTable
              rows={tables?.abs_current_error}
              columns={[
                { key: "accuracy_class", label: "等级" },
                { key: "I_percent_In", label: "%In", render: (r) => fmt(r.I_percent_In, 1) },
                { key: "I_bus_a", label: "I_bus (A)", render: (r) => fmt(r.I_bus_a, 1) },
                {
                  key: "ratio_error_pm_percent",
                  label: "比值差 ±%",
                  render: (r) => fmt(r.ratio_error_pm_percent, 2),
                },
                {
                  key: "abs_error_pm_a",
                  label: "δI ±A",
                  render: (r) => fmt(r.abs_error_pm_a, 4),
                },
                {
                  key: "I_exc_equivalent_a",
                  label: "I_exc (A)",
                  render: (r) => fmt(r.I_exc_equivalent_a, 3),
                },
                {
                  key: "reachable_on_0_15A_platform",
                  label: "可达",
                  render: (r) => (r.reachable_on_0_15A_platform ? "Y" : "N"),
                },
              ]}
            />
          </div>

          <div>
            <Text fw={700} mb="sm">
              频率锁定容限（理论链）
            </Text>
            <DataTable
              rows={tables?.freq_tolerance}
              columns={[
                { key: "accuracy_class", label: "等级" },
                { key: "I_percent_In", label: "%In", render: (r) => fmt(r.I_percent_In, 1) },
                { key: "I_bus_a", label: "I_bus (A)", render: (r) => fmt(r.I_bus_a, 1) },
                {
                  key: "abs_error_pm_a",
                  label: "δI ±A",
                  render: (r) => fmt(r.abs_error_pm_a, 4),
                },
                {
                  key: "delta_f_tol_khz",
                  label: "δ(Δf) kHz",
                  render: (r) => fmt(r.delta_f_tol_khz, 3),
                },
                {
                  key: "branch_f_tol_khz",
                  label: "δf± kHz",
                  render: (r) => fmt(r.branch_f_tol_khz, 3),
                },
                {
                  key: "independent_rss_two_branch_khz",
                  label: "双支 RSS kHz",
                  render: (r) => fmt(r.independent_rss_two_branch_khz, 3),
                },
              ]}
            />
          </div>

          <div>
            <Text fw={700} mb="sm">
              俯仰角几何预算（1−cosθ）与推荐细扫 0.1°
            </Text>
            <DataTable
              rows={tables?.pitch_angle_budget}
              columns={[
                { key: "accuracy_class", label: "等级" },
                { key: "I_percent_In", label: "%In", render: (r) => fmt(r.I_percent_In, 1) },
                {
                  key: "ratio_error_pm_percent",
                  label: "比值差 ±%",
                  render: (r) => fmt(r.ratio_error_pm_percent, 2),
                },
                {
                  key: "max_pitch_angle_deg_1_minus_cos",
                  label: "最大 |θ| (°)",
                  render: (r) => fmt(r.max_pitch_angle_deg_1_minus_cos, 3),
                },
                {
                  key: "recommended_fine_step_deg",
                  label: "细扫步长 (°)",
                  render: (r) => fmt(r.recommended_fine_step_deg, 2),
                },
                { key: "note", label: "备注" },
              ]}
            />
          </div>

          <div>
            <Text fw={700} mb="sm">
              比值差限值（含参考等级）
            </Text>
            <DataTable
              rows={tables?.ratio_error_limits}
              columns={[
                { key: "accuracy_class", label: "等级" },
                { key: "I_percent_In", label: "%In", render: (r) => fmt(r.I_percent_In, 1) },
                {
                  key: "ratio_error_pm_percent",
                  label: "比值差 ±%",
                  render: (r) => fmt(r.ratio_error_pm_percent, 2),
                },
                {
                  key: "phase_error_pm_min",
                  label: "相位差 ±′",
                  render: (r) =>
                    r.phase_error_pm_min == null ? "--" : fmt(r.phase_error_pm_min, 1),
                },
                { key: "note", label: "备注" },
              ]}
            />
          </div>
        </Stack>
      </SectionCard>
    </Stack>
  );
}
