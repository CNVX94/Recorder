import dataclasses
from typing import List, Optional
import numpy as np


@dataclasses.dataclass
class AudioChunk:
    timestamp: float
    kind: str  # "out" o "mic"
    audio: np.ndarray  # float32 mono a 16 kHz


@dataclasses.dataclass
class TranscriptionResult:
    timestamp_str: str
    kind: str
    text: str
    hits: List[str] = dataclasses.field(default_factory=list)
    screenshot_ref: Optional[str] = None
