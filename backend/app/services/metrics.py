"""Custom Prometheus metrics for scan pipeline.

Default HTTP/latency metrics come from ``prometheus-fastapi-instrumentator``.
Anything domain-specific (scan volume, confidence distribution, e2e latency)
is defined here so it shows up alongside.
"""
from prometheus_client import Counter, Histogram

scan_total = Counter(
    "dermscan_scan_total",
    "Total scans submitted, labeled by terminal status",
    ["status"],
)

scan_confidence_histogram = Histogram(
    "dermscan_scan_confidence",
    "Distribution of scan confidence values",
    buckets=(0.0, 0.5, 0.6, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 1.0),
)

scan_latency_seconds = Histogram(
    "dermscan_scan_latency_seconds",
    "End-to-end inference latency per scan",
    buckets=(0.5, 1, 2, 5, 10, 30, 60, 120),
)
