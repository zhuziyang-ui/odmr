# 双峰跟踪同步电流测量 — 仓库深度研究报告

**仓库**：`odmr_repo`（NV Measurement Console / cw-30）  
**日期**：2026-07-25  
**说明**：本报告由本地代码与文档审计完成。Grok `deep-research` 工作流在 WPS 云盘中文路径下三次因 `scratch atomic persist` 落盘失败；报告正文落在桌面 ASCII 路径以便后续引用与版本管理。

---

## 1. 目标 vs 仓库现状

| 目标 | 仓库实现 | 状态 |
| --- | --- | --- |
| 记录 \(f_-\) / \(f_+\)（低频支 / 高频支） | `f_left_hz` / `f_right_hz`，CSV 与 WebSocket 实时输出 | **已实现** |
| \(\Delta f = f_+ - f_-\) | 时间对齐后 `delta_f_hz` | **已实现** |
| 实时闭环跟踪激励电流变化 | 左右独立受限 PID + 速度外推；激励在亥姆霍兹产生磁场 → 峰移动 | **已实现（微波频率闭环，非激励源闭环）** |
| \(I = a\Delta f + b\) 换算 | 前端物理峰心标定 → 后端加载斜率/截距 | **已实现** |
| 1 s 聚合长时记录 | `CurrentTrackingRecorder` → `data/current_tracking/` | **已实现** |
| EKF/UKF 联合估计 | 独立页 `/state-estimation`，与 PID 路径隔离 | **已实现（另一条算法线）** |
| GB 0.2/0.2S 频率容限 | `/accuracy` + `docs/ct_accuracy_odmr_mapping.md` | **已实现（离线映射）** |
| 激励源（电流源）自动闭环 | 无：只测量激励导致的磁场/电流，不控电流源 | **未实现** |
| 后端无人值守 + 断线重连 | WebSocket 绑会话，关页即停 | **明确缺口** |

**概念澄清：**  
这里的「闭环」是 **微波频率跟踪 ODMR 双峰** 的闭环，不是「电流源 → 电流设定」的闭环。亥姆霍兹激励电流是**被测对象**；探头感受 \(B_\parallel\)，通过 \(\Delta f\) 推回电流。

代码中左右峰命名为 **left/right**，对应物理上的 **\(f_-\)/\(f_+\)**（频率较低/较高的一支）。

---

## 2. 物理链路

与 `docs/ct_accuracy_odmr_mapping.md` 一致：

```text
激励电流 I_exc ──► 一维亥姆霍兹线圈 B ──► NV 探头 B∥
                                              │
                                    Δf = f+ − f− ≈ 2γ B∥
                                              │
                         经验标定  I = a·Δf + b  （或理论 γ/kH）
                                              │
                                    I_bus = α · I_exc（平台几何）
```

文档默认工程量级：

| 参数 | 值 |
| --- | ---: |
| In | 3000 A |
| 1 A 激励 → 中心磁场 | 6.8 Gs |
| 1 A 激励 ≈ 母线 | 150 A |
| γ/2π | 28 GHz/T = 2.8 MHz/G |
| 理论 \(d(\Delta f)/dI_{\mathrm{exc}}\) | ≈ 38.08 MHz/A |
| 实测常见 | 1 A 时 Δf ≈ 23 MHz（低于理论） |

→ **必须用物理标定**，不能只靠理论灵敏度。

0.2S @ 1%In 粗算：\(\delta(\Delta f)\lesssim 57\,\mathrm{kHz}\)。对闭环噪声、时间对齐与锁相时间常数要求极苛刻。

---

## 3. 架构总览

```text
Frontend /current
  CurrentPage + CurrentTrackingPanel
        │
        ▼
WebSocket /api/measurement/...
        │
        ▼
InstrumentManager.run_current_tracking
   ├─ dual_peak_tracker.py   FM 谷识别 · 复数 b/g · PID · 时间对齐
   ├─ Microwave VISA :FREQ
   ├─ Lock-in X/Y/R
   └─ CurrentTrackingRecorder  1s 聚合 CSV/Excel

独立路径（不调用 PID）：
  /state-estimation → state_estimation_tracking + JointPeakStateEstimator (EKF/UKF)
```

