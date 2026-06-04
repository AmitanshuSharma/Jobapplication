# src/crawlers/exceptions.py
"""Typed exception classes for all crawler modules.

Inputs: message string; optional source URL.
Outputs: exception instances carrying .url attribute.
"""


class CrawlerFetchError(Exception):
    """Raised when an HTTP request or page render fails."""

    def __init__(self, message: str, url: str = "") -> None:
        super().__init__(message)
        self.url = url


class CrawlerParseError(Exception):
    """Raised when HTML or JSON content cannot be parsed into the expected structure."""

    def __init__(self, message: str, url: str = "") -> None:
        super().__init__(message)
        self.url = url
