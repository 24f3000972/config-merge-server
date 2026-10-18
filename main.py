import os
from pathlib import Path
from typing import List

import yaml
from dotenv import dotenv_values
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).parent

# ── Layer 1: Hardcoded defaults ───────────────────────────────────────────────
DEFAULTS: dict = {
    "port": 8000,
    "workers": 1,
    "debug": False,
    "log_level": "info",
    "api_key": "default-secret-000",
}

KNOWN_KEYS = set(DEFAULTS.keys())


# ── Helpers ───────────────────────────────────────────────────────────────────
def to_bool(v: str) -> bool:
    return str(v).strip().lower() in ("true", "1", "yes", "on")


def coerce(key: str, value):
    """Apply type coercion rules."""
    if key in ("port", "workers"):
        return int(value)
    if key == "debug":
        return to_bool(value)
    return str(value)


def apply_env_dict(config: dict, env: dict) -> dict:
    """
    Merge an env-var dict (APP_* prefix or NUM_WORKERS alias) into config.
    """
    for raw_key, raw_val in env.items():
        # Alias: NUM_WORKERS → workers
        if raw_key == "NUM_WORKERS":
            config["workers"] = coerce("workers", raw_val)
            continue
        if raw_key.startswith("APP_"):
            cfg_key = raw_key[4:].lower()   # strip "APP_", lowercase
            if cfg_key in KNOWN_KEYS:
                config[cfg_key] = coerce(cfg_key, raw_val)
    return config


# ── Layer 2: YAML (loaded once at startup) ───────────────────────────────────
_yaml_config: dict = {}
_yaml_path = BASE_DIR / "config.development.yaml"
if _yaml_path.exists():
    with open(_yaml_path) as f:
        _yaml_config = yaml.safe_load(f) or {}


# ── Layer 3: .env file (loaded once at startup) ──────────────────────────────
_dotenv_config: dict = {}
_dotenv_path = BASE_DIR / ".env"
if _dotenv_path.exists():
    _dotenv_config = dotenv_values(str(_dotenv_path))


# ── Endpoint ──────────────────────────────────────────────────────────────────
@app.get("/effective-config")
def effective_config(set: List[str] = Query(default=[])):
    # 1. Defaults
    config = dict(DEFAULTS)

    # 2. YAML layer
    for k, v in _yaml_config.items():
        k = k.lower()
        if k in KNOWN_KEYS:
            config[k] = coerce(k, v)

    # 3. .env layer  (APP_* prefix + NUM_WORKERS alias)
    config = apply_env_dict(config, _dotenv_config)

    # 4. OS environment variables  (APP_* prefix + NUM_WORKERS alias)
    config = apply_env_dict(config, dict(os.environ))

    # 5. CLI overrides — highest precedence
    for override in set:
        if "=" in override:
            k, v = override.split("=", 1)
            k = k.strip().lower()
            if k in KNOWN_KEYS:
                config[k] = coerce(k, v)
            else:
                # unknown key: store as string
                config[k] = v

    # Always mask api_key
    config["api_key"] = "****"

    return JSONResponse(content=config)


@app.get("/health")
def health():
    return {"status": "ok"}
