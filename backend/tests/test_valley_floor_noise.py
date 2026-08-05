
import math
import unittest
from backend.app.services.dual_peak_tracker import (
    find_fm_magnitude_resonances,
    select_fm_resonance_pair,
)

class ValleyFloorNoiseMaximaTests(unittest.TestCase):
    def test_mid_valley_noise_bump_does_not_destroy_right_resonance(self):
        # Two clean FM |dL/df| resonances plus a tiny local max in the right valley.
        frequencies = [float(v) for v in range(0, 1001, 2)]
        phase = complex(math.cos(0.4), math.sin(0.4))
        def lobe(f, c, g=24.0):
            n = (f - c) / g
            return 2.0 * n / (g * (1.0 + n * n) ** 2)
        complex_values = []
        r_values = []
        for f in frequencies:
            z = phase * (lobe(f, 300.0) + 0.9 * lobe(f, 700.0))
            # inject a noise bump at the right valley floor
            r = abs(z)
            if abs(f - 700.0) < 1.5:
                r = max(r, 0.02 * max(abs(phase * lobe(f, 676.0)), 1e-12))
            complex_values.append(z)
            r_values.append(r)
        # stronger floor bump on R only to mimic real failed_full_scan
        for i, f in enumerate(frequencies):
            if 695 <= f <= 705:
                r_values[i] = max(r_values[i], 0.05 * max(r_values))
        candidates = find_fm_magnitude_resonances(
            frequencies, r_values, complex_values, minimum_prominence_fraction=0.05
        )
        self.assertGreaterEqual(len(candidates), 2)
        left, right = select_fm_resonance_pair(
            candidates, delta_f_min_hz=300, delta_f_max_hz=500, ambiguity_score_ratio=0.95
        )
        self.assertAlmostEqual(left.center_hz, 300.0, delta=8.0)
        self.assertAlmostEqual(right.center_hz, 700.0, delta=8.0)

if __name__ == "__main__":
    unittest.main()
