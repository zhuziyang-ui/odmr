#!/usr/bin/env python3
"""Map frequency lock error (kHz) to bus/excitation current error (A).

Examples
--------
  python scripts/freq_to_current_error.py --df-khz 50 --quantity delta_f
  python scripts/freq_to_current_error.py --df-khz 50 --quantity branch
  python scripts/freq_to_current_error.py --df-khz 50 --mode empirical --slope-a-per-hz 4.2e-8
  python scripts/freq_to_current_error.py --df-khz 10,20,50,100 --compare-standard
"""

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
    abs_current_error_table,
    delta_f_khz_to_delta_I_a,
)


def _parse_df_list(text: str) -> list[float]:
    return [float(part.strip()) for part in text.split(",") if part.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--df-khz",
        required=True,
        help="Frequency error in kHz; comma-separated list allowed",
    )
    parser.add_argument(
        "--quantity",
        choices=("delta_f", "branch"),
        default="delta_f",
        help="delta_f: splitting error; branch: single-peak lock error",
    )
    parser.add_argument("--mode", choices=("theoretical", "empirical"), default="theoretical")
    parser.add_argument(
        "--slope-a-per-hz",
        type=float,
        default=None,
        help="Empirical calibration slope a in I=a*Δf+b (A/Hz)",
    )
    parser.add_argument("--In", dest="in_a", type=float, default=3000.0)
    parser.add_argument("--kH", type=float, default=6.8)
    parser.add_argument("--alpha", type=float, default=150.0)
    parser.add_argument("--gamma", type=float, default=28e9)
    parser.add_argument(
        "--compare-standard",
        action="store_true",
        help="Compare |δI| against GB/T 20840.2 0.2/0.2S absolute limits",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON only")
    args = parser.parse_args()

    params = PlatformParams(
        kH_gs_per_a=args.kH,
        alpha_bus_per_exc=args.alpha,
        gamma_hz_per_t=args.gamma,
        In_a=args.in_a,
    )

    results = []
    for df in _parse_df_list(args.df_khz):
        mapped = delta_f_khz_to_delta_I_a(
            df,
            quantity=args.quantity,
            params=params,
            mode=args.mode,
            empirical_slope_a_per_hz=args.slope_a_per_hz,
        )
        item = mapped.as_dict()
        if args.compare_standard:
            comparisons = []
            for row in abs_current_error_table(params, classes=PRIMARY_CLASSES):
                comparisons.append(
                    {
                        "accuracy_class": row.accuracy_class,
                        "I_percent_In": row.I_percent_In,
                        "I_bus_a": row.I_bus_a,
                        "abs_error_limit_a": row.abs_error_pm_a,
                        "delta_I_bus_a": mapped.delta_I_bus_a,
                        "within_limit": mapped.delta_I_bus_a <= row.abs_error_pm_a + 1e-15,
                        "margin_a": row.abs_error_pm_a - mapped.delta_I_bus_a,
                    }
                )
            item["standard_comparison"] = comparisons
        results.append(item)

    if args.json:
        print(json.dumps(results if len(results) > 1 else results[0], indent=2, ensure_ascii=False))
        return 0

    print(f"mode={args.mode}  quantity={args.quantity}")
    print(f"sensitivity ≈ {results[0]['sensitivity_khz_per_a_bus']:.6f} kHz per A_bus")
    print()
    for item in results:
        print(
            f"δf = {item['delta_f_khz']:g} kHz  →  "
            f"δI_bus = {item['delta_I_bus_a']:.6f} A  |  "
            f"δI_exc = {item['delta_I_exc_a']:.6f} A"
        )
        if "standard_comparison" in item:
            print("  vs GB/T 20840.2 absolute limits:")
            for c in item["standard_comparison"]:
                flag = "OK" if c["within_limit"] else "FAIL"
                print(
                    f"    [{flag}] {c['accuracy_class']:>4} @ {c['I_percent_In']:5.1f}%In "
                    f"(I={c['I_bus_a']:.1f} A, limit ±{c['abs_error_limit_a']:.4f} A, "
                    f"margin {c['margin_a']:+.4f} A)"
                )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
