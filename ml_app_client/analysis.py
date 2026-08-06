"""Full-dataset profiling and visualization workflows.

The platform performs every analytical scan.  This module only submits bounded
requests, polls asynchronous jobs, and renders the compact result contracts.
"""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
import math
import time
from typing import Any, Callable, Mapping
from urllib.parse import quote

from .datasets import DatasetRef
from .errors import ApiError
from .models import ApiModel, Dataset
from .transport import TransportClientMixin


def _dataset_id(dataset: DatasetRef) -> str:
    return dataset.id if isinstance(dataset, Dataset) else str(dataset)


def _number(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:,.5g}"
    return f"{value:,}" if isinstance(value, int) else str(value if value is not None else "-")


@dataclass(frozen=True)
class DescriptiveProfile(ApiModel):
    """Compact aggregate result of a platform-side full descriptive profile."""

    dataset_id: str
    columns: tuple[Mapping[str, Any], ...]
    row_count: int
    profile: Mapping[str, Any]
    raw: Mapping[str, Any]

    @classmethod
    def from_api(cls, value: Mapping[str, Any]) -> "DescriptiveProfile":
        return cls(
            dataset_id=str(value["dataset_id"]),
            columns=tuple(item for item in value.get("columns", ()) if isinstance(item, Mapping)),
            row_count=int(value.get("row_count") or 0),
            profile=dict(value.get("profile") or {}),
            raw=value,
        )


@dataclass(frozen=True)
class DescriptiveProfileJob(ApiModel):
    """State of one asynchronous full descriptive-profile request."""

    dataset_id: str
    job_id: str
    status: str
    result: DescriptiveProfile | None
    error: str | None
    raw: Mapping[str, Any]

    @property
    def finished(self) -> bool:
        return self.status in {"completed", "failed"}

    @classmethod
    def from_api(cls, dataset_id: str, value: Mapping[str, Any]) -> "DescriptiveProfileJob":
        raw_result = value.get("result")
        return cls(
            dataset_id=dataset_id,
            job_id=str(value["job_id"]),
            status=str(value["status"]),
            result=DescriptiveProfile.from_api(raw_result) if isinstance(raw_result, Mapping) else None,
            error=str(value["error"]) if value.get("error") else None,
            raw=value,
        )


@dataclass(frozen=True)
class VisualizationResult(ApiModel):
    """Bounded visualization data calculated over the full selected dataset."""

    dataset_id: str
    kind: str
    row_count: int
    scanned_row_count: int
    valid_count: int
    points: tuple[Mapping[str, Any], ...]
    trends: tuple[Mapping[str, Any], ...]
    series: tuple[str, ...]
    kpi: float | None
    execution_mode: str
    truncated: bool
    approximate: bool
    approximation_method: str | None
    reduction_metadata: Mapping[str, Any] | None
    raw: Mapping[str, Any]

    @classmethod
    def from_api(cls, kind: str, value: Mapping[str, Any]) -> "VisualizationResult":
        return cls(
            dataset_id=str(value["dataset_id"]), kind=kind,
            row_count=int(value.get("row_count") or 0),
            scanned_row_count=int(value.get("scanned_row_count") or 0),
            valid_count=int(value.get("valid_count") or 0),
            points=tuple(item for item in value.get("points", ()) if isinstance(item, Mapping)),
            trends=tuple(item for item in value.get("trends", ()) if isinstance(item, Mapping)),
            series=tuple(str(item) for item in value.get("series", ())),
            kpi=float(value["kpi"]) if value.get("kpi") is not None else None,
            execution_mode=str(value.get("execution_mode") or ""),
            truncated=bool(value.get("truncated")), approximate=bool(value.get("approximate")),
            approximation_method=(str(value["approximation_method"]) if value.get("approximation_method") else None),
            reduction_metadata=dict(value["reduction_metadata"]) if isinstance(value.get("reduction_metadata"), Mapping) else None,
            raw=value,
        )


