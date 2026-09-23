import sys
from pathlib import Path

# Make the FastAPI app importable (main, papi.*) from the tests directory.
APP_DIR = Path(__file__).resolve().parent.parent / "app"
sys.path.insert(0, str(APP_DIR))
