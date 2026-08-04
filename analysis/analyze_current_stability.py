"""Analyze dual-peak current-tracking Excel for probe current stability."""
from __future__ import annotations

import warnings
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib import rcParams

warnings.filterwarnings("ignore")

rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans", "Arial"]
rcParams["axes.unicode_minus"] = False
rcParams["figure.dpi"] = 140
rcParams["savefig.dpi"] = 160
rcParams["axes.grid"] = True
rcParams["grid.alpha"] = 0.3


def stats(x: np.ndarray | pd.Series) -> dict:
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    if x.size == 0:
        return {}
    mean = float(np.mean(x))
    std = float(np.std(x, ddof=1)) if x.size > 1 else 0.0
    med = float(np.median(x))
    p16, p84 = np.percentile(x, [15.87, 84.13])
    mad = float(np.median(np.abs(x - med)))
    robust_sigma = 1.4826 * mad
    peak_to_peak = float(np.max(x) - np.min(x))
    cv = std / mean * 100 if mean != 0 else float("nan")
    return {
        "n": int(x.size),
        "mean": mean,
        "std": std,
        "median": med,
        "mad": mad,
        "robust_sigma": float(robust_sigma),
        "ptp": peak_to_peak,
        "cv_pct": float(cv),
        "p16": float(p16),
        "p84": float(p84),
        "min": float(np.min(x)),
        "max": float(np.max(x)),
    }


def overlapping_allan_dev(y: np.ndarray, dt: float, max_m: int | None = None):
    y = np.asarray(y, dtype=float)
    n = y.size
    if n < 8:
        return np.array([]), np.array([])
    if max_m is None:
        max_m = n // 4
    ms = np.unique(np.geomspace(1, max(1, max_m), num=30).astype(int))
    ms = ms[ms >= 1]
    taus, adev = [], []
    csum = np.cumsum(np.insert(y, 0, 0.0))
    for m in ms:
        if 2 * m >= n:
            continue
        max_i = n - 2 * m + 1
        if max_i < 2:
            continue
        idx = np.arange(max_i)
        m1 = (csum[idx + m] - csum[idx]) / m
        m2 = (csum[idx + 2 * m] - csum[idx + m]) / m
        diffs = m2 - m1
        avar = 0.5 * np.mean(diffs**2)
        taus.append(m * dt)
        adev.append(np.sqrt(avar))
    return np.array(taus), np.array(adev)


