"""Genera los stubs de Python a partir de proto/lamport.proto.

Uso, desde la raíz del repositorio:

    python src/grpc/generar_stubs.py

Requiere grpcio-tools (ver requirements.txt). Los archivos generados
(lamport_pb2.py y lamport_pb2_grpc.py) se conservan en el repositorio para que
el proyecto se pueda ejecutar sin volver a generar el código.
"""

import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
PROTO = RAIZ / "proto" / "lamport.proto"
DESTINO = Path(__file__).resolve().parent


def main():
    if not PROTO.is_file():
        raise SystemExit(f"No se encontró el contrato: {PROTO}")

    orden = [
        sys.executable, "-m", "grpc_tools.protoc",
        f"-I{PROTO.parent}",
        f"--python_out={DESTINO}",
        f"--grpc_python_out={DESTINO}",
        str(PROTO),
    ]
    print("Ejecutando:", " ".join(orden), flush=True)
    subprocess.run(orden, check=True)

    for nombre in ("lamport_pb2.py", "lamport_pb2_grpc.py"):
        archivo = DESTINO / nombre
        if not archivo.is_file():
            raise SystemExit(f"grpcio-tools no generó {archivo}")
        print(f"Generado: {archivo.relative_to(RAIZ)} ({archivo.stat().st_size} B)")


if __name__ == "__main__":
    main()
