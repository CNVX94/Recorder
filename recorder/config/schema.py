import dataclasses
import pathlib
from typing import Dict, List, Optional


@dataclasses.dataclass
class AppConfig:
    notes_dir: str = dataclasses.field(
        default_factory=lambda: str(pathlib.Path.home() / "Documents" / "Dailies")
    )
    caps_dir: str = dataclasses.field(
        default_factory=lambda: str(pathlib.Path.home() / "Documents" / "Dailies" / "capturas")
    )
    keywords: List[str] = dataclasses.field(
        default_factory=lambda: ["pendiente", "bloqueo", "captura"]
    )
    mic: bool = True
    out_dev: str = ""   # Nombre WASAPI de la salida a capturar ("" = predeterminada)
    mic_dev: str = ""   # Nombre WASAPI del micrófono ("" = predeterminado)
    screen: int = 0     # 0 = todas las pantallas; 1..n = monitor n
    model: str = "small"  # tiny, base, small, medium, large-v3-turbo
    beam_size: int = 5

    # Vocabulario de contexto (Initial prompt) para guiar terminos tecnicos y nombres.
    # Vacio a proposito: cada usuario pone el suyo. Ver config.example.json.
    vocab: str = ""

    # Frases fantasma que Whisper inventa en silencios/ruido (lista negra)
    ignore: List[str] = dataclasses.field(
        default_factory=lambda: [
            "suscríbete",
            "próximo vídeo",
            "gracias por ver",
            "hasta la próxima",
            "subtítulos",
            "amara.org",
            "gracias por estar aquí",
            "dale like",
            "nos vemos en el próximo",
        ]
    )

    # Correcciones personales post-transcripcion: palabra completa (mal -> bien).
    # Vacio a proposito: se llena con lo que tu Whisper confunda. Ver config.example.json.
    fixes: Dict[str, str] = dataclasses.field(default_factory=dict)

    # Umbrales heurísticos anti-alucinaciones
    no_speech_threshold: float = 0.6  # Descartar si probabilidad de no-voz >= umbral
    logprob_threshold: float = -1.0    # Descartar si confianza logarítmica <= umbral
    compression_ratio_threshold: float = 2.4  # Descartar repeticiones si zlib ratio excede umbral
    repetition_penalty: float = 1.1

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "AppConfig":
        valid_fields = {f.name for f in dataclasses.fields(cls)}
        filtered = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered)
