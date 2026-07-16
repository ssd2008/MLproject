from app.main import create_app


def test_openapi_contains_core_endpoints() -> None:
    schema = create_app().openapi()
    paths = schema["paths"]
    assert "/api/v1/documents" in paths
    assert "/api/v1/documents/{document_id}/index" in paths
    assert "/api/v1/search" in paths
    assert "/api/v1/answer" in paths
