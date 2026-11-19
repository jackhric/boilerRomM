"""Counting the bytes an install downloads, whatever it downloads and however it goes about it."""
from collections.abc import AsyncIterator, Callable, Mapping
from contextlib import AbstractAsyncContextManager
from types import TracebackType
from typing import Any, Protocol

import aiohttp

Report = Callable[[int, int], None]   # bytes so far, bytes in all (0 when the server does not say)


class Session(Protocol):
    def get(self, url: str, *, headers: Mapping[str, str] | None = None) -> AbstractAsyncContextManager[Any]: ...


class _Body:
    def __init__(self, body: aiohttp.StreamReader, report: Report, total: int) -> None:
        self._body, self._report, self._total, self._done = body, report, total, 0

    async def iter_chunked(self, size: int) -> AsyncIterator[bytes]:
        async for chunk in self._body.iter_chunked(size):
            self._done += len(chunk)
            self._report(self._done, self._total)
            yield chunk

    def __getattr__(self, name: str) -> object:
        return getattr(self._body, name)


class _Response:
    def __init__(self, response: aiohttp.ClientResponse, report: Report) -> None:
        self._response = response
        self.content = _Body(response.content, report, int(getattr(response, "content_length", 0) or 0))

    def __getattr__(self, name: str) -> object:
        return getattr(self._response, name)


class _Request:
    def __init__(self, request: AbstractAsyncContextManager[aiohttp.ClientResponse], report: Report) -> None:
        self._request, self._report = request, report

    async def __aenter__(self) -> _Response:
        return _Response(await self._request.__aenter__(), self._report)

    async def __aexit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None) -> bool | None:
        return await self._request.__aexit__(exc_type, exc, tb)


class Counted:
    """A session whose downloads report their progress. Only bodies read in chunks count: API answers do not."""

    def __init__(self, session: aiohttp.ClientSession, report: Report) -> None:
        self._session, self._report = session, report

    def get(self, url: str, *, headers: Mapping[str, str] | None = None) -> _Request:
        return _Request(self._session.get(url, headers=headers), self._report)

    def __getattr__(self, name: str) -> object:
        return getattr(self._session, name)
