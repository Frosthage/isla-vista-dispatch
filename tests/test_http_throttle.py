import threading
import time

from scrape import http


def test_throttle_spaces_concurrent_starts_one_second_apart():
    http._last_hit.pop("throttle-test.example", None)
    starts: list[float] = []
    lock = threading.Lock()

    def hit():
        http._throttle("throttle-test.example")
        with lock:
            starts.append(time.monotonic())

    threads = [threading.Thread(target=hit) for _ in range(4)]
    t0 = time.monotonic()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    starts.sort()
    assert starts[-1] - t0 < 3.6          # 4 starts fit in ~3 seconds, not exponentially more
    gaps = [b - a for a, b in zip(starts, starts[1:])]
    assert all(g >= 0.95 for g in gaps)
