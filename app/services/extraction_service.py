from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
from dataclasses import dataclass
from io import BytesIO
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from pypdf import PdfReader

from app.config import Settings
from app.exceptions import InvalidDocumentError, UnsupportedMediaTypeError


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
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

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
        await self._validate_public_url(url)
        timeout = httpx.Timeout(self._settings.url_fetch_timeout_seconds)
        headers = {"User-Agent": self._settings.url_user_agent}
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            max_redirects=self._settings.url_fetch_max_redirects,
            headers=headers,
        ) as client:
            async with client.stream("GET", url) as response:
                response.raise_for_status()
                await self._validate_public_url(str(response.url))
                content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
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
                            f"Remote document exceeds the {self._settings.max_document_size_mb} MB limit"
                        )

        encoding = response.encoding or "utf-8"
        raw = bytes(data).decode(encoding, errors="replace")
        if content_type == "text/plain":
            return self.extract_text(raw)
        return self.extract_text(self._html_to_text(raw))

    @staticmethod
    def _html_to_text(html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript", "svg", "nav", "footer", "header", "form"]):
            tag.decompose()
        main = soup.find("main") or soup.find("article") or soup.body or soup
        return main.get_text("\n", strip=True)

    @staticmethod
    async def _validate_public_url(url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise InvalidDocumentError("Only absolute HTTP(S) URLs are supported")
        try:
            addresses = await asyncio.to_thread(
                socket.getaddrinfo,
                parsed.hostname,
                parsed.port or (443 if parsed.scheme == "https" else 80),
                type=socket.SOCK_STREAM,
            )
        except socket.gaierror as exc:
            raise InvalidDocumentError("URL hostname cannot be resolved") from exc

        for address in addresses:
            ip = ipaddress.ip_address(address[4][0])
            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_multicast
                or ip.is_reserved
                or ip.is_unspecified
            ):
                raise InvalidDocumentError("URLs resolving to private or local networks are forbidden")
