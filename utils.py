#!/usr/local/bin/python3
# coding: utf-8

import logging
import time
import coloredlogs

def setup_logger():
    coloredlogs.install(
        level=logging.INFO,
        fmt="[%(asctime)s %(filename)s:%(lineno)d %(levelname).1s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

def sizeof_fmt(num: int, suffix="B"):
    for unit in ["", "Ki", "Mi", "Gi", "Ti", "Pi", "Ei", "Zi"]:
        if abs(num) < 1024.0:
            return "%3.1f%s%s" % (num, unit, suffix)
        num /= 1024.0
    return "%.1f%s%s" % (num, "Yi", suffix)

class TokenBucket:
    def __init__(self, tokens, fill_rate):
        self.capacity = tokens
        self.tokens = tokens
        self.fill_rate = fill_rate
        self.timestamp = time.time()

    def consume(self, tokens):
        now = time.time()
        self.tokens += (now - self.timestamp) * self.fill_rate
        if self.tokens > self.capacity:
            self.tokens = self.capacity
        self.timestamp = now
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False

def rate_limit(seconds):
    def decorator(func):
        last_called = {}
        def wrapper(*args, **kwargs):
            now = time.time()
            if func in last_called and now - last_called[func] < seconds:
                return
            last_called[func] = now
            return func(*args, **kwargs)
        return wrapper
    return decorator