@dataclass(frozen=True)
class TimeSeriesAnalysis(ApiModel):
    """Bounded temporal diagnostics calculated by the platform over all rows."""

    dataset_id: str
    time_column: str
    value_column: str
    row_count: int
    scanned_row_count: int
    valid_count: int
    summary: Mapping[str, Any]
    series: tuple[Mapping[str, Any], ...]
    autocorrelation: tuple[Mapping[str, Any], ...]
    cross_correlation: tuple[Mapping[str, Any], ...]
    driver_relationships: tuple[Mapping[str, Any], ...]
    seasonal_profile: tuple[Mapping[str, Any], ...]
    decomposition: tuple[Mapping[str, Any], ...]
    difference_series: tuple[Mapping[str, Any], ...]
    feature_preview: tuple[Mapping[str, Any], ...]
    quality_notes: tuple[str, ...]
    execution_mode: str
    raw: Mapping[str, Any]

    @classmethod
    def from_api(cls, value: Mapping[str, Any]) -> "TimeSeriesAnalysis":
        def records(name: str) -> tuple[Mapping[str, Any], ...]:
            return tuple(item for item in value.get(name, ()) if isinstance(item, Mapping))
        return cls(
            dataset_id=str(value["dataset_id"]), time_column=str(value["time_column"]),
            value_column=str(value["value_column"]), row_count=int(value.get("row_count") or 0),
            scanned_row_count=int(value.get("scanned_row_count") or 0), valid_count=int(value.get("valid_count") or 0),
            summary=dict(value.get("summary") or {}), series=records("series"),
            autocorrelation=records("autocorrelation"), cross_correlation=records("cross_correlation"),
            driver_relationships=records("driver_relationships"), seasonal_profile=records("seasonal_profile"),
            decomposition=records("decomposition"), difference_series=records("difference_series"),
            feature_preview=records("feature_preview"), quality_notes=tuple(str(item) for item in value.get("quality_notes", ())),
            execution_mode=str(value.get("execution_mode") or ""), raw=value,
        )


@dataclass(frozen=True)
class TimeSeriesAnalysisJob(ApiModel):
    """State of one asynchronous full-dataset time-series analysis."""

    dataset_id: str
    job_id: str
    status: str
    result: TimeSeriesAnalysis | None
    error: str | None
    raw: Mapping[str, Any]

    @property
    def finished(self) -> bool:
        return self.status in {"completed", "failed"}

    @classmethod
    def from_api(cls, dataset_id: str, value: Mapping[str, Any]) -> "TimeSeriesAnalysisJob":
        raw_result = value.get("result")
        return cls(
            dataset_id=dataset_id, job_id=str(value["job_id"]), status=str(value["status"]),
            result=TimeSeriesAnalysis.from_api(raw_result) if isinstance(raw_result, Mapping) else None,
            error=str(value["error"]) if value.get("error") else None, raw=value,
        )


