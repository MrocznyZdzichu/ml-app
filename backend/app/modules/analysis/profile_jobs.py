from app.modules.analysis.dataset_jobs import DatasetAnalysisJobs


class DescriptiveProfileJobs(DatasetAnalysisJobs):
    key_prefix = "descriptive-profile-owner"
    task_name = "app.worker.tasks.descriptive_profile_dataset"
    not_found_message = "Profile job not found"
