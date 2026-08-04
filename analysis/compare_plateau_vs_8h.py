"""Compare Excel plateau (t>620s) vs stable segment from 8h aggregate CSV by CV."""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib import rcParams

rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans", "Arial"]
rcParams["axes.unicode_minus"] = False
rcParams["figure.dpi"] = 140
rcParams["savefig.dpi"] = 160
rcParams["axes.grid"] = True
rcParams["grid.alpha"] = 0.3

T_CUT = 620.0
# Prefer a long stable window for 8h data (comparable multi-hour use)
CANDIDATE_WINDOWS_S = [600, 1800, 3600, 7200]  # 10min, 30min, 1h, 2h


def stats(I: np.ndarray) -> dict:
    I = np.asarray(I, dtype=float)
    I = I[np.isfinite(I)]
    mean = float(np.mean(I))
    std = float(np.std(I, ddof=1)) if I.size > 1 else 0.0
    med = float(np.median(I))
    mad = float(np.median(np.abs(I - med)))
    return {
        "n": int(I.size),
        "mean": mean,
        "std": std,
        "cv": std / mean if mean != 0 else float("nan"),
        "cv_pct": (std / mean * 100.0) if mean != 0 else float("nan"),
        "median": med,
        "robust_sigma": float(1.4826 * mad),
        "ptp": float(np.ptp(I)),
        "min": float(np.min(I)),
        "max": float(np.max(I)),
    }


def best_window_by_cv(t: np.ndarray, I: np.ndarray, window_s: float, step_s: float = 30.0):
    """Sliding window with lowest CV."""
    t = np.asarray(t, dtype=float)
    I = np.asarray(I, dtype=float)
    m = np.isfinite(I) & np.isfinite(t)
    t, I = t[m], I[m]
    if t.size < 10:
        return None
    t0, t1 = float(t[0]), float(t[-1])
    if t1 - t0 < window_s:
        return None
    best = None
    start = t0
    while start + window_s <= t1 + 1e-9:
        end = start + window_s
        mask = (t >= start) & (t < end)
        if mask.sum() >= max(30, int(0.7 * window_s)):  # allow some missing bins
            st = stats(I[mask])
            st["t0"] = start
            st["t1"] = end
            st["duration_s"] = window_s
            if best is None or st["cv"] < best["cv"]:
                best = st
        start += step_s
    return best