class _AnalysisPresentation:
    title = "Analysis result"

    def __init__(self, value: Any) -> None:
        self.value = value

    @staticmethod
    def _card(label: str, value: Any) -> str:
        return f'<div class="metric"><span>{escape(label)}</span><strong>{escape(_number(value))}</strong></div>'

    @staticmethod
    def _document(body: str) -> str:
        return (
            '<section class="mlapp-analysis">' + body +
            '<style>.mlapp-analysis .categorical-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(310px,1fr));gap:12px}.mlapp-analysis .category-card{padding:12px;border:1px solid #29405f;border-radius:10px;background:#101c2f}.mlapp-analysis .category-head{display:flex;align-items:baseline;justify-content:space-between;gap:8px;margin-bottom:8px}.mlapp-analysis .category-head strong{color:#d8f68a}.mlapp-analysis .category-head span,.mlapp-analysis .category-head small{display:block;color:#93a8c7;font-size:11px;text-align:right}.mlapp-analysis .category-head span{text-align:left}.mlapp-analysis .category-stats{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin:10px 0}.mlapp-analysis .category-stats>div{padding:8px;border:1px solid #29405f;border-radius:7px}.mlapp-analysis .category-stats span{display:block;color:#93a8c7;font-size:10px}.mlapp-analysis .category-stats b{display:block;margin-top:3px;color:#dce8fb;font-size:13px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.mlapp-analysis .category-values{padding:4px 0}.mlapp-analysis .category-row{display:grid;grid-template-columns:minmax(0,1fr) 1.65fr 42px;gap:8px;align-items:center;margin:8px 0;font-size:12px}.mlapp-analysis .category-label{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#dce8fb}.mlapp-analysis .category-bar{height:10px;overflow:hidden;border-radius:999px;background:#263246}.mlapp-analysis .category-bar i{display:block;height:100%;border-radius:inherit;background:#2ea39a}.mlapp-analysis .category-row em{color:#a8b8d2;font-size:11px;font-style:normal;text-align:right}</style>' +
            '<style>.mlapp-analysis{max-width:1100px;color:#eaf1ff;font-family:system-ui,sans-serif}.mlapp-analysis h3{margin:0 0 5px}.mlapp-analysis p,.mlapp-analysis .small{color:#afbdd5}.mlapp-analysis .metrics{display:flex;gap:10px;flex-wrap:wrap;margin:14px 0}.mlapp-analysis .metric{min-width:138px;padding:11px 13px;border:1px solid #29405f;border-radius:9px;background:#101c2f}.mlapp-analysis .metric span{display:block;color:#93a8c7;font-size:12px}.mlapp-analysis .metric strong{font-size:18px;color:#d8f68a}.mlapp-analysis table{width:100%;border-collapse:collapse;background:#101c2f}.mlapp-analysis th,.mlapp-analysis td{padding:8px 10px;border-bottom:1px solid #29405f;text-align:left;vertical-align:top}.mlapp-analysis th{color:#a8b8d2;font-size:12px}.mlapp-analysis .note{padding:10px 12px;border-left:3px solid #75d9ed;background:#10263b}.mlapp-analysis svg{width:100%;max-height:330px;border:1px solid #29405f;border-radius:9px;background:#0b1525}.mlapp-analysis .distribution-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(310px,1fr));gap:12px}.mlapp-analysis .distribution-card{padding:12px;border:1px solid #29405f;border-radius:10px;background:#101c2f}.mlapp-analysis .distribution-head{display:flex;align-items:baseline;justify-content:space-between;gap:8px;margin-bottom:8px}.mlapp-analysis .distribution-head strong{color:#d8f68a}.mlapp-analysis .distribution-head span{color:#93a8c7;font-size:11px;text-align:right}.mlapp-analysis svg.histogram{height:168px;max-height:none}.mlapp-analysis .legend{font-size:12px;color:#afbdd5}.mlapp-analysis details{margin-top:12px}.mlapp-analysis summary{cursor:pointer;color:#75d9ed}</style></section>'
        )


