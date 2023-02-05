from __future__ import annotations

from time import time


class Timer:
    def __init__(self) -> None:
        self.started = 0.0
        self.finished = 0.0
        self.duration = 0.0

    def __enter__(self) -> Timer:
        self.started = time()
        return self

    def __exit__(self, *args) -> None:
        self.finished = time()
        self.duration = self.finished - self.started

    def s(self) -> float:
        return self.duration

    def ms(self) -> float:
        return self.duration * 1e3

    def us(self) -> float:
        return self.duration * 1e6

    def ns(self) -> float:
        return self.duration * 1e9

    def log_s(self, msg: str) -> None:
        print(f"{msg} in {self.s()} s")

    def log_ms(self, msg: str) -> None:
        print(f"{msg} in {self.ms()} ms")

    def log_us(self, msg: str) -> None:
        print(f"{msg} in {self.us()} us")

    def log_ns(self, msg: str) -> None:
        print(f"{msg} in {self.ns()} ns")
