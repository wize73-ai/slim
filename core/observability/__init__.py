"""Locked observability for the wize73 class chatbot.

Mounted by the main FastAPI app as a sub-app at ``/metrics`` so the
metrics tab survives any breakage in the student-editable chatbot router.
The locked module is the source of truth for what the dashboard sees;
students consume the API but can't change the numbers.

Public surface:

* :func:`create_metrics_app` — build the FastAPI sub-app, returns a
  ``FastAPI`` instance ready to be mounted at ``/metrics``.
* :class:`RingBuffer` — bounded thread-safe deque of :class:`TurnRecord`.
* :class:`TurnRecord`, :class:`TokenFlowSnapshot`,
  :class:`TimingSnapshot`, :class:`GuapoIndirectStats`,
  :class:`SlimHostStats` — the data records.
* :func:`project`, :func:`fit_coefficients`, :class:`ArchitectureSpec`,
  :class:`ProjectedTurn`, :class:`ProjectionResult`,
  :class:`ProjectionCoefficients` — the projection calculator.
* :class:`IndirectProvider`, :class:`DirectProvider`,
  :class:`GuapoStatsProvider` — the abstraction over guapo stats.
* :class:`SlimStatsClient` — the host-stats sidecar consumer.
"""

from core.observability.app import (
    MetricsState,
    ProjectionRequest,
    create_metrics_app,
)
from core.observability.guapo_provider import (
    DirectProvider,
    GuapoStatsProvider,
    IndirectProvider,
)
from core.observability.projection import (
    ArchitectureSpec,
    ProjectedTurn,
    ProjectionCoefficients,
    ProjectionResult,
    fit_coefficients,
    project,
)
from core.observability.records import (
    DEFAULT_RING_BUFFER_SIZE,
    GuapoIndirectStats,
    SlimHostStats,
    TimingSnapshot,
    TokenFlowSnapshot,
    TurnRecord,
)
from core.observability.ring_buffer import RingBuffer, aggregate_input_categories
from core.observability.slim_stats import SlimStatsClient

__all__ = [
    "DEFAULT_RING_BUFFER_SIZE",
    "ArchitectureSpec",
    "DirectProvider",
    "GuapoIndirectStats",
    "GuapoStatsProvider",
    "IndirectProvider",
    "MetricsState",
    "ProjectedTurn",
    "ProjectionCoefficients",
    "ProjectionRequest",
    "ProjectionResult",
    "RingBuffer",
    "SlimHostStats",
    "SlimStatsClient",
    "TimingSnapshot",
    "TokenFlowSnapshot",
    "TurnRecord",
    "aggregate_input_categories",
    "create_metrics_app",
    "fit_coefficients",
    "project",
]
