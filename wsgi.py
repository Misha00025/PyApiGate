import os
from app import create_app
from app.auth_strategies import rsa_jwt_auth_strategy

public_key_path = os.environ.get("PUBLIC_KEY_PATH", "public.pem")
auth_strategy = None
try:
    with open(public_key_path, "rb") as f:
        public_key = f.read()
    oidc_issuer = os.environ.get("OIDC_ISSUER")
    auth_strategy = rsa_jwt_auth_strategy(public_key, oidc_issuer)
except FileNotFoundError:
    pass

application = create_app(
    config_path=os.environ.get("CONFIG_PATH"),
    auth_strategy=auth_strategy,
)
