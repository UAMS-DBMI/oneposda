import sys
from pathlib import Path

# The deployment sets PYTHONPATH=<posdatools>/python; mirror that for tests
# so `import posda...` resolves the same way it does in the container.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
