"""Stability analysis restricted to the steady plateau t > 620 s."""
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

T_CUT_S = 620.0


def stats(x: np.ndarray) -> dict:
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    if x.size == 0:
        return {}
    mean = float(np.mean(x))
    std = float(np.std(x, ddof=1)) if x.size > 1 else 0.0
    med = float(np.median(x))
    mad = float(np.median(np.abs(x - med)))
    p16, p84 = np.percentile(x, [15.87, 84.13])
    return {
        "n": int(x.size),
        "mean": mean,
        "std": std,
        "median": med,
        "mad": mad,
        "robust_sigma": float(1.4826 * mad),
        "ptp": float(np.ptp(x)),
        "cv_pct": float(std / mean * 100) if mean != 0 else float("nan"),
        "p16": float(p16),
        "p84": float(p84),
        "min": float(np.min(x)),
        "max": float(np.max(x)),
    }


def overlapping_allan_dev(y: np.ndarray, dt: float):
    y = np.asarray(y, dtype=float)
    n = y.size
    if n < 8:
        return np.array([]), np.array([])
    max_m = n // 4
    ms = np.unique(np.geomspace(1, max(1, max_m), num=28).astype(int))
    csum = np.cumsum(np.insert(y, 0, 0.0))
    taus, adev = [], []
    for m in ms:
        max_i = n - 2 * m + 1
        if max_i < 2:
            continue
        idx = np.arange(max_i)
        m1 = (csum[idx + m] - csum[idx]) / m
        m2 = (csum[idx + 2 * m] - csum[idx + m]) / m
        avar = 0.5 * np.mean((m2 - m1) ** 2)
        taus.append(m * dt)
        adev.append(np.sqrt(avar))
    return np.array(taus), np.array(adev)


