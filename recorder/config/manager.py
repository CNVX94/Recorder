import json
import pathlib
import shutil
from typing import Optional, Union

from .schema import AppConfig

DEFAULT_CONFIG_PATH = pathlib.Path(__file__).resolve().parent.parent.parent / "config.json"
SUFIJO_ROTO = ".roto"


class ConfigManager:
    """Carga y guarda la configuración de la aplicación.

    Que el archivo no exista es normal: primer arranque, valores de fábrica y a correr.
    Que exista pero no se pueda leer es otra cosa, y **no se calla**: el motivo queda en
    `last_error` para que la interfaz lo muestre, y se aparta una copia del archivo ilegible.

    Ese respaldo importa porque, sin él, la secuencia es silenciosa y destructiva: la
    configuración se corrompe, la aplicación arranca con los valores de fábrica sin avisar,
    el usuario abre Opciones, pulsa Guardar, y su vocabulario y sus correcciones desaparecen
    para siempre.
    """

    def __init__(self, path: Optional[Union[str, pathlib.Path]] = None):
        self.path = pathlib.Path(path) if path else DEFAULT_CONFIG_PATH
        self.last_error = ""  # vacío mientras la carga vaya bien

    def load(self) -> AppConfig:
        self.last_error = ""
        if not self.path.exists():
            return AppConfig()  # primer arranque: valores de fábrica, sin aviso
        try:
            # utf-8-sig tolera la marca BOM que dejan algunos editores y PowerShell
            data = json.loads(self.path.read_text(encoding="utf-8-sig"))
            return AppConfig.from_dict(data)
        except Exception as e:
            copia = self._apartar_roto()
            detalle = f" Copia del original en «{copia.name}»." if copia else ""
            self.last_error = (
                f"No se pudo leer «{self.path.name}» ({e.__class__.__name__}). "
                f"Se usan los valores de fábrica, así que las notas irán a la carpeta "
                f"por defecto y se pierden tu vocabulario y tus correcciones.{detalle} "
                f"No guardes desde Opciones hasta revisarlo."
            )
            return AppConfig()

    def _apartar_roto(self) -> Optional[pathlib.Path]:
        """Copia el archivo ilegible a un lado para que un guardado posterior no lo pise."""
        destino = self.path.with_name(self.path.name + SUFIJO_ROTO)
        try:
            if not destino.exists():  # ponytail: una sola copia, no una por cada arranque
                shutil.copy2(self.path, destino)
            return destino
        except OSError:
            return None

    def save(self, config: AppConfig) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        content = json.dumps(config.to_dict(), ensure_ascii=False, indent=2)
        self.path.write_text(content, encoding="utf-8")
        self.last_error = ""  # tras guardar bien, el archivo vuelve a ser legible
