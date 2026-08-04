"""
Interactive A/B pitch → four-NV ODMR spectrum viewer (Streamlit).

Includes Wuhan geomagnetic field + (100) face-up mounting.

Run from repo root:
  python -m streamlit run scripts/odmr_pitch_ui/app.py
Or:
  scripts\\start_odmr_pitch_ui.bat
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import plotly.graph_objects as go
import streamlit as st

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from physics import (  # noqa: E402
    DEFAULT_B0_MT,
    DEFAULT_FWHM_MHZ,
    D_MHZ,
    GAMMA_MHZ_PER_MT,
    MOUNT_100_FACE_UP,
    NV_LABELS,
    WUHAN_SITE,
    GeomagneticSite,
    StageModel,
    coil_field_lab_mT,
    frequencies_mhz,
    odmr_spectrum,
    projections_vs_axis,
    summarize,
    unified_freq_axis_mhz,
)


def _f64_list(a) -> list[float]:
    """Pure Python floats — avoids Plotly→pandas encoder paths."""
    arr = np.asarray(a, dtype=np.float64).ravel()
    return [float(v) for v in arr]


def _show_plotly(fig: go.Figure, *, height: int = 480) -> None:
    """
    Display Plotly figure via st.plotly_chart only.

    Do NOT use fig.to_html() here: under Streamlit it can trigger a broken
    partial pandas import (NaT circular-import error).
    """
    # Ensure layout height
    fig.update_layout(height=height)
    config = {
        "displayModeBar": True,
        "scrollZoom": True,
        "displaylogo": False,
    }
    st.plotly_chart(fig, use_container_width=True, config=config)


def _odmr_plotly_figure(
    freq_mhz: np.ndarray,
    traces: list[tuple[np.ndarray, str, str, str]],
    *,
    marker_freqs: list[tuple[float, str, str]] | None = None,
    title: str = "CW ODMR（悬停读数 · 框选缩放 · 双击复位）",
) -> go.Figure:
    """
    traces: (y, name, color, dash) with dash in solid|dash|dot
    """
    x = np.asarray(freq_mhz, dtype=np.float64)
    step = max(1, len(x) // 2000)
    x_list = _f64_list(x[::step])

    fig = go.Figure()
    y_mins, y_maxs = [], []
    for y, name, color, dash in traces:
        y_arr = np.asarray(y, dtype=np.float64)[::step]
        y_mins.append(float(np.min(y_arr)))
        y_maxs.append(float(np.max(y_arr)))
        line_style: dict = {"color": color, "width": 2}
        if dash in ("dash", "dot", "dashdot"):
            line_style["dash"] = dash
        fig.add_trace(
            go.Scatter(
                x=x_list,
                y=_f64_list(y_arr),
                mode="lines",
                name=str(name),
                line=line_style,
                hovertemplate=(
                    "<b>%{fullData.name}</b><br>"
                    "微波频率 f = <b>%{x:.3f}</b> MHz<br>"
                    "归一化 PL = <b>%{y:.5f}</b><br>"
                    "<extra></extra>"
                ),
            )
        )

    if marker_freqs and y_mins:
        y0, y1 = min(y_mins), max(y_maxs)
        mx: list[float | None] = []
        my: list[float | None] = []
        for f0, _lab, _color in marker_freqs:
            mx.extend([float(f0), float(f0), None])
            my.extend([y0, y1, None])
        fig.add_trace(
            go.Scatter(
                x=mx,
                y=my,
                mode="lines",
                name="共振标记",
                line=dict(color="#888888", width=1, dash="dot"),
                hoverinfo="skip",
                showlegend=True,
            )
        )

    fig.update_layout(
        title=title,
        xaxis_title="微波频率 f (MHz)",
        yaxis_title="归一化 PL (arb.)",
        hovermode="closest",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0.0),
        margin=dict(l=60, r=20, t=70, b=50),
        height=480,
        template="plotly_white",
        dragmode="zoom",
    )
    fig.update_xaxes(rangeslider=dict(visible=True, thickness=0.08))
    return fig


def _proj_vs_a_plotly(
    angles: np.ndarray,
    proj_curve: np.ndarray,
    *,
    current_a: float,
    ref_mT: float,
) -> go.Figure:
    colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728"]
    ang = np.asarray(angles, dtype=np.float64)
    curve = np.asarray(proj_curve, dtype=np.float64)
    fig = go.Figure()
    for i, lab in enumerate(NV_LABELS):
        fig.add_trace(
            go.Scatter(
                x=_f64_list(ang),
                y=_f64_list(curve[:, i]),
                mode="lines",
                name=str(lab),
                line=dict(color=colors[i], width=2),
                hovertemplate=(
                    f"<b>{lab}</b><br>"
                    "A = <b>%{x:.3f}</b> °<br>"
                    "|B∥| = <b>%{y:.5f}</b> mT"
                    "<extra></extra>"
                ),
            )
        )
    a0, a1 = float(ang.min()), float(ang.max())
    fig.add_trace(
        go.Scatter(
            x=[a0, a1],
            y=[float(ref_mT), float(ref_mT)],
            mode="lines",
            name="B0/√3 (coil)",
            line=dict(color="black", width=1, dash="dash"),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=[float(current_a), float(current_a)],
            y=[float(curve.min()), float(curve.max())],
            mode="lines",
            name=f"A={current_a:.2f}°",
            line=dict(color="red", width=1, dash="dot"),
        )
    )
    fig.update_layout(
        title="|B∥| vs A",
        xaxis_title="A 轴俯仰 (°)",
        yaxis_title="|B∥| (mT)",
        hovermode="closest",
        height=400,
        template="plotly_white",
        dragmode="zoom",
        legend=dict(orientation="h", y=1.12),
        margin=dict(l=60, r=20, t=60, b=50),
    )
    return fig


def _bar_plotly(
    projections_mT: np.ndarray,
    *,
    delta_f_mhz: np.ndarray,
    ref_mT: float,
) -> go.Figure:
    colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728"]
    labels = [f"NV{i+1}" for i in range(4)]
    projs = _f64_list(projections_mT)
    dfs = _f64_list(delta_f_mhz)
    hover = [
        f"{NV_LABELS[i]} |B∥|={projs[i]:.5f} mT Δf={dfs[i]:.3f} MHz"
        for i in range(4)
    ]
    fig = go.Figure(
        data=[
            go.Bar(
                x=labels,
                y=projs,
                marker_color=colors,
                text=[f"{v:.4f}" for v in projs],
                textposition="outside",
                name="|B∥|",
                hovertext=hover,
                hoverinfo="text",
            ),
            go.Scatter(
                x=labels,
                y=[float(ref_mT)] * 4,
                mode="lines",
                name="B0/√3 (coil)",
                line=dict(color="black", width=1, dash="dash"),
            ),
        ]
    )
    fig.update_layout(
        title="四族 |B∥|",
        xaxis_title="NV 家族",
        yaxis_title="|B∥| (mT)",
        height=400,
        template="plotly_white",
        dragmode="zoom",
        margin=dict(l=60, r=20, t=60, b=50),
        yaxis=dict(rangemode="tozero"),
    )
    return fig


st.set_page_config(
    page_title="NV ODMR Pitch Sim",
    page_icon="🧲",
    layout="wide",
)

st.title("NV 四族 ODMR · A/B 俯仰交互仿真")
st.caption(
    "实验室：**武汉** · 亥姆霍兹 **B_coil ∥ +z（竖直向上）** · "
    "金刚石 **(100) 上表面水平**，[100] 沿 lab +z · "
    f"默认 Γ = **{DEFAULT_FWHM_MHZ:.0f} MHz**、B0 = **{DEFAULT_B0_MT:.0f} mT**（0721 实测）· "
    "可选叠加 **地磁场**。"
)

with st.sidebar:
    st.header("姿态")
    col_ra1, col_ra2 = st.columns(2)
    with col_ra1:
        a_min = st.number_input("A 滑块最小", value=-6.0, step=1.0, format="%.1f")
    with col_ra2:
        a_max = st.number_input("A 滑块最大", value=6.0, step=1.0, format="%.1f")
    col_rb1, col_rb2 = st.columns(2)
    with col_rb1:
        b_min = st.number_input("B 滑块最小", value=-4.0, step=1.0, format="%.1f")
    with col_rb2:
        b_max = st.number_input("B 滑块最大", value=4.0, step=1.0, format="%.1f")

    if a_min >= a_max:
        a_min, a_max = -6.0, 6.0
    if b_min >= b_max:
        b_min, b_max = -4.0, 4.0

    alpha = st.slider("A 轴俯仰 alpha (deg)", float(a_min), float(a_max), 0.0, 0.05)
    beta = st.slider("B 轴俯仰 beta (deg)", float(b_min), float(b_max), 0.0, 0.05)

    with st.expander("R 轴 / 符号", expanded=False):
        gamma = st.slider("R 轴 gamma (deg)", -180.0, 180.0, 0.0, 0.5)
        flip_a = st.checkbox("翻转 A 轴符号 (alpha_sign = -1)", value=False)
        flip_b = st.checkbox("翻转 B 轴符号 (beta_sign = -1)", value=False)
        flip_r = st.checkbox("翻转 R 轴符号 (gamma_sign = -1)", value=False)

    st.header("物理量")
    B0 = st.number_input(
        "线圈 B0 (mT, 沿 +z 向上)",
        min_value=0.0,
        max_value=50.0,
        value=float(DEFAULT_B0_MT),
        step=0.1,
        key="b0_mT_lab_v3",
        help=(
            "亥姆霍兹中心场，竖直向上。"
            f"默认 {DEFAULT_B0_MT:.0f} mT ≈ 0721 @15A（无地磁时 B∥≈6.4 mT）。"
        ),
    )
    fwhm = st.number_input(
        "线宽 FWHM Γ (MHz)",
        min_value=0.1,
        max_value=80.0,
        value=float(DEFAULT_FWHM_MHZ),
        step=0.5,
        key="fwhm_mhz_lab_v3",
    )
    contrast = st.number_input(
        "单族对比度",
        min_value=0.001,
        max_value=0.25,
        value=0.02,
        step=0.005,
        format="%.3f",
        key="contrast_lab_v3",
    )

    st.header("地磁场（武汉）")
    include_earth = st.checkbox(
        "叠加地磁场",
        value=True,
        key="include_earth_v3",
        help="B_total = B_coil(+z) + B_earth(Wuhan)",
    )
    with st.expander("地磁参数 / 台架朝向", expanded=include_earth):
        st.markdown(
            f"**默认站点**：{WUHAN_SITE.name}  \n"
            f"纬度 **{WUHAN_SITE.lat_deg:.4f}°N**，经度 **{WUHAN_SITE.lon_deg:.4f}°E**，"
            f"海拔 ~{WUHAN_SITE.alt_m:.0f} m  \n"
            f"历元：{WUHAN_SITE.epoch}（主磁场，不含局部铁磁扰动）"
        )
        use_custom = st.checkbox("自定义 F / I / D", value=False, key="custom_geo_v3")
        if use_custom:
            F_nT = st.number_input(
                "总强度 F (nT)",
                min_value=20000.0,
                max_value=70000.0,
                value=float(WUHAN_SITE.F_nT),
                step=50.0,
                key="F_nT_v3",
            )
            I_deg = st.number_input(
                "磁倾角 I (°，向下为正)",
                min_value=-90.0,
                max_value=90.0,
                value=float(WUHAN_SITE.inclination_deg),
                step=0.1,
                key="I_deg_v3",
            )
            D_deg = st.number_input(
                "磁偏角 D (°，东偏为正)",
                min_value=-30.0,
                max_value=30.0,
                value=float(WUHAN_SITE.declination_deg),
                step=0.1,
                key="D_deg_v3",
            )
        else:
            F_nT = float(WUHAN_SITE.F_nT)
            I_deg = float(WUHAN_SITE.inclination_deg)
            D_deg = float(WUHAN_SITE.declination_deg)

        lab_yaw = st.slider(
            "台架方位 yaw (°)",
            -180.0,
            180.0,
            0.0,
            1.0,
            key="lab_yaw_v3",
            help="lab +x 相对地理北的转角：0 = 光学台 +x 指真北；正值 = 向东转。",
        )
        st.caption(
            f"默认元素：F = {WUHAN_SITE.F_nT:.0f} nT ({WUHAN_SITE.F_nT*1e-3:.2f} µT)，"
            f"I = {WUHAN_SITE.inclination_deg:.1f}°，D = {WUHAN_SITE.declination_deg:.1f}°"
        )

    st.header("地磁显示增强")
    earth_scale = st.slider(
        "地磁矢量放大倍数（教学）",
        min_value=1.0,
        max_value=50.0,
        value=1.0,
        step=1.0,
        key="earth_scale_v5",
        help=(
            "真实武汉地磁 |B|≈50 µT，相对默认线圈 11 mT 仅约 0.5%。"
            "Γ≈14 MHz 时全谱几乎重合属正常。放大倍数>1 仅用于看清谱形，非物理增益。"
        ),
    )
    st.header("显示")
    show_markers = st.checkbox("标出各 NV 共振位置（竖线）", value=True, key="show_mk_v5")
    show_spec_coil = st.checkbox("谱线：仅线圈", value=True, key="show_spec_coil_v5")
    show_spec_total = st.checkbox(
        "谱线：线圈+地磁（总场）",
        value=True,
        key="show_spec_total_v5",
    )
    show_spec_earth_only = st.checkbox(
        "谱线：仅地磁（线圈 B0=0）",
        value=True,
        key="show_spec_earth_only_v5",
        help="只看地磁时，劈裂仅 ~MHz 量级，谷在 D≈2870 MHz 附近。",
    )
    show_diff = st.checkbox(
        "差分谱：(线圈+地磁) − (仅线圈)",
        value=True,
        key="show_diff_v5",
        help="放大地磁引起的微弱谱形差（物理 scale=1 时全谱差也很小）。",
    )
    show_zoom = st.checkbox(
        "f− / f+ 局部放大",
        value=True,
        key="show_zoom_v5",
    )
    show_ref = st.checkbox("叠 A=B=0 总场参考", value=False, key="show_ref_v5")
    show_proj_vs_a = st.checkbox("显示 |B_par| vs A", value=True, key="show_vs_a_v5")

site = GeomagneticSite(
    F_nT=float(F_nT),
    inclination_deg=float(I_deg),
    declination_deg=float(D_deg),
)
earth_info = site.summary_dict(lab_yaw_deg=float(lab_yaw))
B_earth = site.lab_vector_mT(float(lab_yaw))
B_coil = coil_field_lab_mT(float(B0))
B_total = B_coil + B_earth if include_earth else B_coil

model = StageModel(
    alpha_sign=-1.0 if flip_a else 1.0,
    beta_sign=-1.0 if flip_b else 1.0,
    gamma_sign=-1.0 if flip_r else 1.0,
    mount_matrix=MOUNT_100_FACE_UP.copy(),
)

coil_kw = dict(include_earth=False, earth_scale=1.0)
total_kw = dict(
    include_earth=True,
    site=site,
    lab_yaw_deg=float(lab_yaw),
    earth_scale=float(earth_scale),
)
earth_only_kw = dict(
    include_earth=True,
    site=site,
    lab_yaw_deg=float(lab_yaw),
    earth_scale=float(earth_scale),
)

# Table / metrics follow sidebar "叠加地磁场" switch
proj_kw = total_kw if include_earth else coil_kw
projs = model.projections(float(B0), float(alpha), float(beta), float(gamma), **proj_kw)
summary = summarize(projs, float(B0))

# Three physical cases for spectrum overlays
projs_coil = model.projections(
    float(B0), float(alpha), float(beta), float(gamma), **coil_kw
)
projs_total = model.projections(
    float(B0), float(alpha), float(beta), float(gamma), **total_kw
)
# Earth only: coil off
projs_geo = model.projections(0.0, float(alpha), float(beta), float(gamma), **earth_only_kw)

summary_coil = summarize(projs_coil, float(B0))
summary_total = summarize(projs_total, float(B0))
summary_geo = summarize(projs_geo, max(float(B0), 1e-6), ref_mT=float(np.mean(projs_geo)) if np.any(projs_geo) else 1e-6)

freq = unified_freq_axis_mhz(
    projs_coil, projs_total, projs_geo, fwhm_mhz=float(fwhm), n_points=5000
)
_, pl_coil = odmr_spectrum(
    projs_coil, fwhm_mhz=float(fwhm), contrast_per_class=float(contrast), freq_mhz=freq
)
_, pl_total = odmr_spectrum(
    projs_total, fwhm_mhz=float(fwhm), contrast_per_class=float(contrast), freq_mhz=freq
)
_, pl_geo = odmr_spectrum(
    projs_geo, fwhm_mhz=float(fwhm), contrast_per_class=float(contrast), freq_mhz=freq
)
pl_diff = pl_total - pl_coil  # residual caused by earth (at given scale)

pl_ref_total = None
if show_ref:
    projs0_t = model.projections(float(B0), 0.0, 0.0, float(gamma), **total_kw)
    _, pl_ref_total = odmr_spectrum(
        projs0_t,
        fwhm_mhz=float(fwhm),
        contrast_per_class=float(contrast),
        freq_mhz=freq,
    )

# Alias for older caption code
summary_earth = summary_total
pl_earth = pl_total

# --- field metrics ---
c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("A / B (°)", f"{alpha:.2f} / {beta:.2f}")
c2.metric("|B_par| mean", f"{summary.mean_mT:.4f} mT")
c3.metric("|B_par| std", f"{summary.std_mT:.4f} mT")
c4.metric("spread/(B0/√3)", f"{100 * summary.spread_rel:.3f} %")
c5.metric("|B_earth|", f"{np.linalg.norm(B_earth)*1e3:.2f} µT")
c6.metric("|B_total|", f"{np.linalg.norm(B_total):.4f} mT")

deg_ok = summary.std_mT < max(0.01 * max(float(B0), 1e-6) / np.sqrt(3), 1e-4)
earth_note = "地磁 **开**" if include_earth else "地磁 **关**"
st.info(
    f"{earth_note} · 简并参考（仅线圈）B0/√3 = **{summary.degenerate_ref_mT:.4f} mT** · "
    f"簇数 ≈ **{summary.n_unique_clusters}** · "
    f"{'近似四族简并' if deg_ok else '已离开简并 / 地磁破缺简并'} · "
    f"D={D_MHZ:.0f} MHz, γ/2π={GAMMA_MHZ_PER_MT:.0f} MHz/mT"
)

# Earth field panel
with st.expander("地磁场矢量（lab：+x 北, +y 东, +z 上）", expanded=include_earth):
    e1, e2, e3 = st.columns(3)
    e1.markdown(
        f"""
