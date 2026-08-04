"""Compare current stability (CV = std/mean) of new CSV vs prior plateau."""
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

# Prior plateau result (Excel session 20260729, Elapsed > 620 s)
REF = {
    "label": "20260729 平台\n(t>620 s)",
    "session": "20260729_155533_f0a50700",
    "mean": 2.034009431183155,
    "std": 0.0016810786209946595,
    "n": 561,
    "duration_s": 560.08,
}
REF["cv"] = REF["std"] / REF["mean"]


def cv_stats(I: np.ndarray) -> dict:
    I = np.asarray(I, dtype=float)
    I = I[np.isfinite(I)]
    mean = float(np.mean(I))
    std = float(np.std(I, ddof=1)) if I.size > 1 else 0.0
    return {
        "n": int(I.size),
        "mean": mean,
        "std": std,
        "cv": std / mean if mean != 0 else float("nan"),
        "cv_pct": (std / mean * 100) if mean != 0 else float("nan"),
        "robust_sigma": float(1.4826 * np.median(np.abs(I - np.median(I)))),
        "ptp": float(np.ptp(I)),
        "min": float(np.min(I)),
        "max": float(np.max(I)),
    }


def find_step_plateaus(t: np.ndarray, I: np.ndarray, dt: float, min_duration_s: float = 15.0):
    """Split into plateaus by relative jumps of rolling mean."""
    win = max(5, int(round(2.0 / max(dt, 1e-6))))
    rm = pd.Series(I).rolling(win, center=True, min_periods=3).mean().to_numpy()
    drm = np.abs(np.diff(rm, prepend=rm[0]))
    positive = drm[drm > 0]
    thr = max(5 * float(np.median(positive)) if positive.size else 0.0, 1e-3 * float(np.median(np.abs(rm))))
    step = drm > thr
    bounds = [0]
    for i in range(1, len(step)):
        if step[i]:
            bounds.append(i)
    bounds.append(len(I))

    plateaus = []
    min_n = max(10, int(min_duration_s / max(dt, 1e-6)))
    for a, b in zip(bounds[:-1], bounds[1:]):
        if b - a < min_n:
            continue
        # trim ~0.5 s edges if long enough
        trim = int(round(0.5 / max(dt, 1e-6)))
        if b - a > 2 * trim + 5:
            a2, b2 = a + trim, b - trim
        else:
            a2, b2 = a, b
        seg_I = I[a2:b2]
        seg_t = t[a2:b2]
        st = cv_stats(seg_I)
        st.update(
            {
                "t0": float(seg_t[0]),
                "t1": float(seg_t[-1]),
                "duration_s": float(seg_t[-1] - seg_t[0]),
            }
        )
        plateaus.append(st)
    return plateaus


