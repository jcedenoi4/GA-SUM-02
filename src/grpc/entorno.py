"""Datos del equipo y de la sesión de trabajo.

Se usan para dos cosas: imprimir el banner de cada corrida (que deja ver en las
capturas el usuario, el nombre del equipo y la fecha y hora) y llenar el
manifiesto de corridas con las condiciones de la máquina que exige el protocolo
experimental.
"""

import ctypes
import os
import platform
import sys
from datetime import datetime, timezone


class _EstadoMemoria(ctypes.Structure):
    _fields_ = [
        ("dwLength", ctypes.c_ulong),
        ("dwMemoryLoad", ctypes.c_ulong),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


def memoria_total_gib():
    """Memoria física total en GiB, o None si el sistema no la reporta."""
    try:
        estado = _EstadoMemoria()
        estado.dwLength = ctypes.sizeof(_EstadoMemoria)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(estado)):
            return None
        return round(estado.ullTotalPhys / 1024 ** 3, 1)
    except (AttributeError, OSError):
        return None


def usuario():
    return os.environ.get("USERNAME") or os.environ.get("USER") or "desconocido"


def condiciones():
    """Condiciones de la máquina que se registran en el manifiesto."""
    return {
        "sistema_operativo": platform.system(),
        "version_so": platform.version(),
        "procesador": platform.processor() or platform.machine(),
        "nucleos": os.cpu_count(),
        "memoria_gib": memoria_total_gib(),
        "python": platform.python_version(),
        "equipo": platform.node(),
        "usuario": usuario(),
        "ejecucion": "tres procesos locales en 127.0.0.1",
    }


def banner(nombre):
    """Línea de identificación que imprime cada proceso al arrancar."""
    ahora = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return (
        f"[{ahora}] {nombre} | host={platform.node()} | usuario={usuario()} "
        f"| python={platform.python_version()} | pid={os.getpid()}"
    )
