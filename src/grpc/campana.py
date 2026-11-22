"""Campaña completa de mediciones gRPC según el protocolo experimental.

Corre, en este orden:

  1. Una tanda de calentamiento por tamaño, que se descarta del análisis.
  2. Cinco repeticiones de 100 envíos por tamaño (100 B y 10 KiB).
  3. Los 20 intercambios que se usan para verificar el reloj de Lamport.
  4. Dos corridas concurrentes con los tres clientes enviando a la vez.

Deja los CSV en data/ y un manifiesto con las condiciones de la máquina y los
parámetros de cada corrida.

Uso, desde la raíz del repositorio:

    python src/grpc/campana.py
"""

import argparse
import csv
import statistics
from pathlib import Path

from experimento import ejecutar, etiqueta_tamano

CAMPOS_MANIFIESTO = (
    "prefijo", "etiqueta", "mecanismo", "modo", "envios", "tamano_b", "repeticion",
    "duracion_s", "eventos", "fecha_utc", "equipo", "usuario",
    "sistema_operativo", "version_so", "procesador", "nucleos", "memoria_gib",
    "python", "ejecucion",
)


def plan(envios, repeticiones, concurrencia):
    """Corridas del protocolo, en orden de ejecución."""
    corridas = []
    for tamano in (100, 10240):
        corridas.append(dict(
            etiqueta="warmup",
            prefijo=f"grpc_warmup_{envios}_{etiqueta_tamano(tamano)}_r0",
            envios=envios, tamano=tamano, concurrente=False, repeticion=0,
        ))
    for repeticion in range(1, repeticiones + 1):
        for tamano in (100, 10240):
            corridas.append(dict(
                etiqueta="medicion",
                prefijo=f"grpc_{envios}_{etiqueta_tamano(tamano)}_r{repeticion}",
                envios=envios, tamano=tamano, concurrente=False, repeticion=repeticion,
            ))
    for tamano in (100, 10240):
        corridas.append(dict(
            etiqueta="lamport",
            prefijo=f"grpc_20_{etiqueta_tamano(tamano)}",
            envios=20, tamano=tamano, concurrente=False, repeticion=1,
        ))
    for repeticion in range(1, concurrencia + 1):
        corridas.append(dict(
            etiqueta="concurrente",
            prefijo=f"grpc_concurrente_10kib_r{repeticion}",
            envios=102, tamano=10240, concurrente=True, repeticion=repeticion,
        ))
    return corridas


def resumen_latencias(ruta):
    with ruta.open(encoding="utf-8") as archivo:
        valores = [float(fila["rtt_ms"]) for fila in csv.DictReader(archivo)]
    valores.sort()
    posicion = max(int(round(0.95 * len(valores))) - 1, 0)
    return statistics.mean(valores), statistics.median(valores), valores[posicion]


def main():
    analizador = argparse.ArgumentParser(description=__doc__)
    analizador.add_argument("--salida", type=Path, default=Path("data"),
                            help="Carpeta donde se guardan los CSV")
    analizador.add_argument("--repeticiones", type=int, default=5)
    analizador.add_argument("--envios", type=int, default=100)
    analizador.add_argument("--concurrencia", type=int, default=2,
                            help="Cantidad de corridas concurrentes")
    analizador.add_argument("--manifiesto", type=Path, default=Path("data/runs_manifest.csv"))
    analizador.add_argument("--verbose", action="store_true")
    args = analizador.parse_args()

    if args.manifiesto.exists():
        analizador.error(f"El manifiesto {args.manifiesto} ya existe; elija otro nombre")

    corridas = plan(args.envios, args.repeticiones, args.concurrencia)
    metas = []
    print(f"Campaña gRPC: {len(corridas)} corridas\n")
    print(f"{'corrida':<28}{'envíos':>7}{'bytes':>8}{'modo':>12}{'mediana ms':>12}{'p95 ms':>10}")
    for corrida in corridas:
        prefijo = args.salida / corrida["prefijo"]
        try:
            meta = ejecutar(
                prefijo, corrida["envios"], corrida["tamano"], corrida["concurrente"],
                verboso=args.verbose, repeticion=corrida["repeticion"], etiqueta=corrida["etiqueta"],
            )
        except (FileExistsError, RuntimeError) as error:
            raise SystemExit(f"Falló {corrida['prefijo']}: {error}")
        metas.append(meta)
        media, mediana, p95 = resumen_latencias(prefijo.with_name(f"{prefijo.name}_latencias.csv"))
        print(f"{corrida['prefijo']:<28}{corrida['envios']:>7}{corrida['tamano']:>8}"
              f"{meta['modo']:>12}{mediana:>12.4f}{p95:>10.4f}")

    args.manifiesto.parent.mkdir(parents=True, exist_ok=True)
    with args.manifiesto.open("x", encoding="utf-8", newline="") as salida:
        escritor = csv.DictWriter(salida, fieldnames=CAMPOS_MANIFIESTO, extrasaction="ignore")
        escritor.writeheader()
        escritor.writerows(metas)

    print(f"\n{len(metas)} corridas registradas")
    print(f"Manifiesto: {args.manifiesto}")


if __name__ == "__main__":
    main()
