/** Shared linear frequency-sweep helpers (aligned with backend schemas). */

export const DEFAULT_FREQ_START_HZ = 2.68e9;
export const DEFAULT_FREQ_STOP_HZ = 3.10e9;
export const DEFAULT_FREQ_STEP_HZ = 10_000;
export const MAX_LINEAR_SWEEP_POINTS = 100_001;

/**
 * N = round((stop - start) / step) + 1
 * @returns {{ points: number|null, effectiveStepHz: number|null, error: string|null }}
 */
export function computeLinearSweepPoints(startHz, stopHz, stepHz, minPoints = 2) {
  const start = Number(startHz);
  const stop = Number(stopHz);
  const step = Number(stepHz);
  if (!Number.isFinite(start) || !Number.isFinite(stop) || !Number.isFinite(step)) {
    return { points: null, effectiveStepHz: null, error: "频率或步进无效" };
  }
  if (!(stop > start)) {
    return { points: null, effectiveStepHz: null, error: "终点必须大于起点" };
  }
  if (!(step > 0)) {
    return { points: null, effectiveStepHz: null, error: "步进必须大于 0" };
  }
  const span = stop - start;
  let points = Math.round(span / step) + 1;
  if (points < minPoints) {
    points = minPoints;
  }
  if (points > MAX_LINEAR_SWEEP_POINTS) {
    return {
      points: null,
      effectiveStepHz: null,
      error: `点数 ${points} 超过上限 ${MAX_LINEAR_SWEEP_POINTS}，请增大步进`,
    };
  }
  return {
    points,
    effectiveStepHz: span / (points - 1),
    error: null,
  };
}

/** Derive step from start/stop/points when step is missing (legacy payloads). */
export function deriveStepHz(startHz, stopHz, points, fallback = DEFAULT_FREQ_STEP_HZ) {
  const start = Number(startHz);
  const stop = Number(stopHz);
  const n = Number(points);
  if (Number.isFinite(start) && Number.isFinite(stop) && stop > start && n > 1) {
    return (stop - start) / (n - 1);
  }
  return fallback;
}

export function formatStepHz(stepHz) {
  const value = Number(stepHz);
  if (!Number.isFinite(value)) {
    return "--";
  }
  if (Math.abs(value) >= 1e6) {
    return `${(value / 1e6).toFixed(3)} MHz`;
  }
  if (Math.abs(value) >= 1e3) {
    return `${(value / 1e3).toFixed(3)} kHz`;
  }
  return `${value.toFixed(1)} Hz`;
}
