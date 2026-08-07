import time


def retry_loop(fn, retries=3, delay_seconds=2, *args, **kwargs):
    last_exception = None
    for attempt in range(1, retries + 1):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            last_exception = exc
            if attempt < retries:
                time.sleep(delay_seconds)
    raise last_exception