def main() -> None:
    src = Path(r"C:\Users\zhuzi\Desktop\current_tracking_20260729_155533_f0a50700.xlsx")
    out_dir = Path(__file__).resolve().parent / "current_tracking_20260729_155533_plateau_t620"
    out_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_excel(src, sheet_name="Data")
    t_all = df["Elapsed (s)"].to_numpy(float)
    mask = t_all > T_CUT_S
    both_locked = (df["Left peak state"] == "LOCKED") & (df["Right peak state"] == "LOCKED")
    clean = mask & both_locked & df["All samples valid"].to_numpy(bool) & np.isfinite(df["Current (A)"])

    d = df.loc[clean].copy()
    t = d["Elapsed (s)"].to_numpy(float)
    I = d["Current (A)"].to_numpy(float)
    I_std = d["Current std (A)"].to_numpy(float)
    I_unc = d["Current uncertainty (A)"].to_numpy(float)
    dF = d["Splitting Δf (Hz)"].to_numpy(float)
    eL = d["Left frequency error (Hz)"].to_numpy(float)
    eR = d["Right frequency error (Hz)"].to_numpy(float)
    rate = d["Measured update rate (Hz)"].to_numpy(float)

    if I.size < 10:
        raise SystemExit(f"Not enough plateau points after t>{T_CUT_S}s")

    t_rel = t - t[0]
    duration = float(t[-1] - t[0])
    dt_med = float(np.median(np.diff(t)))
    sI = stats(I)
    s_dF = stats(dF)
    s_eL = stats(eL)
    s_eR = stats(eR)

    # linear drift
    A = np.vstack([t_rel, np.ones_like(t_rel)]).T
    slope, intercept = np.linalg.lstsq(A, I, rcond=None)[0]
    resid = I - (slope * t_rel + intercept)
    residual_std = float(np.std(resid, ddof=1))
    ss_res = float(np.sum(resid**2))
    ss_tot = float(np.sum((I - np.mean(I)) ** 2))
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else float("nan")
    total_drift = float(slope * t_rel[-1])
    drift = {
        "slope_A_per_s": float(slope),
        "slope_mA_per_min": float(slope * 60 * 1e3),
        "total_drift_mA": total_drift * 1e3,
        "residual_std_mA": residual_std * 1e3,
        "r2": float(r2),
        "intercept": float(intercept),
    }

    dI = np.diff(I)
    diff_rms = float(np.sqrt(np.mean(dI**2)))
    diff_std = float(np.std(dI, ddof=1))
    med_abs_diff = float(np.median(np.abs(dI)))

    window = min(30, max(5, I.size // 5))
    ser = pd.Series(I)
    roll_std = ser.rolling(window, center=True, min_periods=max(3, window // 3)).std(ddof=1).to_numpy()

    taus, adev = overlapping_allan_dev(I, dt_med)
    allan_rows = []
    for tau_mark in [1, 2, 5, 10, 30, 60, 120, 180]:
        if taus.size and taus.min() <= tau_mark <= taus.max():
            val = float(np.interp(tau_mark, taus, adev))
            allan_rows.append((tau_mark, val, val * 1e3))

    # spectrum of residual
    t_u = np.arange(t[0], t[-1], dt_med)
    y_u = np.interp(t_u, t, I)
    x = t_u - t_u[0]
    A2 = np.vstack([x, np.ones_like(x)]).T
    sl, b = np.linalg.lstsq(A2, y_u, rcond=None)[0]
    y_d = y_u - (sl * x + b)
    Y = np.fft.rfft(y_d * np.hanning(len(y_d)))
    freqs = np.fft.rfftfreq(len(y_d), d=dt_med)
    psd = (np.abs(Y) ** 2) / len(y_d)

    # ---- figures ----
    fig, axes = plt.subplots(3, 1, figsize=(11, 8.5), sharex=True, gridspec_kw={"height_ratios": [2.2, 1.2, 1.2]})
    ax = axes[0]
    ax.plot(t, I * 1e3, color="#0ea5e9", lw=1.1, label="I (plateau)")
    ax.plot(t, (intercept + slope * t_rel) * 1e3, "r--", lw=1.4, label=f"drift {drift['slope_mA_per_min']:.4f} mA/min")
    ax.axhline(sI["mean"] * 1e3, color="#22c55e", ls=":", lw=1.2, label=f"mean {sI['mean']*1e3:.2f} mA")
    ax.fill_between(
        [t.min(), t.max()],
        (sI["mean"] - sI["std"]) * 1e3,
        (sI["mean"] + sI["std"]) * 1e3,
        color="#22c55e",
        alpha=0.12,
        label=f"±1σ = ±{sI['std']*1e3:.2f} mA",
    )
    ax.set_ylabel("Current (mA)")
    ax.set_title(f"Steady plateau only: Elapsed > {T_CUT_S:.0f} s  (duration {duration/60:.2f} min)")
    ax.legend(loc="upper right", fontsize=8, ncol=2)

    ax = axes[1]
    ax.plot(t, resid * 1e3, color="#64748b", lw=0.9)
    ax.axhline(0, color="k", lw=0.6)
    ax.axhline(drift["residual_std_mA"], color="#ef4444", ls="--", lw=0.9)
    ax.axhline(-drift["residual_std_mA"], color="#ef4444", ls="--", lw=0.9, label=f"residual σ={drift['residual_std_mA']:.2f} mA")
    ax.set_ylabel("Residual (mA)")
    ax.set_title("Linear-detrended residual")
    ax.legend(fontsize=8)

    ax = axes[2]
    ax.plot(t, I_std * 1e3, color="#a78bfa", lw=0.9, label="In-interval std")
    ax.plot(t, I_unc * 1e3, color="#f97316", lw=0.9, alpha=0.85, label="Reported uncertainty")
    ax.plot(t, roll_std * 1e3, color="#0ea5e9", lw=1.0, label=f"Rolling σ ({window}s)")
    ax.set_ylabel("mA")
    ax.set_xlabel("Elapsed (s)")
    ax.set_title("Dispersion metrics on plateau")
    ax.legend(loc="upper right", fontsize=8)
    fig.tight_layout()
    fig.savefig(out_dir / "01_plateau_timeseries.png")
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    ax = axes[0]
    ax.hist(I * 1e3, bins=35, color="#0ea5e9", alpha=0.9, edgecolor="white")
    ax.axvline(sI["mean"] * 1e3, color="#22c55e", ls="--", label=f"mean {sI['mean']*1e3:.2f} mA")
    ax.axvline((sI["mean"] - sI["std"]) * 1e3, color="#94a3b8", ls=":")
    ax.axvline((sI["mean"] + sI["std"]) * 1e3, color="#94a3b8", ls=":", label=f"±1σ {sI['std']*1e3:.2f} mA")
    ax.set_xlabel("Current (mA)")
    ax.set_ylabel("Counts")
    ax.set_title("Plateau current distribution")
    ax.legend(fontsize=8)

    ax = axes[1]
    if taus.size:
        ax.loglog(taus, adev * 1e3, "o-", color="#0ea5e9", ms=4, lw=1.2)
        for tau_mark in [1, 10, 60]:
            if taus.min() <= tau_mark <= taus.max():
                val = np.interp(tau_mark, taus, adev)
                ax.axvline(tau_mark, color="#94a3b8", ls=":", lw=0.8)
                ax.annotate(
                    f"τ={tau_mark}s\n{val*1e3:.3f} mA",
                    xy=(tau_mark, val * 1e3),
                    textcoords="offset points",
                    xytext=(6, 6),
                    fontsize=7,
                )
        ax.set_xlabel("τ (s)")
        ax.set_ylabel("Allan deviation (mA)")
        ax.set_title("Allan deviation (plateau only)")
    fig.tight_layout()
    fig.savefig(out_dir / "02_plateau_hist_allan.png")
    plt.close(fig)

    fig, axes = plt.subplots(2, 1, figsize=(11, 6.2), sharex=True)
    ax = axes[0]
    ax.plot(t, (dF - np.median(dF)) / 1e3, color="#f59e0b", lw=0.9)
    ax.set_ylabel("Δf − median (kHz)")
    ax.set_title("Peak splitting fluctuation on plateau")
    ax = axes[1]
    ax.plot(t, eL / 1e3, color="#22c55e", lw=0.8, alpha=0.85, label="Left freq error")
    ax.plot(t, eR / 1e3, color="#ef4444", lw=0.8, alpha=0.85, label="Right freq error")
    ax.set_ylabel("kHz")
    ax.set_xlabel("Elapsed (s)")
    ax.set_title("Tracking frequency error on plateau")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(out_dir / "03_plateau_frequency.png")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(10, 4))
    m = freqs > 0
    ax.loglog(freqs[m], psd[m], color="#0ea5e9", lw=1.0)
    ax.set_xlabel("Frequency (Hz)")
    ax.set_ylabel("Relative power (a.u.)")
    ax.set_title("Detrended plateau current spectrum")
    fig.tight_layout()
    fig.savefig(out_dir / "04_plateau_spectrum.png")
    plt.close(fig)

    # report
    lines = [
        f"# 稳态平台稳定性分析（Elapsed > {T_CUT_S:.0f} s）",
        "",
        f"- **数据**: `{src.name}`",
        f"- **截取条件**: Elapsed > {T_CUT_S:.0f} s，且双峰 LOCKED + all-valid",
        f"- **平台样本数**: {sI['n']}",
        f"- **平台时长**: {duration:.1f} s（{duration/60:.2f} min）",
        f"- **中位时间间隔**: {dt_med:.3f} s",
        f"- **更新率中位数**: {float(np.median(rate)):.2f} Hz",
        "",
        "## 1. 电流稳定度（主结果）",
        "",
        "| 指标 | 数值 | 换算 |",
        "|---|---:|---:|",
        f"| 均值 ⟨I⟩ | {sI['mean']:.6f} A | **{sI['mean']*1e3:.3f} mA** |",
        f"| 标准差 σ | {sI['std']:.6f} A | **{sI['std']*1e3:.3f} mA** |",
        f"| 相对起伏 CV | {sI['cv_pct']:.4f} % | **{sI['cv_pct']*10:.3f} ‰** |",
        f"| 稳健 σ (1.4826·MAD) | {sI['robust_sigma']:.6f} A | {sI['robust_sigma']*1e3:.3f} mA |",
        f"| 峰峰值 | {sI['ptp']:.6f} A | {sI['ptp']*1e3:.3f} mA |",
        f"| P16–P84 | {sI['p16']:.6f} – {sI['p84']:.6f} A | |",
        f"| 秒内 std 中位数 | {float(np.median(I_std)):.6f} A | {float(np.median(I_std))*1e3:.3f} mA |",
        f"| 报告 uncertainty 中位数 | {float(np.median(I_unc)):.6f} A | {float(np.median(I_unc))*1e3:.3f} mA |",
        f"| 相邻点差分 RMS | {diff_rms:.6f} A | {diff_rms*1e3:.3f} mA |",
        f"| 相邻点差分 σ | {diff_std:.6f} A | {diff_std*1e3:.3f} mA |",
        f"| 相邻点 |ΔI| 中位数 | {med_abs_diff:.6f} A | {med_abs_diff*1e3:.3f} mA |",
        f"| 滚动 {window}s σ 中位数 | {float(np.nanmedian(roll_std)):.6f} A | {float(np.nanmedian(roll_std))*1e3:.3f} mA |",
        "",
        "## 2. 平台内漂移",
        "",
        "| 指标 | 数值 |",
        "|---|---:|",
        f"| 斜率 | {drift['slope_A_per_s']:.4e} A/s = **{drift['slope_mA_per_min']:.4f} mA/min** |",
        f"| 全程线性漂移量 | **{drift['total_drift_mA']:.3f} mA** |",
        f"| 去趋势残差 σ | **{drift['residual_std_mA']:.3f} mA** |",
        f"| R² | {drift['r2']:.4f} |",
        "",
    ]
    if abs(total_drift) < 0.3 * sI["std"]:
        lines.append("**解读**：平台内线性漂移小于 0.3σ，以随机起伏为主。")
    elif abs(total_drift) < sI["std"]:
        lines.append("**解读**：平台内有轻微缓漂，但仍小于 1σ 起伏。")
    else:
        lines.append("**解读**：平台内线性漂移超过 1σ，报告稳定度时应同时给出漂移率。")
    lines += [
        "",
        "## 3. Allan 偏差（仅平台）",
        "",
    ]
    if allan_rows:
        lines += ["| τ (s) | σ_y (A) | σ_y (mA) |", "|---:|---:|---:|"]
        for tau, a, amA in allan_rows:
            lines.append(f"| {tau:g} | {a:.4e} | {amA:.4f} |")
    else:
        lines.append("数据不足。")
    lines += [
        "",
        "## 4. 鉴频链路（平台）",
        "",
        f"- Δf 均值: {s_dF['mean']/1e6:.4f} MHz；σ = {s_dF['std']/1e3:.2f} kHz；CV = {s_dF['cv_pct']:.4f}%",
        f"- 左峰频率误差 σ: {s_eL['std']/1e3:.2f} kHz；右峰: {s_eR['std']/1e3:.2f} kHz",
        f"- I 的 CV = {sI['cv_pct']:.4f}%；Δf 的 CV = {s_dF['cv_pct']:.4f}%（应同阶）",
        "",
        "## 5. 结论",
        "",
        f"1. 稳态工作点 ≈ **{sI['mean']*1e3:.2f} mA**。",
        f"2. 平台短时稳定度（1σ）≈ **{sI['std']*1e3:.2f} mA**（CV **{sI['cv_pct']:.3f}%**）。",
        f"3. 去趋势后噪声 ≈ **{drift['residual_std_mA']:.2f} mA**；漂移 ≈ **{drift['slope_mA_per_min']:.3f} mA/min**。",
        f"4. 秒级噪声（差分/秒内 std）约 **{diff_rms*1e3:.2f}–{float(np.median(I_std))*1e3:.2f} mA**。",
        "5. 本段适合作为探头在恒定电流附近的稳定性代表指标。",
        "",
        "## 6. 图件",
        "",
        "| 图 | 文件 |",
        "|---|---|",
        "| 1 | `01_plateau_timeseries.png` |",
        "| 2 | `02_plateau_hist_allan.png` |",
        "| 3 | `03_plateau_frequency.png` |",
        "| 4 | `04_plateau_spectrum.png` |",
        "",
        f"输出目录: `{out_dir}`",
    ]
    report = out_dir / "plateau_stability_report.md"
    report.write_text("\n".join(lines), encoding="utf-8")

    print("=== PLATEAU t >", T_CUT_S, "===")
    print("n=", sI["n"], "duration_s=", duration)
    print("I mean/std_mA/cv%:", sI["mean"], sI["std"] * 1e3, sI["cv_pct"])
    print("robust_mA:", sI["robust_sigma"] * 1e3)
    print("drift_mA_per_min:", drift["slope_mA_per_min"], "resid_mA:", drift["residual_std_mA"], "R2:", drift["r2"])
    print("diff_rms_mA:", diff_rms * 1e3, "I_std_med_mA:", float(np.median(I_std)) * 1e3)
    print("allan:", allan_rows)
    print("report:", report)
    for p in sorted(out_dir.glob("*.png")):
        print("fig:", p)


if __name__ == "__main__":
    main()
