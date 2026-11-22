"""Estadísticas de latencia y rendimiento a partir de los CSV del protocolo.

Lee los manifiestos de data/protocolo/sesion_*/, toma las corridas medidas que
terminaron bien (descarta los calentamientos) y escribe en analysis/resultados/:

  estadisticas_por_corrida.csv, estadisticas_resumen.csv y comparacion_mecanismos.csv
  tabla_latencias.tex, tabla_rendimiento.tex y tabla_comparacion.tex
  grafico_cajas.png y grafico_barras.png

El informe incluye las tablas con \\input y los gráficos con \\includegraphics.

Media, mediana, desviación muestral (n - 1) y percentil 95 (interpolación
lineal) se calculan con todas las mediciones de cada combinación. El intervalo
del 95 % se calcula con las medias de las corridas, porque los 100 envíos de una
misma corrida comparten proceso y conexión y no son independientes entre sí.

El rendimiento es envíos / duración de la tanda. La duración la mide cada
programa con perf_counter(); wall_time_utc no sirve para esto porque en Windows
con Python 3.12 avanza en saltos de 15,6 ms.

La comparación expresa cada medida de gRPC como diferencia porcentual respecto
a TCP: (gRPC - TCP) / TCP * 100. Un valor positivo indica que gRPC tiene un
valor mayor.

Uso, desde la raíz del repositorio:

    python analysis/estadisticas.py
"""

import argparse
import math
from itertools import product
from pathlib import Path

import pandas as pd
from matplotlib.figure import Figure
from matplotlib.ticker import ScalarFormatter

RAIZ = Path(__file__).resolve().parents[1]
CLAVE = ["mecanismo", "tamano_bytes", "modo"]
CONDICIONES = list(product((100, 10240), ("secuencial", "concurrente")))
ORDEN = [(mecanismo, *condicion) for mecanismo in ("tcp", "grpc") for condicion in CONDICIONES]
MODO_CSV = {"secuencial": "sequential", "concurrente": "concurrent"}
NOMBRE = {"tcp": "TCP", "grpc": "gRPC"}
CARGA = {100: "100 B", 10240: "10 KiB"}
COLORES = {"tcp": "#4c72b0", "grpc": "#dd8452"}
MEDIDAS_COMPARADAS = ("media_ms", "mediana_ms", "p95_ms", "rendimiento_msg_s")
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


def resumir(por_corrida, rtt):
    corridas = dict(list(por_corrida.groupby(CLAVE)))
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


def comparar(resumen):
    """Pone TCP y gRPC lado a lado en cada carga y modo medidos con ambos."""
    indice = resumen.set_index(CLAVE)
    filas = []
    for tamano, modo in CONDICIONES:
        if ("tcp", tamano, modo) not in indice.index or ("grpc", tamano, modo) not in indice.index:
            continue
        tcp, grpc = indice.loc[("tcp", tamano, modo)], indice.loc[("grpc", tamano, modo)]
        fila = {"tamano_bytes": tamano, "modo": modo}
        for medida in MEDIDAS_COMPARADAS:
            fila[f"tcp_{medida}"] = tcp[medida]
            fila[f"grpc_{medida}"] = grpc[medida]
            fila[f"diferencia_{medida}_pct"] = (grpc[medida] - tcp[medida]) / tcp[medida] * 100
        filas.append(fila)
    return pd.DataFrame(filas)


def numero(valor, decimales):
    """Coma decimal y espacio fino para los miles, como en el resto del informe."""
    return f"{valor:,.{decimales}f}".replace(",", "\\,").replace(".", ",")


def porcentaje(valor):
    return f"{valor:+.1f}".replace(".", ",").replace("-", "$-$") + " \\%"


def tabla_latex(titulo, etiqueta, encabezados, filas, columnas_texto=3):
    lineas = [
        "% Generado por analysis/estadisticas.py; no editar a mano.",
        "\\begin{table}[htbp]", "\\centering", "\\small",
        f"\\caption{{{titulo}}}", f"\\label{{{etiqueta}}}",
        f"\\begin{{tabular}}{{{'l' * columnas_texto}{'r' * (len(encabezados) - columnas_texto)}}}", "\\hline",
        " & ".join(encabezados) + " \\\\", "\\hline",
        *(" & ".join(fila) + " \\\\" for fila in filas),
        "\\hline", "\\end{tabular}", "\\end{table}",
    ]
    return "\n".join(lineas) + "\n"


