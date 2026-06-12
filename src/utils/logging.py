import logging
from contextlib import contextmanager
from time import monotonic


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        force=True,
    )


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def format_bytes(size: int) -> str:
    value = float(size)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TiB"


@contextmanager
def timed_stage(logger: logging.Logger, stage: str, **details):
    suffix = " | " + ", ".join(f"{key}={value}" for key, value in details.items()) if details else ""
    logger.info("START %s%s", stage, suffix)
    started = monotonic()
    try:
        yield
    except Exception:
        logger.exception("FAILED %s | elapsed=%.1fs", stage, monotonic() - started)
        raise
    logger.info("DONE %s | elapsed=%.1fs", stage, monotonic() - started)
