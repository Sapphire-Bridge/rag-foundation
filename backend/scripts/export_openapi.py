import os
import sys
from pathlib import Path

# Force mock mode during export to avoid secret requirements
os.environ.setdefault("GEMINI_MOCK_MODE", "true")
os.environ.setdefault("GEMINI_API_KEY", "export-mock-key")

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from fastapi.openapi.utils import get_openapi  # noqa: E402
from app.main import create_app  # noqa: E402
import yaml  # noqa: E402

app = create_app()
spec = get_openapi(title=app.title, version=app.version, routes=app.routes)
openapi_path = BACKEND_ROOT / "openapi.yaml"
openapi_path.write_text(yaml.safe_dump(spec, sort_keys=False), encoding="utf-8")
print("Wrote openapi.yaml")