class DescriptiveProfilePresentation(_AnalysisPresentation):
    """Readable terminal and notebook rendering of a descriptive profile."""

    title = "Full data profile"

    def __str__(self) -> str:
        result: DescriptiveProfile = self.value
        notes = result.profile.get("dataQualityNotes") or ()
        return f"{self.title}\nDataset: {result.dataset_id}\nRows analyzed: {result.row_count:,}\nColumns: {len(result.columns)}\nQuality notes: {len(notes)}"

    @staticmethod
    def _distribution_svg(column: Mapping[str, Any]) -> str:
        """Render platform-returned histogram bins without recalculating a distribution."""
        histogram = column.get("histogram")
        if not isinstance(histogram, list):
            return ""
        bins = [
            item for item in histogram
            if isinstance(item, Mapping) and isinstance(item.get("count"), (int, float))
        ]
        if not bins:
            return ""
        counts = [float(item["count"]) for item in bins]
        maximum = max(counts)
        width, height, left, top, bottom = 480, 168, 28, 14, 143
        bar_width = (width - left - 10) / len(bins)
        bars = "".join(
            f'<rect x="{left + index * bar_width + 1:.2f}" y="{bottom - (count / maximum * (bottom - top) if maximum else 0):.2f}" width="{max(bar_width - 2, 1):.2f}" height="{(count / maximum * (bottom - top) if maximum else 0):.2f}" rx="1.5" fill="#67e8f9"><title>{escape(str(item.get("label") or ""))}: {escape(_number(item.get("count")))}</title></rect>'
            for index, (item, count) in enumerate(zip(bins, counts))
        )
        first_label = escape(str(bins[0].get("label") or ""))
        last_label = escape(str(bins[-1].get("label") or ""))
        name = escape(str(column.get("name") or "column"))
        return (
            f'<svg class="histogram" viewBox="0 0 {width} {height}" role="img" aria-label="Distribution of {name}">'
            f'<line x1="{left}" y1="{bottom}" x2="{width - 10}" y2="{bottom}" stroke="#58708f"/>'
            f'<line x1="{left}" y1="{top}" x2="{left}" y2="{bottom}" stroke="#58708f"/>{bars}'
            f'<text x="{left}" y="{height - 7}" fill="#afbdd5" font-size="9">{first_label}</text>'
            f'<text x="{width - 12}" y="{height - 7}" text-anchor="end" fill="#afbdd5" font-size="9">{last_label}</text>'
            f'<text x="3" y="{top + 8}" fill="#afbdd5" font-size="9">{escape(_number(maximum))}</text></svg>'
        )

    @staticmethod
    def _categorical_distribution_card(column: Mapping[str, Any]) -> str:
        """Render server-returned top-category aggregates as a compact bar card."""
        top_values = column.get("topValues")
        if not isinstance(top_values, list):
            return ""
        values = [
            item for item in top_values
            if isinstance(item, Mapping) and isinstance(item.get("share"), (int, float))
        ]
        if not values:
            return ""
        rows = "".join(
            f"<div class='category-row'><span class='category-label' title='{escape(str(item.get('value')))}'>{escape(str(item.get('value')))}</span><span class='category-bar'><i style='width:{max(0, min(float(item['share']), 1)) * 100:.2f}%'></i></span><em>{float(item['share']) * 100:.1f}%</em></div>"
            for item in values
        )
        present = int(column.get("count") or 0)
        missing = int(column.get("missing") or 0)
        total = present + missing
        complete = (present / total * 100) if total else 0
        name = escape(str(column.get("name") or "Unnamed column"))
        return (
            "<article class='category-card'>"
            f"<div class='category-head'><div><strong>{name}</strong><span>{escape(str(column.get('role') or 'categorical feature').replace('_', ' '))}</span></div><small>{complete:.0f}% complete</small></div>"
            "<div class='category-stats'>"
            f"<div><span>Count</span><b>{escape(_number(present))}</b></div>"
            f"<div><span>Missing</span><b>{missing / total * 100 if total else 0:.1f}%</b></div>"
            f"<div><span>Unique</span><b>{escape(_number(column.get('unique')))}</b></div>"
            f"<div><span>Mode</span><b>{escape(_number(column.get('mode')))}</b></div>"
            f"</div><div class='category-values'>{rows}</div></article>"
        )

    def _repr_html_(self) -> str:
        result: DescriptiveProfile = self.value
        profiles = result.profile.get("columnProfiles") or ()
        relations = result.profile.get("targetRelations") or ()
        notes = result.profile.get("dataQualityNotes") or ()
        rows = "".join(
            "<tr>" + "".join(f"<td>{escape(_number(item.get(key)))}</td>" for key in ("name", "type", "role", "count", "missing", "unique", "mean")) +
            f"<td>{escape(', '.join(str(note) for note in item.get('notes', ())) or '-')}</td></tr>"
            for item in profiles[:50] if isinstance(item, Mapping)
        ) or "<tr><td colspan='8'>No column profile was requested.</td></tr>"
        note_items = "".join(f"<li>{escape(str(note))}</li>" for note in notes)
        distribution_profiles = [
            item for item in profiles
            if isinstance(item, Mapping) and self._distribution_svg(item)
        ]
        categorical_profiles = [
            item for item in profiles
            if isinstance(item, Mapping) and self._categorical_distribution_card(item)
        ]
        categorical_cards = "".join(
            self._categorical_distribution_card(item)
            for item in categorical_profiles[:24]
        )
        distribution_cards = "".join(
            f"<article class='distribution-card'><div class='distribution-head'><strong>{escape(str(item.get('name') or 'Unnamed column'))}</strong><span>{escape(_number(item.get('count')))} non-null · median {escape(_number(item.get('median')))}</span></div>{self._distribution_svg(item)}</article>"
            for item in distribution_profiles[:24]
        )
        body = f"<h3>{escape(self.title)}</h3><p>Platform-computed aggregates; no source rows were transferred to this client.</p><div class='metrics'>{self._card('Rows analyzed', result.row_count)}{self._card('Columns', len(result.columns))}{self._card('Relations', len(relations))}{self._card('Quality notes', len(notes))}</div>"
        if note_items:
            body += f"<div class='note'><strong>Data-quality guidance</strong><ul>{note_items}</ul></div>"
        if distribution_cards:
            suffix = "" if len(distribution_profiles) <= 24 else f" Showing the first 24 of {len(distribution_profiles)} available distributions."
            body += f"<details open><summary>Numeric distributions ({len(distribution_profiles)})</summary><p class='small'>Histogram bins and counts were computed from the full selected dataset by the platform.{escape(suffix)}</p><div class='distribution-grid'>{distribution_cards}</div></details>"
        if categorical_cards:
            suffix = "" if len(categorical_profiles) <= 24 else f" Showing the first 24 of {len(categorical_profiles)} available categorical distributions."
            body += f"<details open><summary>Categorical distributions ({len(categorical_profiles)})</summary><p class='small'>Bars show the platform-returned share of each top category among non-null values; no records are transferred to the client.{escape(suffix)}</p><div class='categorical-grid'>{categorical_cards}</div></details>"
        body += f"<details open><summary>Column profile ({len(profiles)})</summary><table><thead><tr><th>Column</th><th>Type</th><th>Role</th><th>Present</th><th>Missing</th><th>Unique</th><th>Mean</th><th>Notes</th></tr></thead><tbody>{rows}</tbody></table></details>"
        return self._document(body)


