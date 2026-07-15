import sys
from loguru import logger

logger.remove()

logger.add(
    sys.stderr,
    level="INFO",
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
)

# Keep file logging opt-in to avoid local disk churn in normal runs.
# logger.add("logs/file_{time}.log", level="DEBUG", rotation="10 MB")

__all__ = ["logger"]