**站点**  
- {earth_info['name']}  
- ({earth_info['lat_deg']:.4f}°N, {earth_info['lon_deg']:.4f}°E)  
- F = **{earth_info['F_nT']:.0f} nT** = **{earth_info['F_uT']:.2f} µT**  
- I = **{earth_info['inclination_deg']:.2f}°**（下倾）  
- D = **{earth_info['declination_deg']:.2f}°**（西偏为负）  
- yaw = **{lab_yaw:.1f}°**
"""
    )
    e2.markdown(
        f"""
**地理 NED (mT)**  
- B_N = {earth_info['B_N_mT']:.6f}  
- B_E = {earth_info['B_E_mT']:.6f}  
- B_D = {earth_info['B_D_mT']:.6f}（下）  
- B_U = {earth_info['B_U_mT']:.6f}（上）
"""
    )
    e3.markdown(
        f"""
**Lab 分量 (mT)**  
- B_x (N′) = **{earth_info['B_lab_x_mT']:.6f}**  
- B_y (E′) = **{earth_info['B_lab_y_mT']:.6f}**  
- B_z (Up) = **{earth_info['B_lab_z_mT']:.6f}**  

**线圈** B_coil = (0, 0, {float(B0):.4f}) mT  
**合成** |B| = {np.linalg.norm(B_total):.4f} mT
"""
    )
    st.caption(
        "主磁场模型量级（IGRF/WMM 类）；未含建筑物钢筋、设备铁磁等局域异常。"
        "台架若未指北，请调 yaw。"
    )

# --- interactive ODMR spectrum ---
st.subheader("CW ODMR 谱（交互）")

# Why earth is hard to see at physical scale
B_e_uT = float(np.linalg.norm(B_earth) * 1e3 * earth_scale)
B_c_mT = float(B0)
ratio = (B_e_uT * 1e-3) / max(B_c_mT, 1e-12)
st.info(
    f"武汉 |B_earth|≈**{np.linalg.norm(B_earth)*1e3:.1f} µT**"
    f"{' ×'+str(int(earth_scale))+'（教学放大）' if earth_scale > 1 else ''}；"
    f"线圈 B0=**{B_c_mT:.3f} mT**；|B_e|/B0≈**{100*ratio:.3f}%**。  \n"
    f"仅地磁时 Zeeman 劈裂 2γ|B∥| 仅 **~{2*GAMMA_MHZ_PER_MT*float(np.mean(projs_geo)):.2f} MHz** 量级，"
    f"而 Γ=**{float(fwhm):.1f} MHz** → 谷堆在 **D≈{D_MHZ:.0f} MHz** 附近，不是线圈那种百 MHz 双峰。  \n"
    f"线圈+地磁相对仅线圈：族间 |B∥| spread 差约 "
    f"**{(summary_total.spread_mT - summary_coil.spread_mT)*1e3:.2f} µT** "
    f"（Δf 差 ~**{2*GAMMA_MHZ_PER_MT*(summary_total.spread_mT-summary_coil.spread_mT):.2f} MHz**），"
    f"全谱几乎重合属正常 → 请看 **差分谱** 与 **f± 放大**。"
)

traces: list[tuple[np.ndarray, str, str, str]] = []
pose = f"A={alpha:.2f}°,B={beta:.2f}°"
if show_spec_coil:
    traces.append((pl_coil, f"仅线圈 · {pose}", "#2ca02c", "dash"))
if show_spec_total:
    tag = f"×{earth_scale:.0f}" if earth_scale != 1 else ""
    traces.append(
        (pl_total, f"线圈+地磁{tag} · {pose}", "#1f77b4", "solid")
    )
if show_spec_earth_only:
    tag = f"×{earth_scale:.0f}" if earth_scale != 1 else ""
    traces.append(
        (pl_geo, f"仅地磁{tag} · {pose} · B0=0", "#d62728", "dot")
    )
if pl_ref_total is not None:
    traces.append((pl_ref_total, "线圈+地磁 · A=B=0", "#9467bd", "dot"))

if not traces:
    st.warning("请在侧栏至少勾选一条 ODMR 谱线。")
else:
    markers: list[tuple[float, str, str]] | None = None
    if show_markers:
        colors = ["#d62728", "#ff7f0e", "#2ca02c", "#9467bd"]
        markers = []
        # Mark total-field family resonances (what dual-peak tracking sees in lab)
        for i in range(4):
            markers.append(
                (float(summary_total.f_minus_mhz[i]), f"f− T{i+1}", colors[i])
            )
            markers.append(
                (float(summary_total.f_plus_mhz[i]), f"f+ T{i+1}", colors[i])
            )
        # Also mark pure-earth resonances (near D)
        for i in range(4):
            markers.append(
                (float(summary_geo.f_minus_mhz[i]), f"f− E{i+1}", "#8c564b")
            )
            markers.append(
                (float(summary_geo.f_plus_mhz[i]), f"f+ E{i+1}", "#8c564b")
            )

    df_t = float(np.mean(summary_total.delta_f_mhz))
    df_c = float(np.mean(summary_coil.delta_f_mhz))
    df_g = float(np.mean(summary_geo.delta_f_mhz))
    st.caption(
        f"mean Δf：仅线圈 **{df_c:.3f}** · 线圈+地磁 **{df_t:.3f}** · 仅地磁 **{df_g:.3f}** MHz · "
        f"(总−线圈)= **{df_t-df_c:.3f} MHz**"
    )

    try:
        fig_odmr = _odmr_plotly_figure(freq, traces, marker_freqs=markers)
        _show_plotly(fig_odmr, height=520)
    except Exception as exc:
        st.error(f"ODMR 图绘制失败：{exc}")
        st.exception(exc)

# Difference spectrum
if show_diff:
    st.subheader("差分谱 ΔPL = PL(线圈+地磁) − PL(仅线圈)")
    st.caption(
        "纵轴偏离 0 的位置 = 地磁改变荧光的地方。"
        "物理 scale=1 时幅度很小；可把侧栏「地磁放大」调到 10–30 看清形状。"
    )
    try:
        fig_d = go.Figure(
            data=[
                go.Scatter(
                    x=_f64_list(freq),
                    y=_f64_list(pl_diff),
                    mode="lines",
                    name="ΔPL",
                    line=dict(color="#e377c2", width=2),
                    hovertemplate=(
                        "f=%{x:.3f} MHz<br>ΔPL=%{y:.6f}<br>"
                        "正/负：总场相对仅线圈的 PL 增减"
                        "<extra></extra>"
                    ),
                ),
                go.Scatter(
                    x=[float(freq[0]), float(freq[-1])],
                    y=[0.0, 0.0],
                    mode="lines",
                    name="0",
                    line=dict(color="gray", width=1, dash="dash"),
                    hoverinfo="skip",
                ),
            ]
        )
        fig_d.update_layout(
            xaxis_title="微波频率 f (MHz)",
            yaxis_title="ΔPL (arb.)",
            height=320,
            template="plotly_white",
            dragmode="zoom",
            margin=dict(l=60, r=20, t=30, b=50),
        )
        _show_plotly(fig_d, height=320)
    except Exception as exc:
        st.error(f"差分谱失败：{exc}")

# Zoom around coil f- / f+
if show_zoom and float(B0) > 0:
    st.subheader("f− / f+ 局部放大（看地磁引起的谷位移）")
    fm_c = float(np.mean(summary_coil.f_minus_mhz))
    fp_c = float(np.mean(summary_coil.f_plus_mhz))
    half_win = max(float(fwhm) * 3.0, 40.0)
    col_z1, col_z2 = st.columns(2)
    for col, f_center, title in (
        (col_z1, fm_c, "低频支 f− 附近"),
        (col_z2, fp_c, "高频支 f+ 附近"),
    ):
        with col:
            m = (freq >= f_center - half_win) & (freq <= f_center + half_win)
            if not np.any(m):
                st.write("无数据窗口")
                continue
            fig_z = go.Figure()
            if show_spec_coil:
                fig_z.add_trace(
                    go.Scatter(
                        x=_f64_list(freq[m]),
                        y=_f64_list(pl_coil[m]),
                        mode="lines",
                        name="仅线圈",
                        line=dict(color="#2ca02c", width=2, dash="dash"),
                    )
                )
            if show_spec_total:
                fig_z.add_trace(
                    go.Scatter(
                        x=_f64_list(freq[m]),
                        y=_f64_list(pl_total[m]),
                        mode="lines",
                        name="线圈+地磁",
                        line=dict(color="#1f77b4", width=2),
                    )
                )
            # family sticks for total field
            for i in range(4):
                for f0, lab in (
                    (float(summary_total.f_minus_mhz[i]), f"T{i+1}−"),
                    (float(summary_total.f_plus_mhz[i]), f"T{i+1}+"),
                ):
                    if f_center - half_win <= f0 <= f_center + half_win:
                        fig_z.add_vline(
                            x=f0, line_width=1, line_dash="dot", line_color="#999"
                        )
            fig_z.update_layout(
                title=title,
                xaxis_title="f (MHz)",
                yaxis_title="PL",
                height=340,
                template="plotly_white",
                dragmode="zoom",
                legend=dict(orientation="h", y=1.12),
                margin=dict(l=50, r=10, t=50, b=40),
            )
            try:
                _show_plotly(fig_z, height=340)
            except Exception:
                # vline may fail in some plotly builds — retry without
                fig_z = go.Figure(
                    data=[
                        go.Scatter(
                            x=_f64_list(freq[m]),
                            y=_f64_list(pl_coil[m]),
                            mode="lines",
                            name="仅线圈",
                            line=dict(color="#2ca02c", dash="dash"),
                        ),
                        go.Scatter(
                            x=_f64_list(freq[m]),
                            y=_f64_list(pl_total[m]),
                            mode="lines",
                            name="线圈+地磁",
                            line=dict(color="#1f77b4"),
                        ),
                    ]
                )
                fig_z.update_layout(title=title, height=340, template="plotly_white")
                _show_plotly(fig_z, height=340)

# Resonance comparison table
st.subheader("各 NV 族共振频率对照（MHz）")
res_rows = []
for i, lab in enumerate(NV_LABELS):
    res_rows.append(
        {
            "family": lab,
            "|B∥|_coil (mT)": float(projs_coil[i]),
            "|B∥|_total (mT)": float(projs_total[i]),
            "|B∥|_earth (mT)": float(projs_geo[i]),
            "f−_coil": float(summary_coil.f_minus_mhz[i]),
            "f−_total": float(summary_total.f_minus_mhz[i]),
            "δf− (tot−coil)": float(
                summary_total.f_minus_mhz[i] - summary_coil.f_minus_mhz[i]
            ),
            "f+_coil": float(summary_coil.f_plus_mhz[i]),
            "f+_total": float(summary_total.f_plus_mhz[i]),
            "δf+ (tot−coil)": float(
                summary_total.f_plus_mhz[i] - summary_coil.f_plus_mhz[i]
            ),
            "f−_earth_only": float(summary_geo.f_minus_mhz[i]),
            "f+_earth_only": float(summary_geo.f_plus_mhz[i]),
        }
    )
st.dataframe(res_rows, use_container_width=True, hide_index=True)

# --- table + bar ---
left, right = st.columns([1.2, 1.0])

with left:
    st.subheader("四族投影与共振")
    # Avoid pandas entirely (prevents Plotly/Streamlit circular-import issues).
    rows = []
    for i, lab in enumerate(NV_LABELS):
        rows.append(
            {
                "family": lab,
                "|B_par| (mT)": float(summary.projections_mT[i]),
                "delta_f (MHz)": float(summary.delta_f_mhz[i]),
                "f- (MHz)": float(summary.f_minus_mhz[i]),
                "f+ (MHz)": float(summary.f_plus_mhz[i]),
            }
        )
    st.dataframe(rows, use_container_width=True, hide_index=True)

with right:
    st.subheader("|B∥| 柱状图（交互）")
    try:
        fig_bar = _bar_plotly(
            summary.projections_mT,
            delta_f_mhz=summary.delta_f_mhz,
            ref_mT=float(summary.degenerate_ref_mT),
        )
        _show_plotly(fig_bar, height=420)
    except Exception as exc:
        st.error(f"柱状图绘制失败：{exc}")
        st.exception(exc)

if show_proj_vs_a:
    st.subheader("|B∥| vs A（交互）")
    try:
        angs = np.linspace(float(a_min), float(a_max), 161)
        ang_axis, proj_curve = projections_vs_axis(
            model,
            float(B0),
            axis="A",
            fixed_other_deg=float(beta),
            gamma_deg=float(gamma),
            angles_deg=angs,
            **proj_kw,
        )
        fig_a = _proj_vs_a_plotly(
            ang_axis,
            proj_curve,
            current_a=float(alpha),
            ref_mT=float(summary.degenerate_ref_mT),
        )
        st.caption(
            f"曲线 shape={proj_curve.shape} · |B∥| 范围 "
            f"[{float(proj_curve.min()):.4f}, {float(proj_curve.max()):.4f}] mT"
        )
        _show_plotly(fig_a, height=420)
    except Exception as exc:
        st.error(f"|B∥| vs A 图绘制失败：{exc}")
        st.exception(exc)

with st.expander("模型说明", expanded=False):
    st.markdown(
        f"""