def main() -> None:
    src = Path(r"C:\Users\zhuzi\Desktop\current_tracking_20260729_155533_f0a50700.xlsx")
    out_dir = Path(__file__).resolve().parent / "current_tracking_20260729_155533"
    out_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_excel(src, sheet_name="Data")
    summary_dict: dict = {}
    try:
        s = pd.read_excel(src, sheet_name="Summary", header=1)
        if "Metric" in s.columns and "Value" in s.columns:
            for _, row in s.iterrows():
                summary_dict[str(row["Metric"])] = row["Value"]
    except Exception:
        pass

    df = df.copy()
    df["t"] = df["Elapsed (s)"].astype(float)
    df["I"] = df["Current (A)"].astype(float)
    df["I_std"] = df["Current std (A)"].astype(float)
    df["I_unc"] = df["Current uncertainty (A)"].astype(float)
    df["dF"] = df["Splitting Δf (Hz)"].astype(float)
    df["fcm"] = df["Common-mode frequency (Hz)"].astype(float)
    df["valid_frac"] = df["Valid fraction"].astype(float)
    df["all_valid"] = df["All samples valid"].astype(bool)
    df["relock"] = df["Relock count"].astype(int)
    df["lost"] = df["Lost-lock count"].astype(int)
    df["eL"] = df["Left frequency error (Hz)"].astype(float)
    df["eR"] = df["Right frequency error (Hz)"].astype(float)
    df["rate"] = df["Measured update rate (Hz)"].astype(float)

    both_locked = (df["Left peak state"] == "LOCKED") & (df["Right peak state"] == "LOCKED")
    clean = both_locked & df["all_valid"] & np.isfinite(df["I"])
    ops = both_locked & np.isfinite(df["I"])

    I_all = df.loc[ops, "I"]
    I_clean = df.loc[clean, "I"]
    t_ops = df.loc[ops, "t"]
    t_clean = df.loc[clean, "t"]

    duration = float(df["t"].iloc[-1] - df["t"].iloc[0])
    n_total = len(df)
    n_ops = int(ops.sum())
    n_clean = int(clean.sum())
    valid_frac_mean = float(df["valid_frac"].mean())
    s_ops = stats(I_all)
    s_clean = stats(I_clean)

    drift: dict = {}
    if n_clean >= 3:
        t0 = t_clean.values - t_clean.values[0]
        y = I_clean.values
        A = np.vstack([t0, np.ones_like(t0)]).T
        slope, intercept = np.linalg.lstsq(A, y, rcond=None)[0]
        y_fit = slope * t0 + intercept
        resid = y - y_fit
        residual_std = float(np.std(resid, ddof=1))
        ss_res = float(np.sum(resid**2))
        ss_tot = float(np.sum((y - np.mean(y)) ** 2))
        r2 = 1 - ss_res / ss_tot if ss_tot > 0 else float("nan")
        total_drift = slope * t0[-1]
        drift = {
            "slope_A_per_s": float(slope),
            "slope_mA_per_min": float(slope * 60 * 1e3),
            "total_drift_A": float(total_drift),
            "residual_std_A": residual_std,
            "r2": float(r2),
            "intercept": float(intercept),
            "t_span_s": float(t0[-1]),
        }

    window = 30
    roll = None
    if n_clean >= window:
        s = pd.Series(I_clean.values)
        roll_mean = s.rolling(window, center=True, min_periods=max(5, window // 3)).mean()
        roll_std = s.rolling(window, center=True, min_periods=max(5, window // 3)).std(ddof=1)
        roll = (t_clean.values, roll_mean.values, roll_std.values)

    dt_med = float(np.median(np.diff(df["t"].values)))
    taus, adev = (
        overlapping_allan_dev(I_clean.values, dt_med) if n_clean > 20 else (np.array([]), np.array([]))
    )

    s_dF = stats(df.loc[clean, "dF"])
    s_fcm = stats(df.loc[clean, "fcm"])
    s_eL = stats(df.loc[clean, "eL"])
    s_eR = stats(df.loc[clean, "eR"])

    n_relock_inc = int(df["relock"].diff().clip(lower=0).sum()) if n_total > 1 else 0
    n_lost_inc = int(df["lost"].diff().clip(lower=0).sum()) if n_total > 1 else 0
    frac_both_locked = float(both_locked.mean())
    frac_all_valid = float(df["all_valid"].mean())
    frac_clean = float(clean.mean())

    psd_info: dict = {}
    if n_clean >= 64:
        y = I_clean.values
        t = t_clean.values
        t_u = np.arange(t[0], t[-1], dt_med)
        if t_u.size >= 64:
            y_u = np.interp(t_u, t, y)
            x = t_u - t_u[0]
            A = np.vstack([x, np.ones_like(x)]).T
            sl, b = np.linalg.lstsq(A, y_u, rcond=None)[0]
            y_d = y_u - (sl * x + b)
            Y = np.fft.rfft(y_d * np.hanning(len(y_d)))
            freqs = np.fft.rfftfreq(len(y_d), d=dt_med)
            psd = (np.abs(Y) ** 2) / len(y_d)
            if freqs.size > 2:
                i_peak = 1 + int(np.argmax(psd[1:]))
                psd_info = {
                    "freqs": freqs,
                    "psd": psd,
                    "peak_f": float(freqs[i_peak]),
                    "peak_p": float(psd[i_peak]),
                }

    # Figure 1
    fig, axes = plt.subplots(
        3, 1, figsize=(11, 9), sharex=True, gridspec_kw={"height_ratios": [2.2, 1.2, 1.2]}
    )
    ax = axes[0]
    ax.plot(df["t"], df["I"], color="#94a3b8", lw=0.8, alpha=0.7, label="All samples")
    if n_clean:
        ax.plot(t_clean, I_clean, color="#0ea5e9", lw=1.1, label="Clean (LOCKED & valid)")
    if drift:
        t0 = t_clean.values - t_clean.values[0]
        ax.plot(
            t_clean,
            drift["intercept"] + drift["slope_A_per_s"] * t0,
            "r--",
            lw=1.5,
            label=f"Linear drift {drift['slope_mA_per_min']:.3f} mA/min",
        )
    if s_clean:
        ax.axhline(
            s_clean["mean"],
            color="#22c55e",
            ls=":",
            lw=1.2,
            label=f"Mean {s_clean['mean']:.4f} A",
        )
        ax.fill_between(
            [df["t"].min(), df["t"].max()],
            s_clean["mean"] - s_clean["std"],
            s_clean["mean"] + s_clean["std"],
            color="#22c55e",
            alpha=0.12,
            label=f"±1σ = ±{s_clean['std'] * 1e3:.2f} mA",
        )
    ax.set_ylabel("Current (A)")
    ax.set_title("Current tracking stability — time series")
    ax.legend(loc="upper right", fontsize=8, ncol=2)

    ax = axes[1]
    ax.plot(df["t"], df["I_std"] * 1e3, color="#a78bfa", lw=0.9, label="In-interval std")
    ax.plot(
        df["t"],
        df["I_unc"] * 1e3,
        color="#f97316",
        lw=0.9,
        alpha=0.85,
        label="Reported uncertainty",
    )
    ax.set_ylabel("mA")
    ax.set_title("Per-second dispersion / uncertainty")
    ax.legend(loc="upper right", fontsize=8)

    ax = axes[2]
    ax.plot(df["t"], df["valid_frac"], color="#14b8a6", lw=0.9, label="Valid fraction")
    ax.plot(
        df["t"],
        both_locked.astype(float),
        color="#ef4444",
        lw=0.8,
        alpha=0.7,
        label="Both LOCKED (0/1)",
    )
    ax.set_ylabel("Fraction")
    ax.set_xlabel("Elapsed (s)")
    ax.set_ylim(-0.05, 1.15)
    ax.set_title("Lock / validity quality")
    ax.legend(loc="upper right", fontsize=8)
    fig.tight_layout()
    fig.savefig(out_dir / "01_current_timeseries.png")
    plt.close(fig)

    # Figure 2
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    ax = axes[0]
    if n_clean:
        ax.hist(I_clean * 1e3, bins=40, color="#0ea5e9", alpha=0.85, edgecolor="white")
        ax.axvline(
            s_clean["mean"] * 1e3,
            color="#22c55e",
            ls="--",
            label=f"mean {s_clean['mean'] * 1e3:.2f} mA",
        )
        ax.axvline((s_clean["mean"] - s_clean["std"]) * 1e3, color="#94a3b8", ls=":")
        ax.axvline(
            (s_clean["mean"] + s_clean["std"]) * 1e3,
            color="#94a3b8",
            ls=":",
            label=f"±1σ {s_clean['std'] * 1e3:.2f} mA",
        )
    ax.set_xlabel("Current (mA)")
    ax.set_ylabel("Counts")
    ax.set_title("Clean current distribution")
    ax.legend(fontsize=8)

    ax = axes[1]
    if roll is not None:
        tt, _rm, rs = roll
        ax.plot(tt, rs * 1e3, color="#a78bfa", lw=1.1)
        ax.set_ylabel("Rolling σ (mA)")
        ax.set_xlabel("Elapsed (s)")
        ax.set_title(f"Rolling std (window={window} s)")
    else:
        ax.text(0.5, 0.5, "Not enough clean points", ha="center", va="center", transform=ax.transAxes)
    fig.tight_layout()
    fig.savefig(out_dir / "02_histogram_rolling.png")
    plt.close(fig)

    # Figure 3
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    ax = axes[0]
    if taus.size:
        ax.loglog(taus, adev * 1e3, "o-", color="#0ea5e9", ms=4, lw=1.2)
        ax.set_xlabel("τ (s)")
        ax.set_ylabel("Allan deviation (mA)")
        ax.set_title("Overlapping Allan deviation of current")
        for tau_mark in [1, 10, 60]:
            if taus.min() <= tau_mark <= taus.max():
                val = np.interp(tau_mark, taus, adev)
                ax.axvline(tau_mark, color="#94a3b8", ls=":", lw=0.8)
                ax.annotate(
                    f"τ={tau_mark}s\n{val * 1e3:.3f} mA",
                    xy=(tau_mark, val * 1e3),
                    textcoords="offset points",
                    xytext=(6, 6),
                    fontsize=7,
                )
    else:
        ax.text(0.5, 0.5, "Allan N/A", ha="center", transform=ax.transAxes)

    ax = axes[1]
    if drift and n_clean:
        t0 = t_clean.values - t_clean.values[0]
        resid = I_clean.values - (drift["intercept"] + drift["slope_A_per_s"] * t0)
        ax.plot(t_clean, resid * 1e3, color="#64748b", lw=0.8)
        ax.axhline(0, color="k", lw=0.6)
        ax.axhline(drift["residual_std_A"] * 1e3, color="#ef4444", ls="--", lw=0.9)
        ax.axhline(
            -drift["residual_std_A"] * 1e3,
            color="#ef4444",
            ls="--",
            lw=0.9,
            label=f"residual σ={drift['residual_std_A'] * 1e3:.2f} mA",
        )
        ax.set_xlabel("Elapsed (s)")
        ax.set_ylabel("Residual (mA)")
        ax.set_title("Detrended residual (after linear drift removal)")
        ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(out_dir / "03_allan_residual.png")
    plt.close(fig)

    # Figure 4
    fig, axes = plt.subplots(2, 1, figsize=(11, 6.5), sharex=True)
    ax = axes[0]
    ax.plot(
        df["t"],
        (df["dF"] - df["dF"].median()) / 1e3,
        color="#f59e0b",
        lw=0.9,
        label="Δf - median (kHz)",
    )
    ax.plot(
        df.loc[clean, "t"],
        (df.loc[clean, "dF"] - df.loc[clean, "dF"].median()) / 1e3,
        color="#0ea5e9",
        lw=0.9,
        alpha=0.9,
        label="clean",
    )
    ax.set_ylabel("Δf detuned (kHz)")
    ax.set_title("Peak splitting fluctuation (related to current via calibration)")
    ax.legend(fontsize=8)

    ax = axes[1]
    ax.plot(df["t"], df["eL"] / 1e3, color="#22c55e", lw=0.8, alpha=0.85, label="Left freq error")
    ax.plot(df["t"], df["eR"] / 1e3, color="#ef4444", lw=0.8, alpha=0.85, label="Right freq error")
    ax.set_ylabel("kHz")
    ax.set_xlabel("Elapsed (s)")
    ax.set_title("Tracking frequency error (servo residual)")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(out_dir / "04_frequency_stability.png")
    plt.close(fig)

    if psd_info:
        fig, ax = plt.subplots(figsize=(10, 4))
        f, p = psd_info["freqs"], psd_info["psd"]
        mask = f > 0
        ax.loglog(f[mask], p[mask], color="#0ea5e9", lw=1.0)
        ax.set_xlabel("Frequency (Hz)")
        ax.set_ylabel("Relative power (a.u.)")
        ax.set_title(f'Detrended current spectrum (peak ~ {psd_info["peak_f"]:.3f} Hz)')
        fig.tight_layout()
        fig.savefig(out_dir / "05_current_spectrum.png")
        plt.close(fig)

    allan_rows = []
    if taus.size:
        for tau_mark in [1, 2, 5, 10, 30, 60, 120, 300]:
            if taus.min() <= tau_mark <= taus.max():
                val = float(np.interp(tau_mark, taus, adev))
                allan_rows.append((tau_mark, val, val * 1e3))

    lines: list[str] = []
    lines.append("# 探头电流测量稳定性分析")
    lines.append("")
    lines.append(f"- **数据文件**: `{src.name}`")
    lines.append(f"- **Session**: `{summary_dict.get('Session ID', '20260729_155533_f0a50700')}`")
    lines.append(f"- **记录时长**: {duration:.1f} s ({duration / 60:.2f} min)")
    lines.append(f"- **聚合点数**: {n_total}（约 1 s 一行）")
    lines.append(f"- **中位采样间隔**: {dt_med:.3f} s")
    lines.append(f"- **双峰 LOCKED 占比**: {frac_both_locked * 100:.1f}%")
    lines.append(f"- **区间全有效占比**: {frac_all_valid * 100:.1f}%")
    lines.append(f"- **干净样本（双峰锁定且全有效）**: {n_clean}/{n_total} = {frac_clean * 100:.1f}%")
    lines.append(f"- **平均 Valid fraction**: {valid_frac_mean * 100:.1f}%")
    lines.append(f"- **Relock 增量累计**: {n_relock_inc}；**Lost-lock 增量累计**: {n_lost_inc}")
    lines.append("")
    lines.append("## 1. 电流水平与起伏（数值）")
    lines.append("")
    lines.append(
        "统计对象：**双峰 LOCKED 且 all-valid 的干净段**（更能反映探头/锁定在稳态下的噪声，而不是失锁瞬态）。"
    )
    lines.append("")
    if s_clean:
        lines.append("| 指标 | 数值 | 换算 |")
        lines.append("|---|---:|---:|")
        lines.append(f"| 样本数 | {s_clean['n']} | |")
        lines.append(f"| 均值 ⟨I⟩ | {s_clean['mean']:.6f} A | {s_clean['mean'] * 1e3:.3f} mA |")
        lines.append(f"| 标准差 σ | {s_clean['std']:.6f} A | **{s_clean['std'] * 1e3:.3f} mA** |")
        lines.append(f"| 相对起伏 CV | {s_clean['cv_pct']:.4f} % | **{s_clean['cv_pct'] * 10:.2f} ‰** |")
        lines.append(
            f"| 稳健 σ (1.4826·MAD) | {s_clean['robust_sigma']:.6f} A | {s_clean['robust_sigma'] * 1e3:.3f} mA |"
        )
        lines.append(f"| 峰峰值 | {s_clean['ptp']:.6f} A | {s_clean['ptp'] * 1e3:.3f} mA |")
        lines.append(f"| 中位数 | {s_clean['median']:.6f} A | |")
        lines.append(f"| P16–P84 | {s_clean['p16']:.6f} – {s_clean['p84']:.6f} A | |")
        lines.append("")
    if s_ops and s_ops.get("n") != s_clean.get("n"):
        lines.append(
            f"对照（仅双峰 LOCKED，含部分无效区间）：σ = {s_ops['std'] * 1e3:.3f} mA，n = {s_ops['n']}。"
        )
        lines.append("")

    lines.append("## 2. 漂移 vs 噪声")
    lines.append("")
    if drift:
        lines.append("对干净段做线性拟合 I(t)=a·t+b：")
        lines.append("")
        lines.append("| 指标 | 数值 |")
        lines.append("|---|---:|")
        lines.append(
            f"| 漂移斜率 | {drift['slope_A_per_s']:.4e} A/s = **{drift['slope_mA_per_min']:.4f} mA/min** |"
        )
        lines.append(
            f"| 全程线性漂移量 | {drift['total_drift_A'] * 1e3:.3f} mA（跨度 {drift['t_span_s'] / 60:.2f} min） |"
        )
        lines.append(f"| 去趋势后残差 σ | **{drift['residual_std_A'] * 1e3:.3f} mA** |")
        lines.append(f"| 拟合 R² | {drift['r2']:.4f} |")
        lines.append("")
        if abs(drift["total_drift_A"]) < 0.3 * s_clean["std"]:
            lines.append(
                "**解读**：全程线性漂移幅度小于随机起伏的 ~0.3σ，**主导是噪声/抖动而非单向漂移**。"
            )
        elif abs(drift["total_drift_A"]) < s_clean["std"]:
            lines.append(
                "**解读**：存在可测的缓漂，但幅度与短时噪声相当或更小，稳定性仍主要由起伏项决定。"
            )
        else:
            lines.append(
                "**解读**：线性漂移在全程上已超过 1σ 噪声，稳定性评估应同时报告漂移率与残差噪声。"
            )
        lines.append("")
    else:
        lines.append("干净点不足，无法可靠估计漂移。")
        lines.append("")

    lines.append("## 3. Allan 偏差（时间平均稳定性）")
    lines.append("")
    if allan_rows:
        lines.append("| 平均时间 τ (s) | σ_y(τ) (A) | σ_y(τ) (mA) |")
        lines.append("|---:|---:|---:|")
        for tau, a, amA in allan_rows:
            lines.append(f"| {tau:g} | {a:.4e} | {amA:.4f} |")
        lines.append("")
        lines.append(
            "若 Allan 曲线随 τ 下降，说明平均可抑制白噪声；若在某 τ 后上翘/平台，则存在闪烁噪声或漂移。"
        )
        lines.append("")
    else:
        lines.append("数据不足以计算 Allan 偏差。")
        lines.append("")

    lines.append("## 4. 共振/鉴频链路（辅助判断）")
    lines.append("")
    if s_dF:
        lines.append(
            f"- **峰分裂 Δf**：均值 {s_dF['mean'] / 1e6:.4f} MHz，σ = {s_dF['std'] / 1e3:.2f} kHz，CV = {s_dF['cv_pct']:.4f}%"
        )
    if s_fcm:
        lines.append(f"- **共模频率 fcm**：σ = {s_fcm['std'] / 1e3:.2f} kHz")
    if s_eL:
        lines.append(
            f"- **左峰频率误差 σ**：{s_eL['std'] / 1e3:.2f} kHz；**右峰**：{s_eR['std'] / 1e3:.2f} kHz"
        )
    lines.append(f"- **更新率中位数**：{float(np.median(df['rate'])):.2f} Hz")
    lines.append("")
    lines.append(
        "电流由 Δf 标定换算，因此 Δf 的相对稳定度应与电流相对稳定度同阶。"
        "若 I 的 CV 显著差于 Δf 的 CV，需检查标定系数 a、b 或无效样本混入。"
    )
    if s_clean and s_dF and s_dF["mean"] != 0:
        lines.append(
            f"- 本数据集：I 的 CV = {s_clean['cv_pct']:.4f}%；Δf 的 CV = {s_dF['cv_pct']:.4f}%"
        )
    lines.append("")

    lines.append("## 5. 稳定性结论（数形结合）")
    lines.append("")
    if s_clean:
        lines.append(f"1. **工作点**：约 **{s_clean['mean']:.4f} A ({s_clean['mean'] * 1e3:.1f} mA)**。")
        lines.append(
            f"2. **短时稳定度（干净段 1σ）**：**{s_clean['std'] * 1e3:.3f} mA**，相对 **{s_clean['cv_pct']:.3f}%**。"
        )
        if drift:
            lines.append(
                f"3. **缓漂**：约 **{drift['slope_mA_per_min']:.4f} mA/min**；去趋势后噪声 **{drift['residual_std_A'] * 1e3:.3f} mA**。"
            )
        lines.append(
            f"4. **锁定健康度**：双峰锁定 {frac_both_locked * 100:.1f}%，干净样本 {frac_clean * 100:.1f}%；"
            f"失锁/重锁事件 relock={n_relock_inc}, lost={n_lost_inc}。"
        )
        cv = s_clean["cv_pct"]
        if cv < 0.05:
            grade = "优秀（相对起伏 < 0.05%）"
        elif cv < 0.2:
            grade = "良好（相对起伏 < 0.2%）"
        elif cv < 1.0:
            grade = "一般（相对起伏 < 1%）"
        else:
            grade = "较差（相对起伏 ≥ 1%，建议检查锁定与环境）"
        lines.append(f"5. **综合评级（仅就本段记录）**：{grade}。")
    lines.append("")
    lines.append("## 6. 图件索引")
    lines.append("")
    lines.append("| 图 | 文件 | 说明 |")
    lines.append("|---|---|---|")
    lines.append("| 1 | `01_current_timeseries.png` | 电流时序、漂移拟合、区间不确定性、锁定质量 |")
    lines.append("| 2 | `02_histogram_rolling.png` | 电流直方图 + 滚动标准差 |")
    lines.append("| 3 | `03_allan_residual.png` | Allan 偏差 + 去趋势残差 |")
    lines.append("| 4 | `04_frequency_stability.png` | Δf 与左右峰频率误差 |")
    if psd_info:
        lines.append("| 5 | `05_current_spectrum.png` | 去趋势电流频谱 |")
    lines.append("")
    lines.append(f"全部输出目录：`{out_dir}`")

    report_path = out_dir / "stability_report.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")

    print("=== STABILITY SUMMARY ===")
    print(
        f"duration_s={duration:.1f}, n={n_total}, clean={n_clean}, "
        f"locked_frac={frac_both_locked:.3f}, clean_frac={frac_clean:.3f}"
    )
    print("I_clean:", s_clean)
    print("I_ops:", s_ops)
    print("drift:", drift)
    print("allan:", allan_rows)
    print("dF:", s_dF)
    print("report:", report_path)
    for p in sorted(out_dir.glob("*.png")):
        print("fig:", p)


if __name__ == "__main__":
    main()
