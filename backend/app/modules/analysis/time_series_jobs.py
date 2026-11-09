from app.modules.analysis.dataset_jobs import DatasetAnalysisJobs


class TimeSeriesAnalysisJobs(DatasetAnalysisJobs):
    key_prefix = "time-series-analysis-owner"
    task_name = "app.worker.tasks.time_series_analysis_dataset"
    not_found_message = "Time-series analysis job not found"
