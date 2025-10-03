import os
import shutil
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
CORE_DIR = ROOT_DIR / ".core"
TESTS_DIR = ROOT_DIR / "tests"
RESULTS_DIR = ROOT_DIR / "results"
TEMPLATES_DIR = CORE_DIR / "templates"
TEMPLATE_PATH = TEMPLATES_DIR / "test-block.md"
TEMP_DIR = CORE_DIR / ".temp"
MODELS_DIR = ROOT_DIR / "models"

DEFAULT_TEMPERATURE = float(os.getenv("AUTO_TEST_TEMPERATURE", "0.1"))
DEFAULT_PROVIDER_NAME = os.getenv("AUTO_TEST_PROVIDER", "LM Studio")


def ensure_directories() -> None:
    """Ensure that shared directories exist."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    MODELS_DIR.mkdir(parents=True, exist_ok=True)


def get_env_setting(key: str, default: str) -> str:
    """Read an environment variable with a default fallback."""
    return os.getenv(key, default)


def reset_temp_directory() -> None:
    """Clear and recreate the temporary directory used for staging markdown blocks."""
    if TEMP_DIR.exists():
        shutil.rmtree(TEMP_DIR)
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