| 层 | 路径 | 职责 |
| --- | --- | --- |
| 算法核 | `backend/app/services/dual_peak_tracker.py` | 峰识别、鉴频、PID、运动估计、Δf/电流 |
| 运行时 | `instrument_manager.run_current_tracking` | 扫频/标定/交替访问/失锁重捕获/仪器 I/O |
| 记录 | `current_tracking_recorder.py` | 1 s 聚合、`fL/fR/Δf/I`、状态、质量 |
| 滤波线 | `joint_peak_estimator.py` + `state_estimation_tracking.py` | 13 维 EKF/UKF，**不调用** PID 跟踪 |
| 计量 | `accuracy_mapping.py` + `data/standards/*` | GB 比值差 → 频率容限 |
| 前端 | `CurrentPage.jsx` | 标定 \(I=a\Delta f+b\)（localStorage）、启动跟踪、曲线 |
| 测试 | `test_dual_peak_tracker.py`, `test_current_tracking*.py` | 算法 + 仿真闭环 |

两套测量算法 **刻意隔离**（README）：PID 路径有 1 s 记录器；状态估计页只保留约 600 点实时图，不复用长时记录。

---

## 4. 数据流：从激励变化到 \(f_\pm\) 与电流

### 4.1 启动阶段

1. **FULL_SCAN**：`start_hz` → `stop_hz` 步进扫频，读锁相 X/Y；R 作峰存在性代理（或独立 DC 通道）。
2. **FM 双瓣谷识别** `find_fm_magnitude_resonances`  
   - 一次谐波 FM：\(R \approx |dS/df|\) → 单共振 = **左瓣–中央谷–右瓣**  
   - 复数斜率相位筛掉「两峰之间的假谷」。
3. **选唯一峰对** `select_fm_resonance_pair`（Δf 物理窗、评分歧义比、斜率相位差）。
4. **CALIBRATE**：每峰局部扫，拟合复数仿射模型  
   \[
   Z = X+jY = b + g(f_{\mathrm{cmd}}-f_p)+v
   \]
5. **TRACK**：左右交替写微波频率 → settle → 读 X/Y → 鉴频 → PID 更新指令频率。

### 4.2 闭环单峰访问（核心）

对某一峰 `visit_peak`：

1. 周期性 **斜率验证**（两侧 probe），失败则 SUSPECT。  
2. `acquire_at`：快速写频 + 等待 + 中位数平均。  
3. `calculate_frequency_error`：沿 \(g\) 投影得频偏 \(e\)，正交残差 \(q\)。  
4. 质量状态机：LOCKED / SUSPECT / LOCAL_REACQUIRE / LOST。  
5. `MotionEstimate` 更新中心与速度。  
6. `SpecPidController`：捕获窗、硬件窗、身份边界（中点 ± guard）、步进/slew、抗饱和。  
7. 周期末 `calculate_aligned_output`：把左右外推到**同一时刻**再算 Δf。

### 4.3 电流与记录字段

\[
I = a\cdot\Delta f + b,\quad
\sigma_I \approx |a|\,\sigma_{\Delta f}
\]

**无效条件（不外推）：**

- 双侧未 LOCKED  
- 峰身份交叉  
- Δf 出物理窗 / 出标定窗  
- 外推超时或 \(\sigma_{\Delta f}\) 过大  
- 标定系数缺失  

**记录器列（与「记 \(f_\pm\)」直接对应）：**

| CSV 列 | 含义 |
| --- | --- |
| `f_left_hz` / `f_right_hz` | \(f_-\) / \(f_+\) |
| `delta_f_hz` | 劈裂 |
| `common_mode_hz` | 共模（温漂/共模场诊断） |
| `current_a` + std/σ | 电流及不确定度 |
| `left_state` / `right_state` | 锁定状态 |
| `valid_fraction` / `invalid_reason` | 该秒有效性 |
| `relock_count` / `lost_lock_count` | 失锁统计 |
| `measured_update_rate_hz` | 实测双峰周期更新率 |

落盘路径（相对仓库）：

```text
data/current_tracking/<session_id>[_label]/
  current_tracking_data.csv   # 恢复源，逐行 flush
  metadata.json               # 参数与设备快照，原子替换
  current_tracking_*.xlsx     # Summary / Data / Parameters
```

---

## 5. 与「同步电流测量」相关的关键设计

### 5.1 为何需要时间对齐

左右峰是 **顺序采样**，不是同时。电流变化时若直接 \(f_R(t_2)-f_L(t_1)\) 会有一阶时间偏斜。  
`MotionEstimate.predict` + `calculate_aligned_output` 用速度外推到共同时间戳——这是软件「同步」，不是双通道硬件同步。

对 **快速变化的亥姆霍兹激励**，必须认真设置：

- `maximum_velocity_hz_per_s` / `maximum_acceleration_hz_per_s2`
- `maximum_extrapolation_age_s`
- 实测双峰周期 \(T_u\)（页面 timing 报告）

