"""Condiciones de la máquina que se guardan en cada sesión del protocolo.

Parte de entorno.condiciones(), que Angello escribió para los nodos gRPC, y le
agrega lo que necesita el análisis: el nombre comercial del procesador, el plan
de energía, las versiones de los paquetes y la resolución de los relojes

Para revisar qué se va a registrar:
    python analysis/entorno_experimento.py
"""

import json
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "grpc"))
from entorno import condiciones as condiciones_nodo

PAQUETES = ("grpcio", "grpcio-tools", "protobuf", "pandas", "matplotlib", "numpy")


def nombre_procesador():
    """En Windows, platform.processor() solo devuelve la familia del procesador."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as clave:
            return winreg.QueryValueEx(clave, "ProcessorNameString")[0].strip()
    except (ImportError, OSError):
        return platform.processor() or platform.machine()


def plan_energia():
    """Nombre del plan de energía activo, que influye en la frecuencia del procesador."""
    try:
        salida = subprocess.run(["powercfg", "/getactivescheme"], capture_output=True,
                                text=True, timeout=10, check=True).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    return salida[salida.rfind("(") + 1:-1] if salida.endswith(")") else salida


def versiones_paquetes():
    versiones = {}
    for paquete in PAQUETES:
        try:
            versiones[paquete] = metadata.version(paquete)
        except metadata.PackageNotFoundError:
            versiones[paquete] = None
    return versiones


def condiciones():
    datos = condiciones_nodo()
    # El tipo de ejecución depende del mecanismo; lo registra el manifiesto de cada corrida.
    datos.pop("ejecucion", None)
    datos.update({
        "registrado_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "edicion_so": platform.platform(),
        "procesador": nombre_procesador(),
        "plan_energia": plan_energia(),
        "resolucion_reloj_pared_s": time.get_clock_info("time").resolution,
        "resolucion_perf_counter_s": time.get_clock_info("perf_counter").resolution,
        "paquetes": versiones_paquetes(),
    })
    return datos


if __name__ == "__main__":
    print(json.dumps(condiciones(), ensure_ascii=False, indent=2))
