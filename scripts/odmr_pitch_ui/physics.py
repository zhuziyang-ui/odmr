"""
Four-NV ⟨111⟩ projection + CW ODMR spectrum for A/B pitch simulation.

Lab frame (right-handed):
  +x = geographic North (before optional lab yaw)
  +y = geographic East
  +z = vertical Up  ← Helmholtz coil axis (B_coil = B0 * ẑ)

Crystal mounting (default, (100) diamond):
  top face horizontal; crystal [100] along lab +z (surface normal up).
  In-plane default: crystal [010] → lab +x (North), [001] → lab +y (East).

StageModel rotations match cw-27:
  R = Rz(gamma) @ Ry(alpha_A) @ Rx(beta_B)  (additional crystal→lab from stage)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

import numpy as np

D_MHZ = 2870.0
GAMMA_MHZ_PER_MT = 28.0  # γ/2π for NV electron

# Measured on cw-30/0721 ODMR full-scan (I=15 A, dual-peak Lorentz fits).
DEFAULT_FWHM_MHZ = 14.0
# Lab coil |B| so that B∥ = B0/√3 ≈ 6.4 mT matches 0721 (Δf ≈ 357 MHz at degeneracy).
DEFAULT_B0_MT = 11.0

# --- Wuhan, Hubei, China (lab site) ---
# City-center geodetic reference (WGS-84 style); altitude ~50 m for surface field.
WUHAN_LAT_DEG = 30.5928
WUHAN_LON_DEG = 114.3055
WUHAN_ALT_M = 50.0

# Geomagnetic elements for Wuhan region, epoch ~2025 (IGRF/WMM class; main field only).
# D: declination, degrees east of true north (negative = west).
# I: inclination / dip, degrees (positive = field points downward).
# F: total intensity.
# Uncertainties: typically ~0.5° (D/I) and ~0.2 µT (F) for main-field models;
# local steel / building bias is not included.
WUHAN_DECLINATION_DEG = -5.0
WUHAN_INCLINATION_DEG = 47.0
WUHAN_F_NT = 49800.0  # nT ≈ 49.8 µT

NV_LABELS: tuple[str, ...] = (
    "NV1 [111]",
    "NV2 [1-1-1]",
    "NV3 [-11-1]",
    "NV4 [-1-11]",
)

# NV unit axes in crystal cubic frame ([100],[010],[001]).
NV_DIRS = np.array(
    [
        [1.0, 1.0, 1.0],
        [1.0, -1.0, -1.0],
        [-1.0, 1.0, -1.0],
        [-1.0, -1.0, 1.0],
    ],
    dtype=float,
)
NV_DIRS = NV_DIRS / np.linalg.norm(NV_DIRS, axis=1, keepdims=True)

# Crystal → lab for (100) face-up: [100]→+z, [010]→+x, [001]→+y.
# Columns of M are lab images of crystal basis vectors.
MOUNT_100_FACE_UP = np.array(
    [
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0],
        [1.0, 0.0, 0.0],
    ],
    dtype=float,
)


def rot_x(theta: float) -> np.ndarray:
    c, s = np.cos(theta), np.sin(theta)
    return np.array([[1.0, 0.0, 0.0], [0.0, c, -s], [0.0, s, c]], dtype=float)


def rot_y(theta: float) -> np.ndarray:
    c, s = np.cos(theta), np.sin(theta)
    return np.array([[c, 0.0, s], [0.0, 1.0, 0.0], [-s, 0.0, c]], dtype=float)


def rot_z(theta: float) -> np.ndarray:
    c, s = np.cos(theta), np.sin(theta)
    return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]], dtype=float)


def nT_to_mT(nT: float) -> float:
    return float(nT) * 1e-6  # 1 nT = 1e-6 mT


def earth_field_ned_mT(
    F_nT: float = WUHAN_F_NT,
    inclination_deg: float = WUHAN_INCLINATION_DEG,
    declination_deg: float = WUHAN_DECLINATION_DEG,
) -> tuple[float, float, float, float]:
    """
    Return (B_N, B_E, B_D, F) in mT.
    N/E = geographic north/east; D = downward.
    """
    F = nT_to_mT(F_nT)
    I = np.deg2rad(inclination_deg)
    D = np.deg2rad(declination_deg)
    H = F * np.cos(I)
    B_N = H * np.cos(D)
    B_E = H * np.sin(D)
    B_D = F * np.sin(I)
    return float(B_N), float(B_E), float(B_D), float(F)


def earth_field_lab_mT(
    F_nT: float = WUHAN_F_NT,
    inclination_deg: float = WUHAN_INCLINATION_DEG,
    declination_deg: float = WUHAN_DECLINATION_DEG,
    lab_yaw_deg: float = 0.0,
) -> np.ndarray:
    """
    Earth field in lab frame (mT): +x North, +y East, +z Up, then yaw about +z.

    lab_yaw_deg: rotation of the optical table about vertical —
      positive yaw rotates lab +x from geographic North toward East
      (i.e. how much the 'room north' is rotated from true north).
    """
    B_N, B_E, B_D, _ = earth_field_ned_mT(F_nT, inclination_deg, declination_deg)
    # NED → NEU (lab z up): B_U = -B_D
    B_neu = np.array([B_N, B_E, -B_D], dtype=float)
    yaw = np.deg2rad(lab_yaw_deg)
    return rot_z(yaw) @ B_neu


def coil_field_lab_mT(B0_mT: float) -> np.ndarray:
    """Helmholtz field along +z (vertical up)."""
    return np.array([0.0, 0.0, float(B0_mT)], dtype=float)


@dataclass
class GeomagneticSite:
    name: str = "Wuhan, Hubei, China"
    lat_deg: float = WUHAN_LAT_DEG
    lon_deg: float = WUHAN_LON_DEG
    alt_m: float = WUHAN_ALT_M
    F_nT: float = WUHAN_F_NT
    inclination_deg: float = WUHAN_INCLINATION_DEG
    declination_deg: float = WUHAN_DECLINATION_DEG
    epoch: str = "~2025 (IGRF/WMM-class main field)"

    def lab_vector_mT(self, lab_yaw_deg: float = 0.0) -> np.ndarray:
        return earth_field_lab_mT(
            self.F_nT,
            self.inclination_deg,
            self.declination_deg,
            lab_yaw_deg=lab_yaw_deg,
        )

    def summary_dict(self, lab_yaw_deg: float = 0.0) -> dict:
        B = self.lab_vector_mT(lab_yaw_deg)
        B_N, B_E, B_D, F = earth_field_ned_mT(
            self.F_nT, self.inclination_deg, self.declination_deg
        )
        return {
            "name": self.name,
            "lat_deg": self.lat_deg,
            "lon_deg": self.lon_deg,
            "alt_m": self.alt_m,
            "F_nT": self.F_nT,
            "F_uT": self.F_nT * 1e-3,
            "F_mT": nT_to_mT(self.F_nT),
            "inclination_deg": self.inclination_deg,
            "declination_deg": self.declination_deg,
            "B_N_mT": B_N,
            "B_E_mT": B_E,
            "B_D_mT": B_D,
            "B_U_mT": -B_D,
            "B_lab_x_mT": float(B[0]),
            "B_lab_y_mT": float(B[1]),
            "B_lab_z_mT": float(B[2]),
            "lab_yaw_deg": lab_yaw_deg,
            "epoch": self.epoch,
        }


WUHAN_SITE = GeomagneticSite()


@dataclass
class StageModel:
    """A ≈ pitch about lab Y, B ≈ pitch about lab X, R ≈ roll about lab Z."""

    alpha_sign: float = 1.0
    beta_sign: float = 1.0
    gamma_sign: float = 1.0
    # (100) face-up mount; set None to use identity (legacy: crystal z || lab z).
    mount_matrix: np.ndarray | None = field(default_factory=lambda: MOUNT_100_FACE_UP.copy())

    def crystal_to_lab_rotation(
        self, alpha_deg: float, beta_deg: float, gamma_deg: float = 0.0
    ) -> np.ndarray:
        a = np.deg2rad(self.alpha_sign * alpha_deg)
        b = np.deg2rad(self.beta_sign * beta_deg)
        g = np.deg2rad(self.gamma_sign * gamma_deg)
        R_stage = rot_z(g) @ rot_y(a) @ rot_x(b)
        M0 = np.eye(3) if self.mount_matrix is None else np.asarray(self.mount_matrix, float)
        # v_lab = R_stage @ M0 @ v_cryst
        return R_stage @ M0

    def lab_field_mT(
        self,
        B0_mT: float,
        *,
        include_earth: bool = True,
        earth_lab_mT: np.ndarray | None = None,
        site: GeomagneticSite | None = None,
        lab_yaw_deg: float = 0.0,
        earth_scale: float = 1.0,
    ) -> np.ndarray:
        """
        B_lab = B_coil + earth_scale * B_earth.

        earth_scale=1 is physical; >1 is for teaching visualization only.
        """
        B = coil_field_lab_mT(B0_mT)
        if include_earth:
            if earth_lab_mT is not None:
                Be = np.asarray(earth_lab_mT, dtype=float)
            else:
                site = site or WUHAN_SITE
                Be = site.lab_vector_mT(lab_yaw_deg)
            B = B + float(earth_scale) * Be
        return B

    def projections(
        self,
        B0_mT: float,
        alpha_deg: float,
        beta_deg: float,
        gamma_deg: float = 0.0,
        *,
        include_earth: bool = False,
        earth_lab_mT: np.ndarray | None = None,
        site: GeomagneticSite | None = None,
        lab_yaw_deg: float = 0.0,
        earth_scale: float = 1.0,
    ) -> np.ndarray:
        """Absolute axial projections |B · n_i| for four NV families (mT)."""
        R = self.crystal_to_lab_rotation(alpha_deg, beta_deg, gamma_deg)
        B_lab = self.lab_field_mT(
            B0_mT,
            include_earth=include_earth,
            earth_lab_mT=earth_lab_mT,
            site=site,
            lab_yaw_deg=lab_yaw_deg,
            earth_scale=earth_scale,
        )
        B_cryst = R.T @ B_lab
        return np.abs(NV_DIRS @ B_cryst)

    def signed_projections(
        self,
        B0_mT: float,
        alpha_deg: float,
        beta_deg: float,
        gamma_deg: float = 0.0,
        *,
        include_earth: bool = False,
        earth_lab_mT: np.ndarray | None = None,
        site: GeomagneticSite | None = None,
        lab_yaw_deg: float = 0.0,
        earth_scale: float = 1.0,
    ) -> np.ndarray:
        R = self.crystal_to_lab_rotation(alpha_deg, beta_deg, gamma_deg)
        B_lab = self.lab_field_mT(
            B0_mT,
            include_earth=include_earth,
            earth_lab_mT=earth_lab_mT,
            site=site,
            lab_yaw_deg=lab_yaw_deg,
            earth_scale=earth_scale,
        )
        B_cryst = R.T @ B_lab
        return NV_DIRS @ B_cryst


def frequencies_mhz(projections_mT: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return f_minus, f_plus, delta_f for each family (MHz)."""
    shift = GAMMA_MHZ_PER_MT * np.asarray(projections_mT, dtype=float)
    f_minus = D_MHZ - shift
    f_plus = D_MHZ + shift
    delta_f = 2.0 * shift
    return f_minus, f_plus, delta_f


