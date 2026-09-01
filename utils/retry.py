"""Generic retry-with-backoff helper used for MT5 and Telegram calls."""

from __future__ import annotations

import functools
import time
from typing import Callable, Tuple, Type, TypeVar

from utils.logger import get_logger

logger = get_logger("retry")

T = TypeVar("T")


def retry_with_backoff(
    max_attempts: int = 5,
    base_delay: float = 2.0,
    max_delay: float = 60.0,
    exceptions: Tuple[Type[BaseException], ...] = (Exception,),
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator that retries the wrapped function with exponential backoff.

    The wrapped function is called; if it raises one of `exceptions`, it is
    retried up to `max_attempts` times with delay doubling each time
    (capped at `max_delay`). If all attempts fail, the last exception is
    re-raised.
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            delay = base_delay
            last_exc: BaseException | None = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as exc:  # noqa: BLE001 - intentional broad catch
                    last_exc = exc
                    logger.warning(
                        "Attempt %s/%s for %s failed: %s",
                        attempt,
                        max_attempts,
                        func.__name__,
                        exc,
                    )
                    if attempt < max_attempts:
                        time.sleep(delay)
                        delay = min(delay * 2, max_delay)
            logger.error("All %s attempts for %s failed.", max_attempts, func.__name__)
            assert last_exc is not None
            raise last_exc

        return wrapper

    return decorator