def main() -> None:
    xlsx = Path(r"C:\Users\zhuzi\Desktop\current_tracking_20260729_155533_f0a50700.xlsx")
    csv = Path(
        r"C:\Users\zhuzi\Documents\xwechat_files\wxid_l0d2mmllreaq12_5ca4\msg\file\2026-07\session_d73408df_1s_aggregate.csv"
    )
    out_dir = Path(__file__).resolve().parent / "compare_20260729_plateau_vs_8h_session"
    out_dir.mkdir(parents=True, exist_ok=True)

    # --- A: Excel plateau t>620 ---
    dfx = pd.read_excel(xlsx, sheet_name="Data")
    tx = dfx["Elapsed (s)"].to_numpy(float)
    Ix = dfx["Current (A)"].to_numpy(float)
    locked = (dfx["Left peak state"].astype(str) == "LOCKED") & (
        dfx["Right peak state"].astype(str) == "LOCKED"
    )
    valid = dfx["All samples valid"].to_numpy(bool) if "All samples valid" in dfx.columns else np.ones(len(dfx), bool)
    mx = (tx > T_CUT) & locked & valid & np.isfinite(Ix)
    A = stats(Ix[mx])
    A["label"] = f"20260729 Excel\nplateau t>{T_CUT:.0f}s"
    A["t0"] = float(tx[mx].min())
    A["t1"] = float(tx[mx].max())
    A["duration_s"] = A["t1"] - A["t0"]
    A["source"] = str(xlsx.name)

    # drift on A
    tA = tx[mx]
    IA = Ix[mx]
    t_rel = tA - tA[0]
    coef = np.polyfit(t_rel, IA, 1)
    A["drift_mA_per_min"] = float(coef[0] * 60 * 1e3)
    resid = IA - np.polyval(coef, t_rel)
    A["resid_std"] = float(np.std(resid, ddof=1))

    # --- B: 8h CSV, find stable segment ---
    dfc = pd.read_csv(csv)
    tc = dfc["t_bin"].to_numpy(float)
    Ic = dfc["current_a"].to_numpy(float)
    mc = np.isfinite(Ic) & np.isfinite(tc)
    tc, Ic = tc[mc], Ic[mc]
    full_B = stats(Ic)
    full_B["duration_s"] = float(tc[-1] - tc[0])
    full_B["t0"] = float(tc[0])
    full_B["t1"] = float(tc[-1])

    window_results = {}
    for w in CANDIDATE_WINDOWS_S:
        step = 30.0 if w <= 1800 else 60.0
        window_results[w] = best_window_by_cv(tc, Ic, w, step_s=step)

    # Primary pick: longest window that still has reasonably low CV,
    # prefer 1h if available; else best among available.
    # User asked for a stable period from 8h test — use best 1h if exists, else best 30min, else best 10min.
    B = None
    for w in [3600, 1800, 7200, 600]:
        if window_results.get(w) is not None:
            B = dict(window_results[w])
            B["window_s"] = w
            break
    if B is None:
        raise SystemExit("Could not find stable window in 8h CSV")

    B["label"] = f"8h session\nbest {int(B['window_s']/60)}min"
    B["source"] = str(csv.name)

    # Also record absolute best 10min / 30min / 1h for table
    # Compare
    ratio_B_over_A = B["cv"] / A["cv"]
    ratio_A_over_B = A["cv"] / B["cv"]
    if B["cv"] > A["cv"]:
        larger = "8 小时会话选定段"
        smaller = "20260729 平台 (t>620s)"
    else:
        larger = "20260729 平台 (t>620s)"
        smaller = "8 小时会话选定段"

    # ---- figures ----
    # 1) Excel plateau
    fig, axes = plt.subplots(2, 1, figsize=(11, 6.5), sharex=True)
    ax = axes[0]
    ax.plot(tA, IA * 1e3, color="#0ea5e9", lw=1.0, label="I")
    ax.axhline(A["mean"] * 1e3, color="#22c55e", ls="--", label=f"mean={A['mean']*1e3:.2f} mA")
    ax.fill_between(
        [tA.min(), tA.max()],
        (A["mean"] - A["std"]) * 1e3,
        (A["mean"] + A["std"]) * 1e3,
        color="#22c55e",
        alpha=0.15,
        label=f"+/-1 sigma={A['std']*1e3:.2f} mA",
    )
    ax.set_ylabel("Current (mA)")
    ax.set_title(f"A: 20260729 Excel plateau (t > {T_CUT:.0f} s)")
    ax.legend(fontsize=8)

    ax = axes[1]
    ax.plot(tA, resid * 1e3, color="#64748b", lw=0.8)
    ax.axhline(0, color="k", lw=0.6)
    ax.axhline(A["resid_std"] * 1e3, color="#ef4444", ls="--")
    ax.axhline(-A["resid_std"] * 1e3, color="#ef4444", ls="--", label=f"resid sigma={A['resid_std']*1e3:.2f} mA")
    ax.set_xlabel("Elapsed (s)")
    ax.set_ylabel("Residual (mA)")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(out_dir / "01_excel_plateau_t620.png")
    plt.close(fig)

    # 2) 8h overview + selected window
    fig, axes = plt.subplots(2, 1, figsize=(12, 7.0), sharex=False)
    ax = axes[0]
    # downsample for plot speed
    step_plot = max(1, len(tc) // 8000)
    ax.plot(tc[::step_plot] / 3600.0, Ic[::step_plot], color="#94a3b8", lw=0.6, label="1s aggregate")
    ax.axvspan(B["t0"] / 3600.0, B["t1"] / 3600.0, color="#0ea5e9", alpha=0.2, label="selected stable window")
    ax.set_ylabel("current_a")
    ax.set_xlabel("time (hours from t_bin start scale)")
    ax.set_title(f"B: 8h session overview ({full_B['duration_s']/3600:.2f} h, n={full_B['n']})")
    ax.legend(fontsize=8)

    mB = (tc >= B["t0"]) & (tc < B["t1"])
    tB, IB = tc[mB], Ic[mB]
    ax = axes[1]
    ax.plot(tB, IB, color="#0ea5e9", lw=0.9)
    ax.axhline(B["mean"], color="#22c55e", ls="--", label=f"mean={B['mean']:.4g}")
    ax.fill_between(
        [B["t0"], B["t1"]],
        B["mean"] - B["std"],
        B["mean"] + B["std"],
        color="#22c55e",
        alpha=0.15,
        label=f"+/-1 sigma={B['std']:.4g}  CV={B['cv_pct']:.4f}%",
    )
    ax.set_xlabel("t_bin (s)")
    ax.set_ylabel("current_a")
    ax.set_title(
        f"Selected stable window: t={B['t0']:.0f}-{B['t1']:.0f}s "
        f"({B['duration_s']/60:.0f} min), CV={B['cv_pct']:.4f}%"
    )
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(out_dir / "02_8h_overview_and_window.png")
    plt.close(fig)

    # 3) CV bar comparison
    fig, ax = plt.subplots(figsize=(9, 4.5))
    labels = [
        f"A Excel plateau\nt>{T_CUT:.0f}s",
        f"B 8h best\n{int(B['window_s']/60)}min",
        "B 8h\nfull record",
    ]
    cvs = [A["cv_pct"], B["cv_pct"], full_B["cv_pct"]]
    colors = ["#22c55e", "#0ea5e9", "#f97316"]
    bars = ax.bar(labels, cvs, color=colors, edgecolor="white", width=0.6)
    for bar, v in zip(bars, cvs):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(), f"{v:.4f}%", ha="center", va="bottom", fontsize=10)
    ax.set_ylabel("CV = std / mean  (%)")
    ax.set_title("Who fluctuates more? (larger CV = larger relative fluctuation)")
    fig.tight_layout()
    fig.savefig(out_dir / "03_cv_comparison_bars.png")
    plt.close(fig)

    # 4) side-by-side relative fluctuation histograms
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    relA = (IA - A["mean"]) / A["mean"] * 100.0
    relB = (IB - B["mean"]) / B["mean"] * 100.0
    axes[0].hist(relA, bins=40, color="#22c55e", alpha=0.9, edgecolor="white")
    axes[0].axvline(0, color="k", ls="--", lw=0.8)
    axes[0].set_title(f"A relative (CV={A['cv_pct']:.4f}%)")
    axes[0].set_xlabel("(I-mean)/mean (%)")
    axes[0].set_ylabel("Counts")
    axes[1].hist(relB, bins=40, color="#0ea5e9", alpha=0.9, edgecolor="white")
    axes[1].axvline(0, color="k", ls="--", lw=0.8)
    axes[1].set_title(f"B relative (CV={B['cv_pct']:.4f}%)")
    axes[1].set_xlabel("(I-mean)/mean (%)")
    fig.tight_layout()
    fig.savefig(out_dir / "04_relative_histograms.png")
    plt.close(fig)

    # report
    lines = [
        "# 电流稳定性：Excel 平台 vs 8 小时会话",
        "",
        "## 指标",
        "",
        r"- 均值 $\langle I \rangle$、标准差 $\sigma$",
        r"- 相对波动 $\mathrm{CV}=\sigma/\langle I \rangle$（用于跨量级对比）",
        "",
        "## A. 20260729 Excel（t > 620 s）",
        "",
        f"- 文件: `{xlsx.name}`",
        f"- 截取: Elapsed > {T_CUT:.0f} s，双峰 LOCKED 且 all-valid",
        f"- 时间窗: {A['t0']:.1f} – {A['t1']:.1f} s（{A['duration_s']/60:.2f} min）",
        f"- **均值**: **{A['mean']:.6f} A** = **{A['mean']*1e3:.3f} mA**",
        f"- **标准差**: **{A['std']:.6f} A** = **{A['std']*1e3:.3f} mA**",
        f"- **CV**: **{A['cv_pct']:.4f}%**",
        f"- 稳健 σ: {A['robust_sigma']*1e3:.3f} mA；峰峰值: {A['ptp']*1e3:.3f} mA",
        f"- 线性漂移: {A['drift_mA_per_min']:.4f} mA/min；去趋势残差 σ: {A['resid_std']*1e3:.3f} mA",
        f"- 样本数 n = {A['n']}",
        "",
        "## B. 8 小时会话（自动选稳态窗）",
        "",
        f"- 文件: `{csv.name}`",
        f"- 全记录: t_bin {full_B['t0']:.0f}–{full_B['t1']:.0f} s ≈ **{full_B['duration_s']/3600:.2f} h**，n={full_B['n']}",
        f"- 全记录均值/σ/CV: {full_B['mean']:.6g} / {full_B['std']:.6g} / **{full_B['cv_pct']:.4f}%**（含工况变化，不宜直接当稳定度）",
        "",
        "### 各窗长最优 CV 扫描",
        "",
        "| 窗长 | 最优 CV (%) | 均值 | 标准差 | t0–t1 (s) |",
        "|---:|---:|---:|---:|---|",
    ]
    for w in CANDIDATE_WINDOWS_S:
        r = window_results.get(w)
        if r is None:
            lines.append(f"| {w/60:.0f} min | — | — | — | — |")
        else:
            lines.append(
                f"| {w/60:.0f} min | {r['cv_pct']:.4f}% | {r['mean']:.6g} | {r['std']:.6g} | {r['t0']:.0f}–{r['t1']:.0f} |"
            )
    lines += [
        "",
        f"### 主选稳态段（用于对比）: 最佳 **{int(B['window_s']/60)} min** 窗",
        "",
        f"- 时间窗: t_bin **{B['t0']:.0f} – {B['t1']:.0f} s**",
        f"- **均值**: **{B['mean']:.6g}**",
        f"- **标准差**: **{B['std']:.6g}**",
        f"- **CV**: **{B['cv_pct']:.4f}%**",
        f"- n = {B['n']}",
        "",
        "## 对比：谁的波动更大？",
        "",
        "| 数据集 | 均值 | 标准差 | **CV=σ/均值** | CV (%) |",
        "|---|---:|---:|---:|---:|",
        f"| A Excel t>{T_CUT:.0f}s | {A['mean']:.6g} | {A['std']:.6g} | {A['cv']:.6e} | **{A['cv_pct']:.4f}%** |",
        f"| B 8h 选定 {int(B['window_s']/60)}min | {B['mean']:.6g} | {B['std']:.6g} | {B['cv']:.6e} | **{B['cv_pct']:.4f}%** |",
        f"| B 8h 全程 | {full_B['mean']:.6g} | {full_B['std']:.6g} | {full_B['cv']:.6e} | **{full_B['cv_pct']:.4f}%** |",
        "",
        f"- CV(B)/CV(A) = **{ratio_B_over_A:.3f}**",
        f"- CV(A)/CV(B) = **{ratio_A_over_B:.3f}**",
        f"- **相对波动更大的是：{larger}**",
        f"- **相对波动更小的是：{smaller}**",
        "",
        "说明：绝对电流量级不同时，应用 CV 而非裸 σ 比较“谁抖得更厉害”。",
        "",
        "## 图件",
        "",
        "| 图 | 文件 |",
        "|---|---|",
        "| 1 | `01_excel_plateau_t620.png` |",
        "| 2 | `02_8h_overview_and_window.png` |",
        "| 3 | `03_cv_comparison_bars.png` |",
        "| 4 | `04_relative_histograms.png` |",
        "",
        f"输出目录: `{out_dir}`",
    ]
    report = out_dir / "comparison_report.md"
    report.write_text("\n".join(lines), encoding="utf-8")

    print("=== A Excel t>620 ===")
    print(f"mean={A['mean']:.8f} A = {A['mean']*1e3:.4f} mA")
    print(f"std ={A['std']:.8f} A = {A['std']*1e3:.4f} mA")
    print(f"CV%={A['cv_pct']:.4f}  n={A['n']}  duration_min={A['duration_s']/60:.2f}")
    print("=== B 8h full ===")
    print(f"mean={full_B['mean']:.6g} std={full_B['std']:.6g} CV%={full_B['cv_pct']:.4f} duration_h={full_B['duration_s']/3600:.2f}")
    print("=== B selected window ===")
    print(f"window={B['window_s']/60:.0f}min t={B['t0']:.0f}-{B['t1']:.0f}")
    print(f"mean={B['mean']:.6g} std={B['std']:.6g} CV%={B['cv_pct']:.4f} n={B['n']}")
    print("=== COMPARE ===")
    print(f"CV_B/CV_A={ratio_B_over_A:.4f}  larger_fluctuation={larger}")
    for w, r in window_results.items():
        if r:
            print(f"scan {w/60:.0f}min: CV%={r['cv_pct']:.4f} mean={r['mean']:.6g} std={r['std']:.6g} t={r['t0']:.0f}-{r['t1']:.0f}")
    print("report:", report)


if __name__ == "__main__":
    main()
