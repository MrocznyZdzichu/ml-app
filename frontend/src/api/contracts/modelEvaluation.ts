export type ModelEvaluationMetric = {
  id: string;
  label: string;
  value: number;
  direction: "higher" | "lower" | "target_zero" | string;
  unit: string;
};

export type ModelEvaluationSnapshot = {
  contract_version: string;
  kind: "model_performance";
  status: "available" | "target_unavailable";
  problem_type: string;
  generated_at: string;
  data_scope: {
    mode: "full";
    scanned_row_count?: number;
    evaluated_row_count: number;
    excluded_row_count: number;
  };
  columns?: { target?: string; prediction?: string; score?: string | null };
  metrics: ModelEvaluationMetric[];
  class_metrics?: Array<{
    label: unknown;
    support: number;
    predicted_count: number;
    precision: number;
    recall: number;
    f1: number;
  }>;
  class_count?: number;
  positive_class?: unknown;
  confusion_matrix?: {
    labels: unknown[];
    values: number[][];
    truncated: boolean;
    total_class_count: number;
  };
  curves?: Record<string, {
    x_label: string;
    y_label: string;
    points: Array<{ x: number; y: number; threshold?: number | null; count?: number }>;
    rendering: string;
  }>;
  distributions?: {
    score_by_actual?: Array<{
      lower: number;
      upper: number;
      negative_count: number;
      positive_count: number;
    }>;
  };
  residuals?: {
    summary: {
      mean: number;
      standard_deviation: number;
      p05: number;
      median: number;
      p95: number;
    };
    histogram: Array<{ lower: number; upper: number; count: number }>;
    qq_plot?: {
      points: Array<{ theoretical: number; observed: number }>;
      x_label: string;
      y_label: string;
      rendering: string;
    };
    actual_vs_predicted: {
      points: Array<{ actual: number; predicted: number }>;
      rendering: string;
    };
  };
  warnings: string[];
  monitoring: {
    baseline_eligible: boolean;
    requires_actuals: boolean;
    comparison_dimensions?: string[];
  };
};
