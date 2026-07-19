"""
Start the API server — same as your usual workflow:

    cd backend
    .venv\\Scripts\\activate
    py app.py

Docs: http://127.0.0.1:8000/docs
"""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure imports resolve when started from the backend folder
_BACKEND = Path(__file__).resolve().parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


def main() -> None:
    try:
        import uvicorn
    except ImportError:
        print("Missing dependencies. Run once:")
        print("  py -m pip install -r requirements.txt")
        sys.exit(1)

    print("\n  App Manager API")
    print("  http://127.0.0.1:8000")
    print("  Docs: http://127.0.0.1:8000/docs\n")

    # String path avoids clash between this file (app.py) and the app/ package
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        reload_dirs=[str(_BACKEND / "app")],
        reload_includes=[".env"],
    )


if __name__ == "__main__":
    main()
