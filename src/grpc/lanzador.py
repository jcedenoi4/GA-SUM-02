"""Lanzador de una corrida gRPC para el protocolo experimental común.

Es el punto de entrada que espera `analysis/ejecutar_protocolo.py`. Acepta las
mismas opciones que el cliente TCP (`--count`, `--size`, `--concurrent`,
`--output`), deja `<prefijo>_eventos.csv` y `<prefijo>_latencias.csv`, e imprime
la duración de la tanda con el formato «Duración: <segundos> s», que es el que
el script de análisis lee.

Uso, desde la raíz del repositorio:

    python src/grpc/lanzador.py --count 100 --size 10240 --output data/protocolo/sesion_x/grpc_10kib_secuencial_r01
    python src/grpc/lanzador.py --count 100 --size 100 --concurrent --output .../grpc_100b_concurrente_r01
"""

from experimento import main

if __name__ == "__main__":
    main()
