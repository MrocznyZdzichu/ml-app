"""Compatibility aggregate for online-serving client operations."""

from .deployments import DeploymentClientMixin
from .inference import InferenceClientMixin
from .online_monitoring import OnlineMonitoringClientMixin


class ServingClientMixin(
    DeploymentClientMixin,
    InferenceClientMixin,
    OnlineMonitoringClientMixin,
):
    """Compose deployment, inference, and monitoring workflows."""
