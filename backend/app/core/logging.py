"""Structured logging config."""
import structlog
def configure_logging(level: str = "INFO") -> None:
    structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(level))