class VisualizationPresentation(_AnalysisPresentation):
    """Notebook-friendly visualization summary with an SVG view of bounded points."""

    title = "Full data visualization"

    def __str__(self) -> str:
        result: VisualizationResult = self.value
        return f"{self.title} ({result.kind})\nDataset: {result.dataset_id}\nRows analyzed: {result.scanned_row_count:,}\nDisplay points: {len(result.points):,}\nSeries: {len(result.series)}"

    def _svg(self, points: tuple[Mapping[str, Any], ...]) -> str:
        numeric = [(point, point.get("x"), point.get("y")) for point in points[:1_000]]
        numeric = [(point, float(x), float(y)) for point, x, y in numeric if isinstance(x, (int, float)) and isinstance(y, (int, float)) and math.isfinite(float(x)) and math.isfinite(float(y))]
        if not numeric:
            return ""
        xs, ys = [entry[1] for entry in numeric], [entry[2] for entry in numeric]
        left, right, top, bottom = 48, 790, 20, 275
        x_span, y_span = max(max(xs) - min(xs), 1e-12), max(max(ys) - min(ys), 1e-12)
        colors = ("#67e8f9", "#bef264", "#fbbf24", "#f9a8d4", "#c4b5fd", "#86efac")
        series = {name: colors[index % len(colors)] for index, name in enumerate(dict.fromkeys(str(entry[0].get("series") or "All") for entry in numeric))}
        marks = "".join(
            f'<circle cx="{left + (x - min(xs)) / x_span * (right - left):.2f}" cy="{bottom - (y - min(ys)) / y_span * (bottom - top):.2f}" r="2.2" fill="{series[str(point.get("series") or "All")]}" opacity=".78" />'
            for point, x, y in numeric
        )
        legend = " ".join(f'<span style="color:{color}">● {escape(name)}</span>' for name, color in series.items())
        return f"<svg viewBox='0 0 840 300' role='img' aria-label='Bounded visualization points'><line x1='{left}' y1='{bottom}' x2='{right}' y2='{bottom}' stroke='#58708f'/><line x1='{left}' y1='{top}' x2='{left}' y2='{bottom}' stroke='#58708f'/>{marks}<text x='{left}' y='294' fill='#afbdd5' font-size='11'>{escape(_number(min(xs)))}</text><text x='{right-32}' y='294' fill='#afbdd5' font-size='11'>{escape(_number(max(xs)))}</text><text x='4' y='{top+8}' fill='#afbdd5' font-size='11'>{escape(_number(max(ys)))}</text><text x='4' y='{bottom}' fill='#afbdd5' font-size='11'>{escape(_number(min(ys)))}</text></svg><div class='legend'>{legend}</div>"

    def _repr_html_(self) -> str:
        result: VisualizationResult = self.value
        scope = "full dataset / server-side" if result.execution_mode == "full_dataset" else result.execution_mode
        warning = " Display points are capped." if result.truncated else ""
        if result.approximate:
            warning += f" Uses platform-marked approximation ({result.approximation_method or 'unspecified'})."
        trend_rows = "".join(
            f"<tr><td>{escape(str(trend.get('series') or 'All'))}</td><td>{escape(str(trend.get('kind') or '-'))}</td><td>{escape(_number(trend.get('valid_count')))}</td><td>{escape(_number(trend.get('r_squared')))}</td></tr>"
            for trend in result.trends
        ) or "<tr><td colspan='4'>No trend was requested.</td></tr>"
        body = f"<h3>{escape(self.title)}: {escape(result.kind)}</h3><p>{escape(scope)}.{escape(warning)}</p><div class='metrics'>{self._card('Rows analyzed', result.scanned_row_count)}{self._card('Valid rows', result.valid_count)}{self._card('Display points', len(result.points))}{self._card('Series', len(result.series))}{self._card('KPI', result.kpi)}</div>{self._svg(result.points)}<details open><summary>Trend fit details ({len(result.trends)})</summary><table><thead><tr><th>Series</th><th>Fit</th><th>Valid rows</th><th>R²</th></tr></thead><tbody>{trend_rows}</tbody></table></details>"
        return self._document(body)