def grafico_cajas(rtt, ruta):
    claves = [clave for clave in ORDEN if clave in rtt]
    figura = Figure(figsize=(10, 4.8))
    eje = figura.subplots()
    cajas = eje.boxplot(
        [rtt[clave] for clave in claves],
        tick_labels=[f"{NOMBRE[m]}\n{CARGA[t]}\n{modo}" for m, t, modo in claves],
        patch_artist=True, medianprops={"color": "black"},
        flierprops={"marker": ".", "markersize": 3, "alpha": 0.5},
    )
    for caja, (mecanismo, _, _) in zip(cajas["boxes"], claves):
        caja.set_facecolor(COLORES[mecanismo])
    # Los RTT van de 0,08 ms a varios ms; en escala lineal las cajas de TCP quedan aplastadas.
    eje.set_yscale("log")
    eje.yaxis.set_major_formatter(ScalarFormatter())
    eje.set_ylabel("RTT (ms, escala logarítmica)")
    eje.set_title("Distribución del RTT de cada envío medido")
    eje.grid(axis="y", which="both", alpha=0.3)
    figura.tight_layout()
    figura.savefig(ruta, dpi=200)


def grafico_barras(resumen, ruta):
    indice = resumen.set_index(CLAVE)
    figura = Figure(figsize=(11, 4.5))
    ejes = figura.subplots(1, 2)
    ancho = 0.38
    paneles = (("media_ms", "ic95_media_ms", "Latencia media (ms)"),
               ("rendimiento_msg_s", "ic95_rendimiento_msg_s", "Rendimiento (mensajes/s)"))
    for eje, (medida, intervalo, titulo) in zip(ejes, paneles):
        for desplazamiento, mecanismo in zip((-ancho / 2, ancho / 2), NOMBRE):
            posiciones, alturas, errores = [], [], []
            for posicion, (tamano, modo) in enumerate(CONDICIONES):
                if (mecanismo, tamano, modo) in indice.index:
                    fila = indice.loc[(mecanismo, tamano, modo)]
                    posiciones.append(posicion + desplazamiento)
                    alturas.append(fila[medida])
                    errores.append(fila[intervalo])
            eje.bar(posiciones, alturas, ancho, yerr=errores, capsize=4,
                    color=COLORES[mecanismo], label=NOMBRE[mecanismo])
        eje.set_xticks(range(len(CONDICIONES)), [f"{CARGA[t]}\n{modo}" for t, modo in CONDICIONES])
        eje.set_ylabel(titulo)
        eje.grid(axis="y", alpha=0.3)
    ejes[0].legend()
    figura.suptitle("Media de las corridas con intervalo de confianza del 95 %")
    figura.tight_layout()
    figura.savefig(ruta, dpi=200)


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
    rtt = dict(list(pd.concat(mediciones, ignore_index=True).groupby(CLAVE)["rtt_ms"]))
    resumen = resumir(por_corrida, rtt)
    comparacion = comparar(resumen)

    args.salida.mkdir(parents=True, exist_ok=True)
    por_corrida.to_csv(args.salida / "estadisticas_por_corrida.csv", index=False, float_format="%.6f")
    resumen.to_csv(args.salida / "estadisticas_resumen.csv", index=False, float_format="%.6f")
    comparacion.to_csv(args.salida / "comparacion_mecanismos.csv", index=False, float_format="%.6f")
    grafico_cajas(rtt, args.salida / "grafico_cajas.png")
    grafico_barras(resumen, args.salida / "grafico_barras.png")

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
    if not comparacion.empty:
        (args.salida / "tabla_comparacion.tex").write_text(tabla_latex(
            "RTT medio y diferencia de gRPC respecto a TCP, (gRPC $-$ TCP) / TCP", "tab:comparacion",
            ["Carga", "Modo", "TCP (ms)", "gRPC (ms)", "Media", "Mediana", "P95", "Rendimiento"],
            [[CARGA[f.tamano_bytes], f.modo, numero(f.tcp_media_ms, 4), numero(f.grpc_media_ms, 4),
              *(porcentaje(getattr(f, f"diferencia_{medida}_pct")) for medida in MEDIDAS_COMPARADAS)]
             for f in comparacion.itertuples()],
            columnas_texto=2,
        ), encoding="utf-8")

    pd.set_option("display.width", 160)
    print(f"Sesiones: {len(rutas)} | corridas medidas: {len(por_corrida)} | "
          f"descartadas (calentamiento o fallidas): {len(manifiesto) - len(medidas)}")
    print(resumen[CLAVE + ["corridas", "n", "media_ms", "mediana_ms", "desviacion_ms", "p95_ms",
                           "rendimiento_msg_s"]].to_string(index=False, float_format=lambda v: f"{v:.4f}"))
    if not comparacion.empty:
        diferencias = [f"diferencia_{medida}_pct" for medida in MEDIDAS_COMPARADAS]
        print("\nDiferencia de gRPC respecto a TCP (%):")
        print(comparacion[["tamano_bytes", "modo", *diferencias]].to_string(
            index=False, float_format=lambda v: f"{v:+.1f}"))
    for fila in resumen[resumen["corridas"] < MINIMO_CORRIDAS].itertuples():
        print(f"Aviso: {fila.mecanismo} {fila.tamano_bytes} B {fila.modo} tiene {fila.corridas} corridas; "
              f"el protocolo exige {MINIMO_CORRIDAS}")
    print(f"Resultados en {args.salida}")


if __name__ == "__main__":
    main()