def lorentzian(f: np.ndarray, f0: float, amplitude: float, fwhm: float) -> np.ndarray:
    half = 0.5 * max(float(fwhm), 1e-9)
    return amplitude * (half**2) / ((f - f0) ** 2 + half**2)


def odmr_spectrum(
    projections_mT: np.ndarray,
    *,
    fwhm_mhz: float = DEFAULT_FWHM_MHZ,
    contrast_per_class: float = 0.02,
    freq_mhz: np.ndarray | None = None,
    margin_mhz: float | None = None,
    n_points: int = 4000,
) -> tuple[np.ndarray, np.ndarray]:
    """Ideal equal-weight CW ODMR: PL baseline 1 minus sum of eight Lorentzians."""
    projs = np.asarray(projections_mT, dtype=float)
    f_minus, f_plus, _ = frequencies_mhz(projs)
    all_f = np.concatenate([f_minus, f_plus])
    if margin_mhz is None:
        margin_mhz = max(40.0, 3.0 * float(fwhm_mhz))
    if freq_mhz is None:
        span = max(float(np.ptp(all_f)) + 2.0 * margin_mhz, 4.0 * fwhm_mhz + 80.0)
        center = 0.5 * (all_f.min() + all_f.max())
        freq_mhz = np.linspace(center - 0.5 * span, center + 0.5 * span, int(n_points))
    else:
        freq_mhz = np.asarray(freq_mhz, dtype=float)

    pl = np.ones_like(freq_mhz)
    for fm, fp in zip(f_minus, f_plus):
        pl -= lorentzian(freq_mhz, float(fm), contrast_per_class, fwhm_mhz)
        pl -= lorentzian(freq_mhz, float(fp), contrast_per_class, fwhm_mhz)
    return freq_mhz, pl


