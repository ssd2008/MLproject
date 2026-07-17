from pathlib import Path
from urllib.parse import unquote, urlparse

import yaml


COMPOSE_FILE = Path(__file__).resolve().parents[1] / "docker-compose.yml"


def test_compose_postgres_credentials_are_consistent() -> None:
    compose = yaml.safe_load(COMPOSE_FILE.read_text(encoding="utf-8"))
    services = compose["services"]

    postgres_environment = services["postgres"]["environment"]
    expected_user = postgres_environment["POSTGRES_USER"]
    expected_password = postgres_environment["POSTGRES_PASSWORD"]
    expected_database = postgres_environment["POSTGRES_DB"]

    assert expected_password

    for service_name in ("migrate", "api"):
        database_url = services[service_name]["environment"]["DATABASE_URL"]
        parsed = urlparse(database_url)

        assert parsed.scheme == "postgresql"
        assert parsed.username == expected_user
        assert parsed.password is not None
        assert unquote(parsed.password) == expected_password
        assert parsed.hostname == "postgres"
        assert parsed.port == 5432
        assert parsed.path == f"/{expected_database}"
