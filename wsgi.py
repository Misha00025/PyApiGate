import os
from app import create_app

application = create_app(
    config_path=os.environ.get("CONFIG_PATH"),
)