### 坐标系与装夹
- **Lab**：+x 地理北，+y 东，+z **竖直向上**（亥姆霍兹轴）。
- **线圈**：\\(\\mathbf{{B}}_{{\\mathrm{{coil}}}} = (0,0,B_0)\\)。
- **金刚石 (100)**：上表面水平，**[100] ∥ lab +z**；默认 [010]∥北、[001]∥东。
- **台架**：\\(R_{{\\mathrm{{stage}}}} = R_z(\\gamma) R_y(\\alpha_A) R_x(\\beta_B)\\)，
  总旋转 \\(R = R_{{\\mathrm{{stage}}}} M_{{100}}\\)。

### 地磁场（武汉）
- 位置 ≈ **{WUHAN_SITE.lat_deg:.4f}°N, {WUHAN_SITE.lon_deg:.4f}°E**。
- 默认 F≈**{WUHAN_SITE.F_nT:.0f} nT**，I≈**{WUHAN_SITE.inclination_deg:.1f}°**，
  D≈**{WUHAN_SITE.declination_deg:.1f}°**（西偏）。
- 北半球：场线斜向下 → lab 上的 **B_z 为负的小量**（与线圈 +z 反平行分量）。
- \\(\\mathbf{{B}}_{{\\mathrm{{total}}}} = \\mathbf{{B}}_{{\\mathrm{{coil}}}} + \\mathbf{{B}}_{{\\mathrm{{earth}}}}\\)。
- **有地磁时**，即使 A=B=0，四族 |B∥| 也不再严格相等（水平分量破缺 ⟨100⟩ 简并）。

### 谱与线宽
- \\(f_{{\\pm,i}} = D \\pm (\\gamma/2\\pi)|B_{{\\parallel,i}}|\\)，四族等权洛伦兹。
- 默认 Γ = **{DEFAULT_FWHM_MHZ:.0f} MHz**（0721 实测中位）。

### 局限
- 主磁场模型量级，非实时 IGRF 联网；无建筑物/设备铁磁异常。
- 无应变、偏振选择、横向场二阶混合；不替代计量检定。
"""
    )