class TimeSeriesAnalysisPresentation(_AnalysisPresentation):
    """Readable terminal and notebook rendering of server-side time-series diagnostics."""

    title = "Full data time-series analysis"

    def __str__(self) -> str:
        result: TimeSeriesAnalysis = self.value
        return f"{self.title}\nDataset: {result.dataset_id}\nRows analyzed: {result.scanned_row_count:,}\nValid observations: {result.valid_count:,}\nQuality notes: {len(result.quality_notes)}"

    def _repr_html_(self) -> str:
        result: TimeSeriesAnalysis = self.value
        summary_rows = "".join(f"<tr><th>{escape(str(key).replace('_', ' ').title())}</th><td>{escape(_number(value))}</td></tr>" for key, value in result.summary.items())
        notes = "".join(f"<li>{escape(note)}</li>" for note in result.quality_notes) or "<li>No quality notes returned.</li>"
        body = f"<h3>{escape(self.title)}</h3><p>Temporal diagnostics and bounded display series were calculated over the complete selected relation on the platform.</p><div class='metrics'>{self._card('Rows analyzed', result.scanned_row_count)}{self._card('Valid observations', result.valid_count)}{self._card('ACF lags', len(result.autocorrelation))}{self._card('Driver relations', len(result.driver_relationships))}</div><details open><summary>Summary</summary><table><tbody>{summary_rows}</tbody></table></details><details open><summary>Quality notes</summary><div class='note'><ul>{notes}</ul></div></details>"
        return self._document(body)


