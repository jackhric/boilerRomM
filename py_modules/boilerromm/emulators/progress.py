"""Counting the bytes an install downloads, whatever it downloads and however it goes about it."""
from collections.abc import Callable

Report = Callable[[int, int], None]   # bytes so far, bytes in all (0 when the server does not say)


class _Body:
    def __init__(self, body, report: Report, total: int):
        self._body, self._report, self._total, self._done = body, report, total, 0

    async def iter_chunked(self, size: int):
        async for chunk in self._body.iter_chunked(size):
            self._done += len(chunk)
            self._report(self._done, self._total)
            yield chunk

    def __getattr__(self, name):
        return getattr(self._body, name)


class _Response:
    def __init__(self, response, report: Report):
        self._response = response
        self.content = _Body(response.content, report, int(getattr(response, "content_length", 0) or 0))

    def __getattr__(self, name):
        return getattr(self._response, name)


class _Request:
    def __init__(self, request, report: Report):
        self._request, self._report = request, report

    async def __aenter__(self):
        return _Response(await self._request.__aenter__(), self._report)

    async def __aexit__(self, *exc):
        return await self._request.__aexit__(*exc)


class Counted:
    """A session whose downloads report their progress. Only bodies read in chunks count: API answers do not."""

    def __init__(self, session, report: Report):
        self._session, self._report = session, report

    def get(self, url, **kwargs):
        return _Request(self._session.get(url, **kwargs), self._report)

    def __getattr__(self, name):
        return getattr(self._session, name)
