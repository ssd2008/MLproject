from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
from collections.abc import Collection
from dataclasses import dataclass
from io import BytesIO
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from pypdf import PdfReader

from app.config import Settings
from app.exceptions import InvalidDocumentError, UnsupportedMediaTypeError

_REDIRECT_STATUS_CODES = {301, 302, 303, 307, 308}


@dataclass(frozen=True, slots=True)
class PageSpan:
    page_number: int
    char_start: int
    char_end: int


@dataclass(frozen=True, slots=True)
class TimedTextSpan:
    start_seconds: float
    end_seconds: float
    char_start: int
    char_end: int


@dataclass(frozen=True, slots=True)
class ExtractedDocument:
    text: str
    page_spans: tuple[PageSpan, ...] = ()
    time_spans: tuple[TimedTextSpan, ...] = ()


def clean_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


class ExtractionService:
    def __init__(
        self,
        settings: Settings,
        *,
        http_transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._settings = settings
        self._http_transport = http_transport

    def extract_text(self, raw_text: str) -> ExtractedDocument:
        text = clean_text(raw_text)
        if not text:
            raise InvalidDocumentError("The document text is empty after normalization")
        return ExtractedDocument(text=text)

    async def extract_pdf(self, data: bytes) -> ExtractedDocument:
        if len(data) > self._settings.max_document_size_bytes:
            raise InvalidDocumentError(
                f"PDF exceeds the {self._settings.max_document_size_mb} MB limit"
            )
        return await asyncio.to_thread(self._extract_pdf_sync, data)

    @staticmethod
    def _extract_pdf_sync(data: bytes) -> ExtractedDocument:
        try:
            reader = PdfReader(BytesIO(data))
        except Exception as exc:
            raise InvalidDocumentError("The uploaded file is not a readable PDF") from exc

        parts: list[str] = []
        spans: list[PageSpan] = []
        cursor = 0
        for page_number, page in enumerate(reader.pages, start=1):
            try:
                page_text = clean_text(page.extract_text() or "")
            except Exception as exc:
                raise InvalidDocumentError(f"Failed to extract PDF page {page_number}") from exc
            if not page_text:
                continue
            if parts:
                parts.append("\n\n")
                cursor += 2
            start = cursor
            parts.append(page_text)
            cursor += len(page_text)
            spans.append(PageSpan(page_number=page_number, char_start=start, char_end=cursor))

        text = "".join(parts)
        if not text:
            raise InvalidDocumentError(
                "The PDF contains no extractable text; scanned PDFs require OCR"
            )
        return ExtractedDocument(text=text, page_spans=tuple(spans))

    async def extract_url(self, url: str) -> ExtractedDocument:
        timeout = httpx.Timeout(self._settings.url_fetch_timeout_seconds)
        headers = {"User-Agent": self._settings.url_user_agent}
        current_url = url

        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=False,
            headers=headers,
            trust_env=False,
            transport=self._http_transport,
        ) as client:
            for redirect_count in range(self._settings.url_fetch_max_redirects + 1):
                resolved_addresses = await self._resolve_public_addresses(current_url)
                async with client.stream("GET", current_url) as response:
                    self._validate_connected_peer(response, resolved_addresses)

                    if response.status_code in _REDIRECT_STATUS_CODES:
                        if redirect_count >= self._settings.url_fetch_max_redirects:
                            raise InvalidDocumentError("URL exceeded the redirect limit")
                        location = response.headers.get("location")
                        if not location:
                            raise InvalidDocumentError("URL redirect is missing the Location header")
                        current_url = urljoin(str(response.url), location)
                        continue

                    response.raise_for_status()
                    content_type = (
                        response.headers.get("content-type", "").split(";", 1)[0].lower()
                    )
                    allowed = {"text/html", "application/xhtml+xml", "text/plain"}
                    if content_type not in allowed:
                        raise UnsupportedMediaTypeError(
                            f"URL content type {content_type or 'unknown'} is not supported"
                        )
                    data = bytearray()
                    async for block in response.aiter_bytes():
                        data.extend(block)
                        if len(data) > self._settings.max_document_size_bytes:
                            raise InvalidDocumentError(
                                "Remote document exceeds the "
                                f"{self._settings.max_document_size_mb} MB limit"
                            )
                    encoding = response.encoding or "utf-8"

                raw = bytes(data).decode(encoding, errors="replace")
                if content_type == "text/plain":
                    return self.extract_text(raw)
                return self.extract_text(self._html_to_text(raw))

        raise InvalidDocumentError("URL could not be fetched")

    @staticmethod
    def _html_to_text(html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript", "svg", "nav", "footer", "header", "form"]):
            tag.decompose()
        main = soup.find("main") or soup.find("article") or soup.body or soup
        return main.get_text("\n", strip=True)

    @staticmethod
    def _is_forbidden_address(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
        return (
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_multicast
            or address.is_reserved
            or address.is_unspecified
        )

    @classmethod
    async def _validate_public_url(cls, url: str) -> None:
        """Validate that a URL resolves only to public network addresses."""
        await cls._resolve_public_addresses(url)

    @classmethod
    async def _resolve_public_addresses(
        cls,
        url: str,
    ) -> set[ipaddress.IPv4Address | ipaddress.IPv6Address]:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise InvalidDocumentError("Only absolute HTTP(S) URLs are supported")
        if parsed.username is not None or parsed.password is not None:
            raise InvalidDocumentError("URLs containing credentials are forbidden")

        try:
            literal_address = ipaddress.ip_address(parsed.hostname)
        except ValueError:
            literal_address = None

        if literal_address is not None:
            addresses = {literal_address}
        else:
            try:
                resolved = await asyncio.to_thread(
                    socket.getaddrinfo,
                    parsed.hostname,
                    parsed.port or (443 if parsed.scheme == "https" else 80),
                    type=socket.SOCK_STREAM,
                )
            except socket.gaierror as exc:
                raise InvalidDocumentError("URL hostname cannot be resolved") from exc
            addresses = {ipaddress.ip_address(item[4][0].split("%", 1)[0]) for item in resolved}

        if not addresses or any(cls._is_forbidden_address(address) for address in addresses):
            raise InvalidDocumentError("URLs resolving to private or local networks are forbidden")
        return addresses

    @classmethod
    def _validate_connected_peer(
        cls,
        response: httpx.Response,
        resolved_addresses: Collection[ipaddress.IPv4Address | ipaddress.IPv6Address],
    ) -> None:
        network_stream = response.extensions.get("network_stream")
        if network_stream is None or not hasattr(network_stream, "get_extra_info"):
            return
        server_address = network_stream.get_extra_info("server_addr")
        if not server_address:
            return
        try:
            peer = ipaddress.ip_address(str(server_address[0]).split("%", 1)[0])
        except ValueError as exc:
            raise InvalidDocumentError("Could not validate the URL connection address") from exc
        if cls._is_forbidden_address(peer) or peer not in resolved_addresses:
            raise InvalidDocumentError("URL connection address changed after DNS validation")
