"""
Dev server for PyApiGate (FastAPI).
"""
import os
import uvicorn
from app import create_app

app = create_app(
    config_path=os.environ.get("CONFIG_PATH"),
)

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=5000, reload=True)
