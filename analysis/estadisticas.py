"""Estadísticas de latencia y rendimiento a partir de los CSV del protocolo.

Lee los manifiestos de data/protocolo/sesion_*/, toma las corridas medidas que
terminaron bien (descarta los calentamientos) y escribe en analysis/resultados/
estadisticas_por_corrida.csv, estadisticas_resumen.csv, tabla_latencias.tex y
tabla_rendimiento.tex. Las tablas se incluyen en el informe con \\input.

Media, mediana, desviación muestral (n - 1) y percentil 95 (interpolación
lineal) se calculan con todas las mediciones de cada combinación. El intervalo
del 95 % se calcula con las medias de las corridas, porque los 100 envíos de una
misma corrida comparten proceso y conexión y no son independientes entre sí.

El rendimiento es envíos / duración de la tanda. La duración la mide cada
programa con perf_counter(); wall_time_utc no sirve para esto porque en Windows
con Python 3.12 avanza en saltos de 15,6 ms.

Uso, desde la raíz del repositorio:

    python analysis/estadisticas.py
"""

import argparse
import math
from itertools import product
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
CLAVE = ["mecanismo", "tamano_bytes", "modo"]
ORDEN = list(product(("tcp", "grpc"), (100, 10240), ("secuencial", "concurrente")))
MODO_CSV = {"secuencial": "sequential", "concurrente": "concurrent"}
NOMBRE = {"tcp": "TCP", "grpc": "gRPC"}
CARGA = {100: "100 B", 10240: "10 KiB"}
MINIMO_CORRIDAS = 5

# Cuantil 0,975 de la t de Student según los grados de libertad (corridas - 1),
# para no añadir scipy como dependencia.
T_975 = {
    1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306,
    9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145, 15: 2.131,
    16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093, 20: 2.086, 21: 2.080, 22: 2.074,
    23: 2.069, 24: 2.064, 25: 2.060, 26: 2.056, 27: 2.052, 28: 2.048, 29: 2.045, 30: 2.042,
}


class DatosInvalidos(ValueError):
    """Los CSV de una corrida no coinciden con lo que declara el manifiesto."""


def leer_corrida(corrida):
    """Valida los CSV de una corrida y devuelve sus RTT en ms."""
    carpeta = Path(corrida.carpeta)
    latencias = pd.read_csv(carpeta / f"{corrida.prefijo}_latencias.csv",
                            dtype={"run_id": str, "message_id": str})
    if (
        len(latencias) != corrida.envios
        or latencias["message_id"].duplicated().any()
        or latencias["run_id"].nunique() != 1
        or set(latencias["payload_bytes"]) != {corrida.tamano_bytes}
        or set(latencias["mode"]) != {MODO_CSV[corrida.modo]}
        or not (latencias["rtt_ms"] > 0).all()
    ):
        raise DatosInvalidos(f"{corrida.prefijo}: las latencias no coinciden con el manifiesto")

    archivos = list(carpeta.glob(f"{corrida.prefijo}_eventos*.csv"))
    if not archivos:
        raise DatosInvalidos(f"{corrida.prefijo}: no hay CSV de eventos")
    eventos = pd.concat(pd.read_csv(ruta, dtype=str) for ruta in archivos)
    # Envío y recepción de la solicitud y de la respuesta.
    if (eventos["run_id"] == latencias["run_id"].iloc[0]).sum() != 4 * corrida.envios:
        raise DatosInvalidos(f"{corrida.prefijo}: no hay cuatro eventos por envío")
    return latencias["rtt_ms"].astype(float)


def estadisticos(rtt):
    return {
        "n": len(rtt),
        "media_ms": rtt.mean(),
        "mediana_ms": rtt.median(),
        "desviacion_ms": rtt.std(ddof=1),
        "p95_ms": rtt.quantile(0.95),
    }


def intervalo_95(valores):
    """Media de las corridas y semiamplitud de su intervalo de confianza del 95 %."""
    if len(valores) < 2:
        return valores.mean(), float("nan")
    t = T_975.get(len(valores) - 1, 1.960)
    return valores.mean(), t * valores.std(ddof=1) / math.sqrt(len(valores))


def resumir(por_corrida, mediciones):
    corridas = dict(list(por_corrida.groupby(CLAVE)))
    rtt = dict(list(mediciones.groupby(CLAVE)["rtt_ms"]))
    filas = []
    for clave in ORDEN:
        if clave not in corridas:
            continue
        grupo = corridas[clave]
        _, ic_latencia = intervalo_95(grupo["media_ms"])
        rendimiento, ic_rendimiento = intervalo_95(grupo["rendimiento_msg_s"])
        filas.append({
            **dict(zip(CLAVE, clave)),
            "corridas": len(grupo),
            **estadisticos(rtt[clave]),
            "ic95_media_ms": ic_latencia,
            "rendimiento_msg_s": rendimiento,
            "ic95_rendimiento_msg_s": ic_rendimiento,
        })
    return pd.DataFrame(filas)


def numero(valor, decimales):
    """Coma decimal y espacio fino para los miles, como en el resto del informe."""
    return f"{valor:,.{decimales}f}".replace(",", "\\,").replace(".", ",")