class AnalysisClientMixin(TransportClientMixin):
    """Full-dataset profiling, visualization, and temporal-analysis operations."""

    def start_descriptive_profile(self, dataset: DatasetRef, *, target_column: str = "", target_type: str = "categorical", comparison_column: str = "", comparison_type: str = "categorical", include_summary: bool = True, include_univariate: bool = True, include_target_relations: bool = True, include_segments: bool = True, include_graphic_summaries: bool = True, row_limit: int = 50_000, max_target_features: int = 30, max_segment_features: int = 4) -> DescriptiveProfileJob:
        """Queue a full-dataset descriptive profile; the platform performs the scan."""
        dataset_id = _dataset_id(dataset)
        payload = {"target_column": target_column, "target_type": target_type, "comparison_column": comparison_column, "comparison_type": comparison_type, "include_summary": include_summary, "include_univariate": include_univariate, "include_target_relations": include_target_relations, "include_segments": include_segments, "include_graphic_summaries": include_graphic_summaries, "row_limit": row_limit, "max_target_features": max_target_features, "max_segment_features": max_segment_features}
        return DescriptiveProfileJob.from_api(dataset_id, self._request("POST", f"/datasets/{quote(dataset_id, safe='')}/descriptive-profile", json=payload))

    def get_descriptive_profile_status(self, job: DescriptiveProfileJob) -> DescriptiveProfileJob:
        """Fetch the current compact state of a descriptive-profile job."""
        return DescriptiveProfileJob.from_api(job.dataset_id, self._request("GET", f"/datasets/{quote(job.dataset_id, safe='')}/descriptive-profile/{quote(job.job_id, safe='')}"))

    def wait_for_descriptive_profile(self, job: DescriptiveProfileJob, *, poll_interval: float = 2.0, timeout: float | None = None, on_update: Callable[[DescriptiveProfileJob], None] | None = None) -> DescriptiveProfile:
        """Poll a profile job until it yields its full-dataset aggregate result."""
        started, current = time.monotonic(), job
        while not current.finished:
            if timeout is not None and time.monotonic() - started >= timeout:
                raise TimeoutError(f"Descriptive profile {job.job_id} did not finish within {timeout}s")
            time.sleep(poll_interval)
            current = self.get_descriptive_profile_status(job)
            if on_update is not None:
                on_update(current)
        if current.status != "completed" or current.result is None:
            raise ApiError(f"Descriptive profile {current.job_id} failed: {current.error or 'no error detail returned'}")
        return current.result

    def profile_dataset(self, dataset: DatasetRef, **options: Any) -> DescriptiveProfile:
        """Start and wait for a full-dataset descriptive profile convenience workflow."""
        return self.wait_for_descriptive_profile(self.start_descriptive_profile(dataset, **options))

    def visualize_dataset(self, dataset: DatasetRef, *, kind: str, x: str = "", y: str = "", group: str = "", aggregations: tuple[str, ...] | list[str] = ("average",), selected_groups: tuple[str, ...] | list[str] | None = None, x_epsilon: float = 0, y_epsilon: float = 0, trend: str = "none", polynomial_degree: int = 2, max_points: int = 2_000, bins: int = 80, feature_columns: tuple[str, ...] | list[str] = (), target_column: str = "", reduction_method: str = "pca", max_lag: int = 48, rolling_window: int = 12, driver_column: str = "") -> VisualizationResult:
        """Return a bounded chart result computed from a full platform-side scan."""
        dataset_id = _dataset_id(dataset)
        payload: dict[str, Any] = {"kind": kind, "x": x, "y": y, "group": group, "aggregations": list(aggregations), "x_epsilon": x_epsilon, "y_epsilon": y_epsilon, "trend": trend, "polynomial_degree": polynomial_degree, "max_points": max_points, "bins": bins, "feature_columns": list(feature_columns), "target_column": target_column, "reduction_method": reduction_method, "max_lag": max_lag, "rolling_window": rolling_window, "driver_column": driver_column}
        if selected_groups is not None:
            payload["selected_groups"] = list(selected_groups)
        return VisualizationResult.from_api(kind, self._request("POST", f"/datasets/{quote(dataset_id, safe='')}/visualization", json=payload))

    def visualization_group_values(self, dataset: DatasetRef, column: str, *, limit: int = 100) -> Mapping[str, Any]:
        """Return bounded full-dataset group choices for a visualization dimension."""
        dataset_id = _dataset_id(dataset)
        return self._request("POST", f"/datasets/{quote(dataset_id, safe='')}/visualization/groups", json={"column": column, "limit": limit})

    def start_time_series_analysis(self, dataset: DatasetRef, *, time_column: str, value_column: str, max_lag: int = 48, seasonal_period: int = 0, rolling_window: int = 12, max_points: int = 600, driver_column: str = "", driver_columns: tuple[str, ...] | list[str] = ()) -> TimeSeriesAnalysisJob:
        """Queue complete time-series diagnostics; processing remains on the platform."""
        dataset_id = _dataset_id(dataset)
        payload = {"time_column": time_column, "value_column": value_column, "max_lag": max_lag, "seasonal_period": seasonal_period, "rolling_window": rolling_window, "max_points": max_points, "driver_column": driver_column, "driver_columns": list(driver_columns)}
        return TimeSeriesAnalysisJob.from_api(dataset_id, self._request("POST", f"/datasets/{quote(dataset_id, safe='')}/time-series-analysis", json=payload))

    def get_time_series_analysis_status(self, job: TimeSeriesAnalysisJob) -> TimeSeriesAnalysisJob:
        """Fetch the current compact state of a time-series analysis job."""
        return TimeSeriesAnalysisJob.from_api(job.dataset_id, self._request("GET", f"/datasets/{quote(job.dataset_id, safe='')}/time-series-analysis/{quote(job.job_id, safe='')}"))

    def wait_for_time_series_analysis(self, job: TimeSeriesAnalysisJob, *, poll_interval: float = 2.0, timeout: float | None = None, on_update: Callable[[TimeSeriesAnalysisJob], None] | None = None) -> TimeSeriesAnalysis:
        """Poll a temporal-analysis job and return its compact completed result."""
        started, current = time.monotonic(), job
        while not current.finished:
            if timeout is not None and time.monotonic() - started >= timeout:
                raise TimeoutError(f"Time-series analysis {job.job_id} did not finish within {timeout}s")
            time.sleep(poll_interval)
            current = self.get_time_series_analysis_status(job)
            if on_update is not None:
                on_update(current)
        if current.status != "completed" or current.result is None:
            raise ApiError(f"Time-series analysis {current.job_id} failed: {current.error or 'no error detail returned'}")
        return current.result

    def analyze_time_series(self, dataset: DatasetRef, **options: Any) -> TimeSeriesAnalysis:
        """Start and wait for full-dataset temporal diagnostics."""
        return self.wait_for_time_series_analysis(self.start_time_series_analysis(dataset, **options))

    def present_descriptive_profile(self, result: DescriptiveProfile) -> DescriptiveProfilePresentation:
        """Return a compact notebook/terminal view of profile aggregates."""
        return DescriptiveProfilePresentation(result)

    def display_descriptive_profile(self, result: DescriptiveProfile) -> DescriptiveProfilePresentation:
        """Display profile aggregates in IPython or print their terminal view."""
        presentation = self.present_descriptive_profile(result)
        self._display_analysis_presentation(presentation)
        return presentation

    def present_visualization(self, result: VisualizationResult) -> VisualizationPresentation:
        """Return a notebook/terminal view of bounded visualization results."""
        return VisualizationPresentation(result)

    def display_visualization(self, result: VisualizationResult) -> VisualizationPresentation:
        """Display a bounded SVG/chart summary in IPython or print it in a terminal."""
        presentation = self.present_visualization(result)
        self._display_analysis_presentation(presentation)
        return presentation

    def present_time_series_analysis(self, result: TimeSeriesAnalysis) -> TimeSeriesAnalysisPresentation:
        """Return a compact notebook/terminal view of temporal diagnostics."""
        return TimeSeriesAnalysisPresentation(result)

    def display_time_series_analysis(self, result: TimeSeriesAnalysis) -> TimeSeriesAnalysisPresentation:
        """Display temporal diagnostics in IPython or print their terminal view."""
        presentation = self.present_time_series_analysis(result)
        self._display_analysis_presentation(presentation)
        return presentation

    @staticmethod
    def _display_analysis_presentation(presentation: _AnalysisPresentation) -> None:
        try:
            from IPython.display import display
        except ImportError:
            print(presentation)
        else:
            display(presentation)
