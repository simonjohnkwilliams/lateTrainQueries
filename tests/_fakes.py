"""Shared fake HTTP transport for offline Epic 2 tests (NFR2).

Not a test module (``python_files = test_*.py`` won't collect it). Provides a
``FakeSession`` with the ``.post(url, **kwargs)`` surface ``HspClient`` uses, so
tests run with no real network or credentials.
"""
from __future__ import annotations


class FakeResponse:
    def __init__(self, payload, status_error=None):
        self._payload = payload
        self._status_error = status_error

    def raise_for_status(self):
        if self._status_error is not None:
            raise self._status_error

    def json(self):
        return self._payload


class FakeSession:
    """Records POSTs; returns responses via a handler. Never touches the network.

    ``handler(url, kwargs) -> FakeResponse`` lets a test route serviceMetrics vs
    serviceDetails, inject failures, or count calls. Default returns ``{}``.
    """

    def __init__(self, handler=None):
        self.calls = []
        self._handler = handler

    def post(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        if self._handler is None:
            return FakeResponse({})
        return self._handler(url, kwargs)


class FakeSmtpTransport:
    """Records digest sends; never opens a real SMTP connection (AD-13).

    Callable as ``transport(msg, config)`` — the injectable seam for
    ``notification.send_digest``.
    """

    def __init__(self):
        self.sent = []

    def __call__(self, msg, config):
        self.sent.append((msg, config))
