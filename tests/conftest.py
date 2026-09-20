import os
from dotenv import load_dotenv
import pytest

load_dotenv()


@pytest.fixture(scope="session")
def postgres_url() -> str:
    return os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql+asyncpg://fios:fios@localhost:5432/fios_test",
    )
