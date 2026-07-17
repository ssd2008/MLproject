import ipaddress

import httpx
import pytest

from app.config import Settings
from app.exceptions import InvalidDocumentError
from app.services.extraction_service import ExtractionService


@pytest.mark.asyncio
async def test_url_redirect_to_private_network_is_rejected(monkeypatch) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"Location": "http://127.0.0.1/private"})

    service = ExtractionService(Settings(), http_transport=httpx.MockTransport(handler))

    async def resolve(url: str):
        if "127.0.0.1" in url:
            raise InvalidDocumentError("private address")
        return {ipaddress.ip_address("93.184.216.34")}

    monkeypatch.setattr(service, "_resolve_public_addresses", resolve)

    with pytest.raises(InvalidDocumentError, match="private address"):
        await service.extract_url("https://example.org/start")


@pytest.mark.asyncio
async def test_each_public_redirect_is_validated(monkeypatch) -> None:
    requested_urls: list[str] = []
    validated_urls: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        if request.url.path == "/start":
            return httpx.Response(302, headers={"Location": "/article"})
        return httpx.Response(
            200,
            headers={"Content-Type": "text/html; charset=utf-8"},
            text="<html><main><h1>Заголовок</h1><p>Полезный текст</p></main></html>",
        )

    service = ExtractionService(Settings(), http_transport=httpx.MockTransport(handler))

    async def resolve(url: str):
        validated_urls.append(url)
        return {ipaddress.ip_address("93.184.216.34")}

    monkeypatch.setattr(service, "_resolve_public_addresses", resolve)

    result = await service.extract_url("https://example.org/start")

    assert validated_urls == [
        "https://example.org/start",
        "https://example.org/article",
    ]
    assert requested_urls == validated_urls
    assert result.text == "Заголовок\nПолезный текст"


@pytest.mark.asyncio
async def test_url_credentials_are_rejected() -> None:
    service = ExtractionService(Settings())

    with pytest.raises(InvalidDocumentError, match="credentials"):
        await service._resolve_public_addresses("https://user:password@example.org/")
