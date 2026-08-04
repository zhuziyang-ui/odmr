# GB 互感器准确度 → ODMR 频率/俯仰角映射说明

## 1. 标准与本地资料依据

| 来源 | 用途 |
| --- | --- |
| **GB/T 20840.2** 计量级 0.2 / 0.2S | 本次主用分段比值差限值（与 500 kV 计量 CT 常用等级一致） |
| 本地 `cw-29/NV学习_*.md`（张少春 / 国网量子 CT） | 0.2 级考核点 5%/20%/100% 对应 0.75%/0.35%/0.2%；直流目标 &lt;0.2% |
| 本地笔记提到的 GB/T 26217 / 工程上 **GB/T 26216.1** | HVDC 电子式直流测量装置；全文限值表未完整入库时，计量仍按 20840.2 0.2/0.2S 执行 |
| `cw-27/NV_ODMR_Angle_Response_Test_Plan.docx` | A±6° / B±4° 六轴台；微分头 0.01 mm；细扫 0.2°、目标复现 **~0.1°** |
| `cw-30/0721` 角度 ODMR + `physical_peak_calibration_*.csv` | 实测 Δf–I 与投影因子（1 A 时 Δf≈23 MHz &lt; 理论 38 MHz） |

**默认工程参数**

| 参数 | 值 |
| --- | ---: |
| In | 3000 A |
| 1 A 激励 → 中心磁场 | 6.8 Gs |
| 1 A 激励 ≈ 母线 | 150 A |
| γ/2π | 28 GHz/T = 2.8 MHz/G |
| 激励源量程 | 0–15 A → 等效母线 0–**2250 A**（75% In） |

---

## 2. 量值传递链

\[
I_{\mathrm{bus}}=\alpha I_{\mathrm{exc}},\quad
B=k_H I_{\mathrm{exc}}=\frac{k_H}{\alpha}I_{\mathrm{bus}}
\]

\[
\Delta f=f_+-f_-=2\gamma B_\parallel,\quad
B_\parallel=\frac{\Delta f}{2\gamma}
\]

**理论灵敏度（全对准 \(B_\parallel=B\)）**

| 量 | 数值 |
| --- | ---: |
| \(d(\Delta f)/dI_{\mathrm{bus}}\) | **253.87 kHz/A** |
| \(df_\pm/dI_{\mathrm{bus}}\) | **126.93 kHz/A** |
| \(d(\Delta f)/dI_{\mathrm{exc}}\) | **38.08 MHz/A** |

经验模式：跟踪程序 \(I=a\Delta f+b\)，则 \(\delta I=|a|\,\delta(\Delta f)\)。

---

## 3. Web UI（推荐）与 bat 启动

在 `odmr_repo` 目录双击：

| 脚本 | 作用 |
| --- | --- |
| `start_all.bat` | 同时开后端 + 前端两个窗口 |
| `start_backend.bat` | 仅后端 `http://127.0.0.1:8000` |
| `start_frontend.bat` | 仅前端 `http://127.0.0.1:5173` |

浏览器打开：

- 控制台首页：http://127.0.0.1:5173  
- **准确度映射页**：http://127.0.0.1:5173/accuracy  
- API 文档：http://127.0.0.1:8000/docs  

侧栏入口：**准确度映射**（GB 0.2/0.2S · δf→δI）。

API 前缀：`/api/accuracy/*`（`defaults` / `map` / `tables` / `export-csv` / `export-all`）。

## 3b. CSV 与 CLI

```bash
# 导出标准表 + 频率容限
python scripts/export_ct_accuracy_tables.py --In 3000 --out data/standards

# 频率偏差 → 电流误差
python scripts/freq_to_current_error.py --df-khz 50 --quantity delta_f --compare-standard
python scripts/freq_to_current_error.py --df-khz 50 --quantity branch
python scripts/freq_to_current_error.py --df-khz 50 --mode empirical --slope-a-per-hz 4.2e-8
```

主要输出文件（`data/standards/`）：

1. `gb20840_2_ratio_error_limits.csv` — 分段比值差  
2. `gb20840_2_abs_current_error_In3000A.csv` — 允许绝对电流误差（A）  
3. `gb20840_2_freq_tolerance_In3000A.csv` — Δf / 单支 f± 频率容限（kHz）  
4. `pitch_angle_geometric_budget.csv` — 1−cosθ 几何俯仰上界  
5. `platform_exc_for_standard_points_In3000A.csv` — 标准点对应激励电流  

