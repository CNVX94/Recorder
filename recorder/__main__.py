"""`python -m recorder`: lo mismo que `daily` o `python recorder.py` (ver recorder/cli/app.py)."""
import sys


def main() -> int:
    if "--vulkan" in sys.argv:
        # La consulta de Vulkan en otro proceso (config/hardware.py): solo imprime y sale, sin
        # cargar la terminal ni el registro.
        from .config.hardware import sonda_vulkan

        return sonda_vulkan()
    from .registro import instalar

    instalar()  # las excepciones sin atrapar quedan en %LOCALAPPDATA%\Recorder\logs
    from .cli.app import arrancar

    return arrancar()


if __name__ == "__main__":
    sys.exit(main())
