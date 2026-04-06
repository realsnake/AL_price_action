import os
import sys
from pathlib import Path


os.environ.setdefault("ALPACA_API_KEY", "test-key")
os.environ.setdefault("ALPACA_SECRET_KEY", "test-secret")

backend_dir = Path(__file__).resolve().parents[1]
backend_dir_str = str(backend_dir)
if backend_dir_str not in sys.path:
    sys.path.insert(0, backend_dir_str)
