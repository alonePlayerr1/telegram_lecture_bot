import random
import time
from typing import Callable, TypeVar, Iterable

T = TypeVar("T")

def retry(
    fn: Callable[[], T],
    *,
    tries: int = 5,
    base_delay: float = 0.8,
    max_delay: float = 12.0,
    retry_on: tuple[type[BaseException], ...] = (Exception,),
) -> T:
    """Простой экспоненциальный retry с jitter. Используйте для сетевых вызовов."""
    last_err: BaseException | None = None
    for attempt in range(1, tries + 1):
        try:
            return fn()
        except retry_on as e:
            last_err = e
            if attempt >= tries:
                break
            delay = min(max_delay, base_delay * (2 ** (attempt - 1)))
            delay = delay * (0.7 + random.random() * 0.6)  # jitter 0.7..1.3
            time.sleep(delay)
    assert last_err is not None
    raise last_err
