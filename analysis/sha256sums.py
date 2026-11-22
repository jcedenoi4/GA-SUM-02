"""Genera o comprueba data/SHA256SUMS con el hash de cada CSV original.

El archivo usa el formato de sha256sum (hash, dos espacios y ruta relativa a
data/), así que también se puede comprobar con `sha256sum -c SHA256SUMS` desde
data/ en Linux o Git Bash.

Uso, desde la raíz del repositorio:

    python analysis/sha256sums.py              genera data/SHA256SUMS
    python analysis/sha256sums.py --verificar  compara los CSV con el archivo
"""

import argparse
import hashlib
from pathlib import Path

DATOS = Path(__file__).resolve().parents[1] / "data"
ARCHIVO = DATOS / "SHA256SUMS"


def sha256(ruta):
    resumen = hashlib.sha256()
    with ruta.open("rb") as archivo:
        for bloque in iter(lambda: archivo.read(1 << 16), b""):
            resumen.update(bloque)
    return resumen.hexdigest()


def csv_originales():
    return sorted(ruta.relative_to(DATOS).as_posix() for ruta in DATOS.rglob("*.csv"))


def generar():
    lineas = [f"{sha256(DATOS / ruta)}  {ruta}\n" for ruta in csv_originales()]
    with ARCHIVO.open("w", encoding="utf-8", newline="\n") as salida:
        salida.writelines(lineas)
    print(f"{len(lineas)} archivos -> {ARCHIVO}")


def verificar():
    esperados = {}
    for linea in ARCHIVO.read_text(encoding="utf-8").splitlines():
        hash_esperado, ruta = linea.split("  ", 1)
        esperados[ruta] = hash_esperado

    distintos = [ruta for ruta, hash_esperado in esperados.items()
                 if not (DATOS / ruta).is_file() or sha256(DATOS / ruta) != hash_esperado]
    sin_hash = [ruta for ruta in csv_originales() if ruta not in esperados]
    for ruta in distintos:
        print(f"no coincide o falta: {ruta}")
    for ruta in sin_hash:
        print(f"sin hash registrado: {ruta}")
    print(f"{len(esperados) - len(distintos)} de {len(esperados)} archivos coinciden")
    if distintos or sin_hash:
        raise SystemExit(1)


def main():
    analizador = argparse.ArgumentParser(description=__doc__,
                                         formatter_class=argparse.RawDescriptionHelpFormatter)
    analizador.add_argument("--verificar", action="store_true")
    args = analizador.parse_args()
    if args.verificar:
        verificar()
    else:
        generar()


if __name__ == "__main__":
    main()