def tabla_latex(titulo, etiqueta, encabezados, filas):
    lineas = [
        "% Generado por analysis/estadisticas.py; no editar a mano.",
        "\\begin{table}[htbp]", "\\centering", "\\small",
        f"\\caption{{{titulo}}}", f"\\label{{{etiqueta}}}",
        f"\\begin{{tabular}}{{lll{'r' * (len(encabezados) - 3)}}}", "\\hline",
        " & ".join(encabezados) + " \\\\", "\\hline",
        *(" & ".join(fila) + " \\\\" for fila in filas),
        "\\hline", "\\end{tabular}", "\\end{table}",
    ]
    return "\n".join(lineas) + "\n"


def main():
    analizador = argparse.ArgumentParser(description=__doc__,
                                         formatter_class=argparse.RawDescriptionHelpFormatter)
    analizador.add_argument("--datos", type=Path, default=RAIZ / "data" / "protocolo")
    analizador.add_argument("--salida", type=Path, default=RAIZ / "analysis" / "resultados")
    args = analizador.parse_args()

    rutas = sorted(args.datos.glob("sesion_*/manifiesto.csv"))
    if not rutas:
        raise SystemExit(f"No hay sesiones en {args.datos}; ejecute antes analysis/ejecutar_protocolo.py")
    manifiesto = pd.concat((pd.read_csv(ruta, dtype={"prefijo": str}).assign(carpeta=str(ruta.parent))
                            for ruta in rutas), ignore_index=True)
    medidas = manifiesto[(manifiesto["fase"] == "medicion") & (manifiesto["estado"] == "ok")]
    if medidas.empty:
        raise SystemExit("Los manifiestos no tienen corridas medidas")

    filas, mediciones = [], []
    try:
        for corrida in medidas.itertuples(index=False):
            rtt = leer_corrida(corrida)
            datos = {"sesion": corrida.sesion, "mecanismo": corrida.mecanismo,
                     "tamano_bytes": corrida.tamano_bytes, "modo": corrida.modo,
                     "repeticion": corrida.repeticion}
            filas.append({**datos, **estadisticos(rtt), "duracion_s": corrida.duracion_reportada_s,
                          "rendimiento_msg_s": corrida.envios / corrida.duracion_reportada_s})
            mediciones.append(rtt.to_frame("rtt_ms").assign(**datos))
    except DatosInvalidos as error:
        raise SystemExit(f"Datos inválidos: {error}")
    por_corrida = pd.DataFrame(filas).sort_values(CLAVE + ["sesion", "repeticion"])
    resumen = resumir(por_corrida, pd.concat(mediciones, ignore_index=True))

    args.salida.mkdir(parents=True, exist_ok=True)
    por_corrida.to_csv(args.salida / "estadisticas_por_corrida.csv", index=False, float_format="%.6f")
    resumen.to_csv(args.salida / "estadisticas_resumen.csv", index=False, float_format="%.6f")

    etiquetas = [[NOMBRE[f.mecanismo], CARGA[f.tamano_bytes], f.modo] for f in resumen.itertuples()]
    (args.salida / "tabla_latencias.tex").write_text(tabla_latex(
        "Latencia de ida y vuelta por mecanismo, carga y modo", "tab:latencias",
        ["Mecanismo", "Carga", "Modo", "Media (ms)", "Mediana (ms)", "Desv. est. (ms)", "P95 (ms)"],
        [etiqueta + [numero(valor, 4) for valor in (f.media_ms, f.mediana_ms, f.desviacion_ms, f.p95_ms)]
         for etiqueta, f in zip(etiquetas, resumen.itertuples())],
    ), encoding="utf-8")
    (args.salida / "tabla_rendimiento.tex").write_text(tabla_latex(
        "Rendimiento por mecanismo, carga y modo", "tab:rendimiento",
        ["Mecanismo", "Carga", "Modo", "Corridas", "Mensajes/s", "IC 95 \\% ($\\pm$)"],
        [etiqueta + [str(f.corridas), numero(f.rendimiento_msg_s, 1), numero(f.ic95_rendimiento_msg_s, 1)]
         for etiqueta, f in zip(etiquetas, resumen.itertuples())],
    ), encoding="utf-8")

    pd.set_option("display.width", 160)
    print(f"Sesiones: {len(rutas)} | corridas medidas: {len(por_corrida)} | "
          f"descartadas (calentamiento o fallidas): {len(manifiesto) - len(medidas)}")
    print(resumen[CLAVE + ["corridas", "n", "media_ms", "mediana_ms", "desviacion_ms", "p95_ms",
                           "rendimiento_msg_s"]].to_string(index=False, float_format=lambda v: f"{v:.4f}"))
    for fila in resumen[resumen["corridas"] < MINIMO_CORRIDAS].itertuples():
        print(f"Aviso: {fila.mecanismo} {fila.tamano_bytes} B {fila.modo} tiene {fila.corridas} corridas; "
              f"el protocolo exige {MINIMO_CORRIDAS}")
    print(f"Resultados en {args.salida}")


if __name__ == "__main__":
    main()
