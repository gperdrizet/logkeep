"""
Gunicorn Configuration File for LogKeep Production

This configuration is optimized for a 4-core VPS running blue/green deployments.
Worker count: (2 × CPU cores) + 1 = 9 workers

For more configuration options, see:
https://docs.gunicorn.org/en/stable/settings.html
"""

import multiprocessing
import os

# Server Socket
bind = "0.0.0.0:8000"
backlog = 2048

# Worker Processes
workers = int(os.getenv("GUNICORN_WORKERS", "9"))
worker_class = "uvicorn.workers.UvicornWorker"
worker_connections = 1000
max_requests = 1000  # Recycle workers to prevent memory leaks
max_requests_jitter = 50  # Add randomness to prevent all workers restarting at once

# Timeouts
timeout = 120  # 2 minutes for long-running summarization tasks
graceful_timeout = 30  # Allow 30 seconds for graceful shutdown
keepalive = 5  # Keep connections alive for 5 seconds

# Server Mechanics
daemon = False
pidfile = None
umask = 0
user = None
group = None
tmp_upload_dir = None

# Logging
accesslog = "-"  # Log to stdout
errorlog = "-"  # Log to stderr
loglevel = os.getenv("LOG_LEVEL", "info")
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Process Naming
proc_name = "logkeep"

# Server Hooks
def on_starting(server):
    """Called just before the master process is initialized."""
    server.log.info("Starting Gunicorn server for LogKeep")
    server.log.info(f"Workers: {workers}")
    server.log.info(f"Worker class: {worker_class}")
    server.log.info(f"Binding to: {bind}")


def on_reload(server):
    """Called to recycle workers during a reload via SIGHUP."""
    server.log.info("Reloading Gunicorn workers")


def when_ready(server):
    """Called just after the server is started."""
    server.log.info("Gunicorn server is ready. Spawning workers")


def pre_fork(server, worker):
    """Called just before a worker is forked."""
    pass


def post_fork(server, worker):
    """Called just after a worker has been forked."""
    server.log.info(f"Worker spawned (pid: {worker.pid})")


def pre_exec(server):
    """Called just before a new master process is forked."""
    server.log.info("Forked child, re-executing")


def worker_int(worker):
    """Called just after a worker exited on SIGINT or SIGQUIT."""
    worker.log.info(f"Worker received INT or QUIT signal (pid: {worker.pid})")


def worker_abort(worker):
    """Called when a worker received the SIGABRT signal."""
    worker.log.info(f"Worker received SIGABRT signal (pid: {worker.pid})")


def pre_request(worker, req):
    """Called just before a worker processes the request."""
    worker.log.debug(f"{req.method} {req.path}")


def post_request(worker, req, environ, resp):
    """Called after a worker processes the request."""
    pass


def child_exit(server, worker):
    """Called just after a worker has been exited, in the master process."""
    server.log.info(f"Worker exited (pid: {worker.pid})")


def worker_exit(server, worker):
    """Called just after a worker has been exited, in the worker process."""
    pass


def nworkers_changed(server, new_value, old_value):
    """Called just after num_workers has been changed."""
    server.log.info(f"Number of workers changed from {old_value} to {new_value}")


def on_exit(server):
    """Called just before exiting Gunicorn."""
    server.log.info("Shutting down Gunicorn server")
