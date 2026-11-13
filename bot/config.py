import os
from dataclasses import dataclass
from pathlib import Path


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class Config:
    token: str
    backend_url: str
    service_key: str
    http_timeout: float = 10.0
    cache_seconds: float = 5.0


def load_env_file(path):
    """Fill missing environment variables from a local ``bot/.env`` (never overrides the real environment)."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding='utf-8').splitlines():
        line = raw.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        name, _, value = line.partition('=')
        os.environ.setdefault(name.strip(), value.strip().strip('"').strip("'"))


def load_config():
    load_env_file(Path(__file__).with_name('.env'))
    values = {name: os.environ.get(name, '').strip() for name in ('BOT_TOKEN', 'BACKEND_URL', 'BOT_SERVICE_KEY')}
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise ConfigError(f'Missing environment variables: {", ".join(missing)}')
    return Config(token=values['BOT_TOKEN'], backend_url=values['BACKEND_URL'].rstrip('/'), service_key=values['BOT_SERVICE_KEY'])