def main() -> None:
    csv_path = Path(r"C:\Users\zhuzi\Desktop\current_tracking_20260725_121141_a6aba163_2.csv")
    out_dir = Path(__file__).resolve().parent / "compare_cv_20260725_vs_20260729_plateau"
    out_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(csv_path)
    t = df["elapsed_s"].to_numpy(float)
    I = df["current_a"].to_numpy(float)
    mask = (
        df["valid"].to_numpy(bool)
        & (df["left_state"].to_numpy(str) == "LOCKED")
        & (df["right_state"].to_numpy(str) == "LOCKED")
        & np.isfinite(I)
    )
    t0 = t[mask]
    I0 = I[mask]
    if I0.size < 20:
        raise SystemExit("Not enough valid LOCKED samples in CSV")

    dt = float(np.median(np.diff(t0)))
    full = cv_stats(I0)
    full["duration_s"] = float(t0[-1] - t0[0])
    full["label"] = "20260725 CSV\n(全程 valid)"

    plateaus = find_step_plateaus(t0, I0, dt, min_duration_s=15.0)
    plateaus_sorted = sorted(plateaus, key=lambda s: s["cv"])
    # Prefer longest among low-CV half; else pure best CV with duration>=20
    long_enough = [p for p in plateaus if p["duration_s"] >= 20]
    if long_enough:
        # best CV among plateaus with duration >= 20 s
        plateau = min(long_enough, key=lambda s: s["cv"])
        # if a much longer plateau has CV within 2x of best, prefer longer for fairness vs 560s ref
        best_cv = plateau["cv"]
        candidates = [p for p in long_enough if p["cv"] <= 2.0 * best_cv]
        plateau = max(candidates, key=lambda s: s["duration_s"])
        # actually user wants fair stability comparison — use lowest CV plateau with >=20s
        plateau = min(long_enough, key=lambda s: s["cv"])
    elif plateaus_sorted:
        plateau = plateaus_sorted[0]
    else:
        # fallback: best fixed windows
        plateau = None
        for sec in [30, 60]:
            n = max(10, int(round(sec / dt)))
            if n >= len(I0):
                continue
            best = None
            for i in range(0, len(I0) - n + 1, max(1, n // 20)):
                st = cv_stats(I0[i : i + n])
                st["t0"] = float(t0[i])
                st["t1"] = float(t0[i + n - 1])
                st["duration_s"] = float(t0[i + n - 1] - t0[i])
                if best is None or st["cv"] < best["cv"]:
                    best = st
            if best is not None and (plateau is None or best["cv"] < plateau["cv"]):
                plateau = best

    if plateau is None:
        raise SystemExit("Could not identify a plateau in new CSV")

    plateau["label"] = f"20260725 CSV\n平台 t={plateau['t0']:.0f}–{plateau['t1']:.0f}s"
    plateau["session"] = "20260725_121141_a6aba163_2"

    # Also compute best 30s / 60s / ~560s windows by CV for transparency
    window_stats = {}
    for sec in [30, 60, 120]:
        n = max(10, int(round(sec / dt)))
        if n >= len(I0):
            continue
        best = None
        for i in range(0, len(I0) - n + 1, max(1, n // 25)):
            st = cv_stats(I0[i : i + n])
            st["t0"] = float(t0[i])
            st["t1"] = float(t0[i + n - 1])
            if best is None or st["cv"] < best["cv"]:
                best = st
        window_stats[sec] = best

    ratio_new_over_ref = plateau["cv"] / REF["cv"]
    ratio_ref_over_new = REF["cv"] / plateau["cv"]
    better = "20260725 CSV 平台" if plateau["cv"] < REF["cv"] else "20260729 平台"
    worse = "20260729 平台" if plateau["cv"] < REF["cv"] else "20260725 CSV 平台"

    # ---- plots ----
    fig, axes = plt.subplots(2, 1, figsize=(11, 7.2), sharex=False, gridspec_kw={"height_ratios": [1.6, 1.2]})
    ax = axes[0]
    ax.plot(t0, I0, color="#94a3b8", lw=0.8, alpha=0.85, label="valid LOCKED")
    ax.axvspan(plateau["t0"], plateau["t1"], color="#0ea5e9", alpha=0.15, label="selected plateau")
    ax.axhline(plateau["mean"], color="#0ea5e9", ls="--", lw=1.0)
    ax.set_ylabel("current_a")
    ax.set_xlabel("elapsed_s")
    ax.set_title("20260725 CSV — current time series (valid LOCKED)")
    ax.legend(fontsize=8)

    ax = axes[1]
    labels = [REF["label"], plateau["label"], full["label"]]
    cvs = [REF["cv"] * 100, plateau["cv"] * 100, full["cv"] * 100]
    colors = ["#22c55e", "#0ea5e9", "#f97316"]
    bars = ax.bar(labels, cvs, color=colors, edgecolor="white", width=0.65)
    for bar, v in zip(bars, cvs):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(), f"{v:.4f}%", ha="center", va="bottom", fontsize=9)
    ax.set_ylabel("CV = σ / ⟨I⟩  (%)")
    ax.set_title("Stability comparison by CV (std / mean)")
    fig.tight_layout()
    fig.savefig(out_dir / "01_timeseries_and_cv_bars.png")
    plt.close(fig)

    # zoom plateau + hist
    mplat = (t0 >= plateau["t0"]) & (t0 <= plateau["t1"])
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    ax = axes[0]
    ax.plot(t0[mplat], I0[mplat], color="#0ea5e9", lw=1.0)
    ax.axhline(plateau["mean"], color="#22c55e", ls="--", label=f"mean={plateau['mean']:.4g}")
    ax.fill_between(
        [plateau["t0"], plateau["t1"]],
        plateau["mean"] - plateau["std"],
        plateau["mean"] + plateau["std"],
        color="#22c55e",
        alpha=0.15,
        label=f"±1σ (CV={plateau['cv_pct']:.4f}%)",
    )
    ax.set_xlabel("elapsed_s")
    ax.set_ylabel("current_a")
    ax.set_title("Selected plateau zoom")
    ax.legend(fontsize=8)

    ax = axes[1]
    # relative deviation for comparable histogram shape
    rel_ref = (np.random.default_rng(0).normal(0, REF["std"], size=5000)) / REF["mean"] * 100  # illustrative not needed
    # actual: plot relative residual histogram of plateau vs synthetic? better only plateau
    rel = (I0[mplat] - plateau["mean"]) / plateau["mean"] * 100
    ax.hist(rel, bins=35, color="#0ea5e9", alpha=0.9, edgecolor="white")
    ax.axvline(0, color="#22c55e", ls="--")
    ax.axvline(-plateau["cv_pct"], color="#94a3b8", ls=":")
    ax.axvline(plateau["cv_pct"], color="#94a3b8", ls=":", label=f"±CV = ±{plateau['cv_pct']:.4f}%")
    ax.set_xlabel("(I − ⟨I⟩) / ⟨I⟩  (%)")
    ax.set_ylabel("Counts")
    ax.set_title("Plateau relative fluctuation")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(out_dir / "02_plateau_zoom_hist.png")
    plt.close(fig)

    # comparison table figure
    fig, ax = plt.subplots(figsize=(10, 3.8))
    ax.axis("off")
    rows = [
        ["数据集", "20260729 平台 t>620s", "20260725 CSV 平台", "20260725 CSV 全程"],
        ["均值 ⟨I⟩", f"{REF['mean']:.6g}", f"{plateau['mean']:.6g}", f"{full['mean']:.6g}"],
        ["标准差 σ", f"{REF['std']:.6g}", f"{plateau['std']:.6g}", f"{full['std']:.6g}"],
        ["CV=σ/μ", f"{REF['cv']:.6e}", f"{plateau['cv']:.6e}", f"{full['cv']:.6e}"],
        ["CV (%)", f"{REF['cv']*100:.4f}%", f"{plateau['cv_pct']:.4f}%", f"{full['cv_pct']:.4f}%"],
        ["样本数 n", f"{REF['n']}", f"{plateau['n']}", f"{full['n']}"],
        ["时长 (s)", f"{REF['duration_s']:.1f}", f"{plateau['duration_s']:.1f}", f"{full['duration_s']:.1f}"],
    ]
    table = ax.table(cellText=rows, loc="center", cellLoc="center")
    table.auto_set_font_size(False)
    table.set_fontsize(9)
    table.scale(1.15, 1.45)
    for j in range(4):
        table[(0, j)].set_facecolor("#e2e8f0")
    ax.set_title("CV stability comparison", pad=12)
    fig.tight_layout()
    fig.savefig(out_dir / "03_comparison_table.png")
    plt.close(fig)

    # markdown report
    lines = [
        "# 电流稳定性对比（指标：CV = 标准差 / 均值）",
        "",
        "## 对比对象",
        "",
        f"1. **参考（之前）**: Excel `current_tracking_20260729_155533_f0a50700`，**稳态平台 Elapsed > 620 s**",
        f"2. **新数据**: CSV `{csv_path.name}`，valid 且双峰 LOCKED",
        "",
        "相对稳定度定义：",
        "",
        r"$$\mathrm{CV}=\frac{\sigma(I)}{\langle I \rangle}$$",
        "",
        "（无量纲；电流绝对单位不同时仍可公平比较。）",
        "",
        "## 结果总表",
        "",
        "| 数据集 | ⟨I⟩ | σ | **CV** | **CV (%)** | n | 时长 (s) |",
        "|---|---:|---:|---:|---:|---:|---:|",
        f"| 20260729 平台 t>620s | {REF['mean']:.6g} | {REF['std']:.6g} | {REF['cv']:.6e} | **{REF['cv']*100:.4f}%** | {REF['n']} | {REF['duration_s']:.1f} |",
        f"| 20260725 CSV 平台 | {plateau['mean']:.6g} | {plateau['std']:.6g} | {plateau['cv']:.6e} | **{plateau['cv_pct']:.4f}%** | {plateau['n']} | {plateau['duration_s']:.1f} |",
        f"| 20260725 CSV 全程 valid | {full['mean']:.6g} | {full['std']:.6g} | {full['cv']:.6e} | **{full['cv_pct']:.4f}%** | {full['n']} | {full['duration_s']:.1f} |",
        "",
        "## 平台 vs 平台（主对比）",
        "",
        f"- 新 CSV 平台时间窗：elapsed **{plateau['t0']:.2f} – {plateau['t1']:.2f} s**（{plateau['duration_s']:.1f} s）",
        f"- CV(新平台) / CV(旧平台) = **{ratio_new_over_ref:.3f}**",
        f"- CV(旧平台) / CV(新平台) = **{ratio_ref_over_new:.3f}**",
        f"- **更稳的一方（CV 更小）: {better}**",
        f"- 相对差异：{worse} 的 CV 约为另一方的 **{max(ratio_new_over_ref, ratio_ref_over_new):.2f}×**",
        "",
        "## 说明",
        "",
        "- 新 CSV **全程** CV 很大，是因为电流有台阶/大幅变化，**不能**与旧平台直接比全程 σ。",
        "- 公平比较采用新数据中 **台阶分割后 CV 最低且 ≥20 s 的平台**。",
        "- 旧数据同样是平台段（t>620 s），因此两边都是“稳态段上的相对起伏”。",
        "",
        "### 新 CSV 滑动窗最优 CV（补充）",
        "",
    ]
    if window_stats:
        lines.append("| 窗长 | 最低 CV (%) | 窗内 mean | 窗内 σ |")
        lines.append("|---:|---:|---:|---:|")
        for sec, st in window_stats.items():
            if st is None:
                continue
            lines.append(
                f"| {sec}s | {st['cv_pct']:.4f}% | {st['mean']:.6g} | {st['std']:.6g} |"
            )
        lines.append("")

    if plateaus_sorted:
        lines.append("### 新 CSV 检测到的主要平台（按 CV 排序，前 6）")
        lines.append("")
        lines.append("| t0–t1 (s) | 时长 (s) | mean | σ | CV (%) |")
        lines.append("|---|---:|---:|---:|---:|")
        for p in plateaus_sorted[:6]:
            lines.append(
                f"| {p['t0']:.1f}–{p['t1']:.1f} | {p['duration_s']:.1f} | {p['mean']:.6g} | {p['std']:.6g} | {p['cv_pct']:.4f}% |"
            )
        lines.append("")

    lines += [
        "## 图件",
        "",
        "| 图 | 文件 |",
        "|---|---|",
        "| 1 | `01_timeseries_and_cv_bars.png` |",
        "| 2 | `02_plateau_zoom_hist.png` |",
        "| 3 | `03_comparison_table.png` |",
        "",
        f"输出目录: `{out_dir}`",
    ]
    report = out_dir / "cv_comparison_report.md"
    report.write_text("\n".join(lines), encoding="utf-8")

    print("=== CV COMPARISON ===")
    print("REF: mean=%.6g std=%.6g CV%%=%.4f n=%d" % (REF["mean"], REF["std"], REF["cv"] * 100, REF["n"]))
    print(
        "NEW plateau: mean=%.6g std=%.6g CV%%=%.4f n=%d t=%.1f-%.1f"
        % (plateau["mean"], plateau["std"], plateau["cv_pct"], plateau["n"], plateau["t0"], plateau["t1"])
    )
    print("NEW full: mean=%.6g std=%.6g CV%%=%.4f n=%d" % (full["mean"], full["std"], full["cv_pct"], full["n"]))
    print("CV_new/CV_ref = %.4f" % ratio_new_over_ref)
    print("CV_ref/CV_new = %.4f" % ratio_ref_over_new)
    print("better:", better)
    print("report:", report)
    for p in sorted(out_dir.glob("*.png")):
        print("fig:", p)


if __name__ == "__main__":
    main()
