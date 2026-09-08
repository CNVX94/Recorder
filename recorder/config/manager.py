import json
import pathlib
from typing import Optional, Union
from .schema import AppConfig

DEFAULT_CONFIG_PATH = pathlib.Path(__file__).resolve().parent.parent.parent / "config.json"


class ConfigManager:
    def __init__(self, path: Optional[Union[str, pathlib.Path]] = None):
        self.path = pathlib.Path(path) if path else DEFAULT_CONFIG_PATH

    def load(self) -> AppConfig:
        if not self.path.exists():
            return AppConfig()
        try:
            content = self.path.read_text(encoding="utf-8")
            data = json.loads(content)
            return AppConfig.from_dict(data)
        except Exception:
            return AppConfig()

    def save(self, config: AppConfig) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        content = json.dumps(config.to_dict(), ensure_ascii=False, indent=2)
        self.path.write_text(content, encoding="utf-8")