否则会出现：Δf 尖峰而单峰曲线却「看起来正常」（README 已说明）。

### 5.2 鉴频为何用复数投影

旧方案（过零 / R 极小）被请求模型拒绝；默认 `tracking_target="complex_projection"`。  
FM 1f 下物理峰心在 R 谷，跟踪用 \(g\) 方向投影更抗相位与背景，正交残差可做假锁检测。

### 5.3 标定在前端、系数在后端

- 前端 `CurrentPage`：`I = a*(fR-fL)+b`，点源 `physical_peak_tracking`，存 localStorage v3。  
- 至少 2 个不同电流点；运行中新增点需 **停再启** 才加载新系数。  
- 与平台经验 Δf–I 投影不足（23 vs 38 MHz/A）匹配。

### 5.4 两条算法线怎么选

| | PID `/current` | EKF/UKF `/state-estimation` |
| --- | --- | --- |
| 成熟度 / 记录 | 长时 CSV/Excel、调参文档全 | 短窗实时图，无 13 h 记录器 |
| 输出 | 每周期对齐 Δf、电流 | 状态 + 1σ/95% CI、NIS、预测源 |
| 适用 | 常规闭环、实验记录主路径 | 快变、不确定度触发重扫、科研对比 |
| 建议 | **作为电流测量主路径** | 并行验证；挂上记录器后再考虑主用 |

**EKF/UKF 13 维状态：**

\[
[f_L,f_R,\dot f_L,\dot f_R,
\operatorname{Re}b_L,\operatorname{Im}b_L,
\operatorname{Re}g_L,\operatorname{Im}g_L,
\operatorname{Re}b_R,\operatorname{Im}b_R,
\operatorname{Re}g_R,\operatorname{Im}g_R,I]
\]

电流为增广派生约束：\(I = a(f_R-f_L)+b\)。

---

## 6. API / 前端入口（实操）

| 入口 | 地址 / 接口 |
| --- | --- |
| 电流页 | `http://127.0.0.1:5173/current` |
| 准确度映射 | `http://127.0.0.1:5173/accuracy` |
| 状态估计 | `http://127.0.0.1:5173/state-estimation` |
| 记录状态 | `GET /api/measurement/current/tracking/recording/status` |
| 下载 Excel | `GET /api/measurement/current/tracking/recording/download` |
| API 文档 | `http://127.0.0.1:8000/docs` |

启动：仓库根目录 `start_all.bat`（或分别 `start_backend.bat` / `start_frontend.bat`）。

**前置：** 锁相 + 微波已连接；扫频范围覆盖最大电流下两峰全行程，边沿余量 ≥ 1×FWHM。

---

## 7. 风险与缺口（按优先级）

### P0 — 能否测准电流

1. **标定外推禁止**：激励超出标定 Δf 窗 → 电流无效。实验前用 0–目标电流做满量程标定点。  
2. **峰身份交换**：大电流 / 弱 SNR / 扫频太粗 → 左右跳同一峰。依赖 identity guard、最小间距、FM 相位筛选；需实测确认「一对且仅一对」。  
3. **时间对齐 vs 激励变化率**：激励阶跃或纹波过快而 \(T_u\) 不够 → Δf 系统偏差。先用 timing 报告看瓶颈（settle / VISA / 设备锁）。  
4. **0.2S 小电流点**：1%In 要求 \(\delta\Delta f\sim 57\,\mathrm{kHz}\)，闭环噪声、微波分辨率、锁相 TC 任一不达标都会失败。

### P1 — 长时间同步记录

5. **WebSocket 会话绑定**：刷新/关页 → 停微波并封存记录。真正无人值守缺「后端独立任务 + 重连」。  
6. **单微波源交替**：硬件上无法同时锁两峰；同步是软件外推。更高同步度需 List/触发跳频或第二源（架构未支持）。  
7. **状态估计路径无长时记录**：若以后主用 EKF，需复用或镜像 `CurrentTrackingRecorder`。

### P2 — 工程完善

8. 无 **激励电流源/分流器真值通道** 同步进 CSV（只有 ODMR 推算 I）。  
9. 无温度/参考传感器列。  
10. Zurich 节点 / 微波 SCPI 仍可能需按实机微调。  
11. 在含中文/WPS 云盘路径下，部分自动化工具落盘可能失败——研究副本宜放 ASCII 路径。

---

## 8. 后续实现建议

### 阶段 A — 用现成 PID 路径做可用系统

