"""
gateway/app/core/logging_config.py - Zero-Bloat Structured JSON Logging Engine
Provides single-line JSON log formatting using the Python standard library.
Compatible with Docker json-file driver, Vector, Promtail, Fluentd, and Grafana Loki.
Preserves existing diagnostic in-memory ring buffers without regression.
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Optional


class JSONLogFormatter(logging.Formatter):
    """
    Standard-library based JSON log formatter.
    Generates single-line JSON log strings with timestamp, level, logger, message,
    and optional trace_id and exception details.
    """

    def format(self, record: logging.LogRecord) -> str:
        # Generate ISO 8601 UTC timestamp
        dt = datetime.fromtimestamp(record.created, tz=timezone.utc)
        timestamp_str = dt.isoformat(timespec="milliseconds")

        log_data = {
            "timestamp": timestamp_str,
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Include trace_id if present
        trace_id = getattr(record, "trace_id", None)
        if trace_id:
            log_data["trace_id"] = str(trace_id)

        # Include exception trace if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data, ensure_ascii=False)


def configure_gateway_logging(ring_buffer_handler: Optional[logging.Handler] = None) -> None:
    """
    Configures logging across the gateway application.
    Selects JSON formatter if LOG_FORMAT == 'json' (default in production/docker)
    or standard human-readable text formatter if LOG_FORMAT == 'text'.
    """
    log_format = os.getenv("LOG_FORMAT", "json").lower().strip()
    log_level_str = os.getenv("LOG_LEVEL", "INFO").upper().strip()
    log_level = getattr(logging, log_level_str, logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Remove existing stream handlers to prevent duplicate stdout logs
    for h in list(root_logger.handlers):
        if isinstance(h, logging.StreamHandler) and not (ring_buffer_handler and h is ring_buffer_handler):
            root_logger.removeHandler(h)

    # Add console stream handler
    console_handler = logging.StreamHandler(sys.stdout)
    if log_format == "json":
        console_handler.setFormatter(JSONLogFormatter())
    else:
        console_handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
        )
    root_logger.addHandler(console_handler)

    # Attach ring buffer handler if provided (for /api/diagnostics/logs)
    if ring_buffer_handler and ring_buffer_handler not in root_logger.handlers:
        root_logger.addHandler(ring_buffer_handler)
