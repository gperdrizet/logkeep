"""Prometheus metrics definitions."""
from prometheus_client import Counter, Histogram, Gauge

# Request metrics
REQUEST_COUNT = Counter(
    'logkeep_requests_total',
    'Total number of requests',
    ['method', 'endpoint', 'status']
)

REQUEST_DURATION = Histogram(
    'logkeep_request_duration_seconds',
    'Request duration in seconds',
    ['method', 'endpoint']
)

# Link metrics
LINK_SUBMISSIONS = Counter(
    'logkeep_link_submissions_total',
    'Total number of link submissions',
    ['status']
)

# User metrics
ACTIVE_USERS = Gauge(
    'logkeep_active_users',
    'Number of currently logged in users'
)

# Error metrics
PROCESSING_ERRORS = Counter(
    'logkeep_processing_errors_total',
    'Total number of processing errors',
    ['error_type']
)

# Database metrics
DB_CONNECTIONS = Gauge(
    'logkeep_db_connections',
    'Number of active database connections'
)

# Summarization metrics
SUMMARIZATION_DURATION = Histogram(
    'logkeep_summarization_duration_seconds',
    'Time taken to generate summaries',
    ['status']  # success or error
)

SUMMARIZATION_COUNT = Counter(
    'logkeep_summarizations_total',
    'Total number of summarization attempts',
    ['status']  # success or error
)