@dataclass(frozen=True)
class ProjectionSummary:
    projections_mT: np.ndarray
    mean_mT: float
    std_mT: float
    spread_mT: float
    spread_rel: float
    eps_mean: float
    degenerate_ref_mT: float
    n_unique_clusters: int
    f_minus_mhz: np.ndarray
    f_plus_mhz: np.ndarray
    delta_f_mhz: np.ndarray


def summarize(
    projections_mT: np.ndarray,
    B0_mT: float,
    *,
    cluster_tol_mT: float = 1e-4,
    ref_mT: float | None = None,
) -> ProjectionSummary:
    p = np.asarray(projections_mT, dtype=float)
    # Coil-only equal-projection reference (ignores Earth).
    ref = float(B0_mT) / np.sqrt(3.0) if ref_mT is None else float(ref_mT)
    mean = float(p.mean())
    std = float(p.std(ddof=0))
    spread = float(p.max() - p.min())
    spread_rel = spread / ref if ref > 0 else 0.0
    eps_mean = 1.0 - mean / ref if ref > 0 else 0.0
    rounded = np.round(p / max(cluster_tol_mT, 1e-12)) * max(cluster_tol_mT, 1e-12)
    n_unique = int(len(np.unique(np.round(rounded, 8))))
    f_m, f_p, df = frequencies_mhz(p)
    return ProjectionSummary(
        projections_mT=p,
        mean_mT=mean,
        std_mT=std,
        spread_mT=spread,
        spread_rel=spread_rel,
        eps_mean=eps_mean,
        degenerate_ref_mT=ref,
        n_unique_clusters=n_unique,
        f_minus_mhz=f_m,
        f_plus_mhz=f_p,
        delta_f_mhz=df,
    )


