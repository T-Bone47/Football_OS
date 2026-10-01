import os
from dotenv import load_dotenv
import pytest

load_dotenv()

# TEST FIXTURE OPT-IN. The legacy Phase 10-16 engine tests exercise engine
# logic on the demo fixtures those engines carry (players, outcomes, squads
# that were never observed). Production and every non-test run default to
# DEV_SEED off; tests/unit/test_phase18_truth.py proves the engines then start
# empty and never run a seed routine.
os.environ["DEV_SEED"] = "true"


@pytest.fixture(scope="session")
def postgres_url() -> str:
    return os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql+asyncpg://fios:fios@localhost:5432/fios_test",
    )