1. 固定几何：探头在一维亥姆霍兹中心，记录投影角；扫确认双峰。  
2. 静止峰 → 调 settle、probe offset、Kp；再 Ki。  
3. 阶梯激励 \(I_{\mathrm{exc}}\)（如 0.2 / 1 / 4 / 10 A）：每点记有效 Δf，写入物理标定。  
4. 慢扫激励 + 开 1 s 记录：检查 `f_left/f_right/delta_f/current` 与外部电流表一致性。  
5. 对各标准点对照 `/accuracy` 的 \(\delta(\Delta f)\) 容限。

### 阶段 B — 「同步」增强（代码向）

| 项 | 建议 |
| --- | --- |
| 真值通道 | 记录器增加 `excitation_current_ref_a`（串口/DAQ/电源回读），与 ODMR 行时间对齐 |
| 任务解耦 | `run_current_tracking` 改为后台 `task_id`，前端只订阅状态 |
| 更快同步 | 跟踪期暂停 100 Hz 轮询；Zurich 订阅缓冲取样；评估 List 跳频 |
| 双算法对照 | 同一标定系数下并行短窗 EKF，比 Δf 偏差与 CI |
| 事件标记 | CSV 增加 `operator_event`（阶跃时刻、换量程） |

### 阶段 C — 电流源闭环（若目标是控 I 而非只测 I）

当前仓库 **没有** 激励源驱动。若目标是给定母线/激励电流设定并稳定：

- 外环：设定 \(I^*\) → 读 \(\hat I(\Delta f)\) → 调电源  
- 内环：保持现有微波双峰跟踪  
- 带宽：\(f_{\mathrm{外环}} \ll f_{\mathrm{内环}}\)，且仅在 `valid=true` 时更新电源  

应作为新模块，不宜塞进 `dual_peak_tracker`。

---

## 9. PID 调参速查（摘自 README）

调参基准：实测单峰半高全宽 \(\Gamma = \mathrm{FWHM}\) 与同峰更新周期 \(T_u\)。

| 参数 | 推荐起始 |
| --- | ---: |
| 探测偏移 | 0.1～0.2 × Γ（默认常 250 kHz） |
| 每点稳定等待 | ≥ 5 × 锁相时间常数（代码至少 5 ms） |
| Kp | 0.2～0.45，从小开始 |
| Ki | 先 0，再 0.01～0.05 /s |
| Kd | 0 s（通常保持关闭） |
| 单周期最大校正 | 0.1～0.25 × Γ |
| 失锁偏差阈值 | 0.5～0.8 × Γ |

顺序：采集质量 → 只调 Kp → 再加 Ki → 最后决定是否 Kd。

---

## 10. 关键源码索引

| 文件 | 内容 |
| --- | --- |
| `backend/app/services/dual_peak_tracker.py` | FM 共振、PID、运动估计、`calculate_aligned_output` |
| `backend/app/services/instrument_manager.py` | `run_current_tracking` 全流程 |
| `backend/app/services/current_tracking_recorder.py` | 1 s 聚合与 CSV/Excel |
| `backend/app/services/joint_peak_estimator.py` | EKF/UKF 13 维 |
| `backend/app/services/state_estimation_tracking.py` | 状态估计运行时 |
| `backend/app/routers/measurement.py` | ODMR / 电流 / 记录 API |
| `frontend/src/pages/CurrentPage.jsx` | 物理标定与电流页 |
| `frontend/src/components/CurrentTrackingPanel.jsx` | 跟踪面板 |
| `docs/ct_accuracy_odmr_mapping.md` | GB 映射与平台灵敏度 |
| `README.md` | 调参、timing、长时记录说明 |

---

## 11. 结论

本仓库 **已经是一套可落地的「双峰跟踪 → 记录 \(f_\pm\)/Δf → 经验标定电流」方案**：物理模型、失锁恢复、时间对齐、长时记录和 GB 映射文档齐全；与「亥姆霍兹激励 + 一维探头测电流」计划高度对齐。

尚未覆盖：激励源真值同步、无人值守任务、以及把 EKF 线提升到与 PID 同等的长时记录与标定工作流。

**主路径建议：** `/current` PID + 物理标定 + 1 s 记录。  
**对照路径：** `/state-estimation` 用于不确定度与快变场景。

---

## 12. 可选后续工作

1. 给记录器加「外部激励电流」字段与接口草案  
2. 整理 `CurrentTrackingRequest` 全参数默认值实验 checklist  
3. 将「从激励阶跃到 CSV 一行」时序图写入仓库 `docs/`  
4. 把仓库克隆到纯 ASCII 路径后再跑自动化/deep-research 类工作流  

---

*报告结束。*
