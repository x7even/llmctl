import time
from functools import wraps
from typing import Any, Callable

__all__ = ["retry"]


def retry(
    max_attempts: int = 3,
    delay