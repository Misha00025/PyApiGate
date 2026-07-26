import os
from app import create_app

app = create_app(
    config_path=os.environ.get("CONFIG_PATH"),
)