**0.2S @ In=3000 A 速查**

| %In | I_bus (A) | δI (A) | δ(Δf) (kHz) | δf± (kHz) | 0–15 A 可达 |
| ---: | ---: | ---: | ---: | ---: | :---: |
| 1 | 30 | 0.225 | 57.1 | 28.6 | ✓ (0.2 A) |
| 5 | 150 | 0.525 | 133.3 | 66.6 | ✓ (1 A) |
| 20 | 600 | 1.2 | 304.6 | 152.3 | ✓ (4 A) |
| 100 | 3000 | 6.0 | 1523 | 762 | ✗ |
| 120 | 3600 | 7.2 | 1828 | 914 | ✗ |

小电流点频率容限最严：闭环与微波源在 1%In 处需把 **Δf 总误差控制在约 57 kHz 以内**。

---

## 4. 俯仰角步长：为何推荐 0.1°（结合你“4° 已很明显”的经验）

### 4.1 几何投影（电流标定后、未随角度重标定）

\[
\varepsilon = 1-\cos\theta
\]

| θ | 相对误差 ε | 相对 0.2% 预算 |
| ---: | ---: | --- |
| 0.1° | 0.00015% | 几乎不计 |
| 1° | 0.015% | 很宽裕 |
| 3.62° | ≈0.20% | **0.2 级几何边界** |
| **4°** | **≈0.244%** | **已超过 0.2%** |
| 6° | ≈0.55% | 明显超差 |

因此：**4° 差别很明显是合理的**——仅投影模型就已越过 0.2 级；再叠加峰对比度变化、多族峰劈裂、线形畸变，观感会更强。

### 4.2 与 `cw-27` 方案的衔接

原方案：粗扫 1–2° → 中扫 0.5° → 细扫 **0.2°**，目标复现 **~0.1°**。  
六轴 A 行程 **±6°**，微分头 **0.01 mm**；激光反射标定要求误差 **&lt;0.1°**。

### 4.3 是否以 0.1° 为步长？——**建议：边界与最优附近用 0.1°，外区用 0.5°**

| 区域 | 推荐步长 | 理由 |
| --- | ---: | --- |
| 远离 a* 的粗定位 | 0.5°–1° | 省时间；4° 级变化足够看见趋势 |
| 简并点 / 最大 Δf 附近 | **0.1°** | 与台精度目标一致；画准“谷底” |
| **准确度合格边界附近（约 ±3°–±5°）** | **0.1°** | 0.2% 边界约 3.6°；0.1° 对应边界处误差变化约 **0.01%** 量级，可分辨 pass/fail |
| 全范围盲扫一律 0.1° | 不推荐 | A 轴 ±6° 即 121 点 × 多电流，成本高 |

**结论：以 0.1° 作为“细扫与判据边界”步长是合适且推荐的**；不必在整个 ±6° 上全部 0.1°，但在你关心的“最大可允许俯仰范围”测定中，**边界必须 0.1° 加密**。

### 4.4 建议实验网格（0–15 A 激励，In=3000 A 等效）

1. **a→° 标定**（激光反射或倾角仪），单向逼近减回差（见 cw-27）。  
2. 固定 I_exc = 5 A 或 10 A，找 Δf 最大 a*（名义 0°）。  
3. **电流点**（等效母线 %In）  
   - 0.2 A → 30 A (1%)  
   - 1.0 A → 150 A (5%)  
   - 4.0 A → 600 A (20%)  
   - 15 A → 2250 A (75%，平台上限；**不能代替 100% In 认证点**)  
4. **角度**  
   - 粗：a* ±6°，步长 **0.5°**  
   - 细：在粗扫合格区边缘 ±1° 内，步长 **0.1°**  
   - 每点机械稳定 ≥5 s，单向逼近  
5. **判据**：用零俯仰标定系数换算 I_meas，比值差 ≤ 该电流百分数下 0.2 / 0.2S 限值；且 σ_Δf &lt; 表中 δ(Δf) 容限。  
6. **最大允许 a 范围**：所有目标电流点均合格的最大连续区间；并换算为 °。

---

## 5. 模块位置

- `backend/app/services/accuracy_mapping.py` — 计算核心  
- `scripts/export_ct_accuracy_tables.py` — 导出 CSV  
- `scripts/freq_to_current_error.py` — δf(kHz)→δI(A)  
- `backend/tests/test_accuracy_mapping.py` — 单测  

不修改 `/current` PID 与 EKF 主路径；需要时可将 CLI 结果挂到前端显示。