def projections_vs_axis(
    model: StageModel,
    B0_mT: float,
    *,
    axis: str = "A",
    fixed_other_deg: float = 0.0,
    gamma_deg: float = 0.0,
    angles_deg: Sequence[float] | np.ndarray | None = None,
    include_earth: bool = False,
    earth_lab_mT: np.ndarray | None = None,
    site: GeomagneticSite | None = None,
    lab_yaw_deg: float = 0.0,
    earth_scale: float = 1.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Sweep A or B; return angles and (N, 4) absolute projections."""
    if angles_deg is None:
        angles_deg = np.linspace(-6.0, 6.0, 121)
    angles = np.asarray(angles_deg, dtype=float)
    out = np.zeros((len(angles), 4), dtype=float)
    kw = dict(
        include_earth=include_earth,
        earth_lab_mT=earth_lab_mT,
        site=site,
        lab_yaw_deg=lab_yaw_deg,
        earth_scale=earth_scale,
    )
    for i, ang in enumerate(angles):
        if axis.upper() == "A":
            out[i] = model.projections(
                B0_mT, float(ang), fixed_other_deg, gamma_deg, **kw
            )
        else:
            out[i] = model.projections(
                B0_mT, fixed_other_deg, float(ang), gamma_deg, **kw
            )
    return angles, out


def unified_freq_axis_mhz(
    *projection_sets: np.ndarray,
    fwhm_mhz: float = DEFAULT_FWHM_MHZ,
    n_points: int = 5000,
    margin_mhz: float | None = None,
) -> np.ndarray:
    """Frequency grid covering all D±γ|B∥| from several projection sets."""
    shifts = []
    for p in projection_sets:
        if p is None:
            continue
        shifts.append(GAMMA_MHZ_PER_MT * np.asarray(p, dtype=float).ravel())
    if not shifts:
        return np.linspace(D_MHZ - 50.0, D_MHZ + 50.0, n_points)
    all_shift = np.concatenate(shifts)
    # include near-zero-field (earth-only) and large coil splitting
    f_lo = D_MHZ - float(all_shift.max()) - (margin_mhz or max(40.0, 3 * fwhm_mhz))
    f_hi = D_MHZ + float(all_shift.max()) + (margin_mhz or max(40.0, 3 * fwhm_mhz))
    # also ensure D itself is covered for earth-only dips
    f_lo = min(f_lo, D_MHZ - max(40.0, 3 * fwhm_mhz))
    f_hi = max(f_hi, D_MHZ + max(40.0, 3 * fwhm_mhz))
    return np.linspace(f_lo, f_hi, int(n_points))


def assert_degenerate_at_origin(B0_mT: float = 1.0, rtol: float = 1e-9) -> None:
    """Coil-only, (100) face-up: four |B∥| equal at A=B=0."""
    model = StageModel()
    p = model.projections(B0_mT, 0.0, 0.0, 0.0, include_earth=False)
    ref = B0_mT / np.sqrt(3.0)
    if not np.allclose(p, ref, rtol=rtol, atol=1e-12):
        raise AssertionError(f"Expected all |B∥|={ref}, got {p}")
