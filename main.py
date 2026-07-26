"""
Dev server for PyApiGate.
"""
import os
from app import create_app

app = create_app(
    config_path=os.environ.get("CONFIG_PATH"),
)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
