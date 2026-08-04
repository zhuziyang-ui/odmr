#!/usr/bin/env python3
"""Export GB/T 20840.2 accuracy tables and ODMR frequency-tolerance CSVs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.services.accuracy_mapping import (  # noqa: E402
    PRIMARY_CLASSES,
    PlatformParams,
    export_standard_csvs,
    freq_tolerance_table,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--In", dest="in_a", type=float, default=3000.0, help="Rated primary current In (A)")
    parser.add_argument("--kH", type=float, default=6.8, help="Helmholtz Gs per ampere excitation")
    parser.add_argument("--alpha", type=float, default=150.0, help="Bus amperes per excitation ampere")
    parser.add_argument("--gamma", type=float, default=28e9, help="gamma/2pi in Hz/T")
    parser.add_argument("--max-exc", type=float, default=15.0, help="Max excitation current (A)")
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "data" / "standards",
        help="Output directory",
    )
    parser.add_argument(
        "--also-copy",
        type=Path,
        nargs="*",
        default=[],
        help="Optional extra directories to copy the same CSVs into",
    )
    args = parser.parse_args()

    params = PlatformParams(
        kH_gs_per_a=args.kH,
        alpha_bus_per_exc=args.alpha,
        gamma_hz_per_t=args.gamma,
        In_a=args.in_a,
        max_exc_a=args.max_exc,
    )

    paths = export_standard_csvs(args.out, params)
    for extra in args.also_copy:
        export_standard_csvs(extra, params)

    print("=== Platform params ===")
    print(json.dumps(params.as_public_dict(), indent=2, ensure_ascii=False))
    print()
    print(f"Primary classes: {PRIMARY_CLASSES}")
    print(f"0–{params.max_exc_a:g} A platform covers up to {params.max_bus_a():.1f} A bus "
          f"({params.max_bus_percent_In():.1f}% In) — 100%/120% In points not reachable.")
    print()
    print("=== 0.2 / 0.2S frequency tolerances (theoretical) ===")
    print(
        f"{'class':>6} {'%In':>6} {'I_bus':>10} {'δI_A':>10} "
        f"{'δΔf_kHz':>12} {'δf±_kHz':>12} {'reach':>6}"
    )
    for row in freq_tolerance_table(params, classes=PRIMARY_CLASSES):
        print(
            f"{row.accuracy_class:>6} {row.I_percent_In:6.1f} {row.I_bus_a:10.1f} "
            f"{row.abs_error_pm_a:10.4f} {row.delta_f_tol_khz:12.3f} "
            f"{row.branch_f_tol_khz:12.3f} "
            f"{'Y' if row.reachable_on_0_15A_platform else 'N':>6}"
        )
    print()
    print("Wrote:")
    for name, path in paths.items():
        print(f"  {name}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
