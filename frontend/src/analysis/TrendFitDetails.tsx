import type { VisualizationTrendCurve } from "../api/client";
import { formatInteger, formatNumber } from "./visualizationFormatters";

export function TrendFitDetails({ trends }: { trends: VisualizationTrendCurve[] }) {
  return (
    <details className="trend-fit-details">
      <summary>Trend fit details ({trends.length})</summary>
      <div className="trend-fit-list">
        {trends.map((trend) => (
          <div key={`${trend.series}-${trend.kind}`}>
            <strong>{trend.series}</strong>
            <span>{describeTrendFit(trend)}</span>
            <small>
              {trend.r_squared != null ? `R²=${formatNumber(trend.r_squared)} · ` : ""}
              n={formatInteger(trend.valid_count)}
              {trend.fit_space === "log_y" ? " · R² in log(Y) space · positive Y only" : ""}
              {trend.approximate ? " · approximate" : ""}
            </small>
          </div>
        ))}
      </div>
    </details>
  );
}

function describeTrendFit(trend: VisualizationTrendCurve) {
  if (trend.kind === "linear") {
    const slope = trend.parameters.slope as number;
    const intercept = trend.parameters.intercept as number;
    return `y = ${formatNumber(slope)}x ${intercept < 0 ? "−" : "+"} ${formatNumber(Math.abs(intercept))} · slope=${formatNumber(slope)} · intercept=${formatNumber(intercept)}`;
  }
  if (trend.kind === "exponential") {
    const amplitude = trend.parameters.amplitude as number;
    const rate = trend.parameters.rate as number;
    return `y = ${formatNumber(amplitude)} · e^(${formatNumber(rate)}x) · amplitude=${formatNumber(amplitude)} · rate=${formatNumber(rate)}`;
  }
  if (trend.kind === "polynomial") {
    return `y = ${formatPolynomialEquation(trend.parameters.coefficients as number[])}`;
  }
  return `Natural spline · ${trend.parameters.nodes} used nodes from ${trend.parameters.source_bins} full-data bins`;
}

function formatPolynomialEquation(coefficients: number[]) {
  return coefficients.map((coefficient, power) => {
    const variable = power ? `x${power > 1 ? superscript(power) : ""}` : "";
    const magnitude = `${formatNumber(Math.abs(coefficient))}${variable}`;
    if (power === 0) return coefficient < 0 ? `−${magnitude}` : magnitude;
    return coefficient < 0 ? ` − ${magnitude}` : ` + ${magnitude}`;
  }).join("");
}

function superscript(value: number) {
  return String(value).replace(/2/g, "²").replace(/3/g, "³").replace(/4/g, "⁴").replace(/5/g, "⁵");
}
