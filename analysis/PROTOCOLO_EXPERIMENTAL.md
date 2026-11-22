# Protocolo experimental común para TCP y gRPC

Responsable: Darwin Joel Sánchez Vera. Este documento fija cómo medimos los dos mecanismos para que la comparación sea justa. La sesión oficial `data/protocolo/sesion_20261122T011620Z/` se ejecutó con este protocolo, con TCP y gRPC en la misma sesión.

## 1. Qué se mide

| Elemento | Definición |
| --- | --- |
| Variable independiente | Mecanismo (`tcp`, `grpc`), tamaño de la carga (100 B y 10 240 B = 10 KiB) y modo (`secuencial`, `concurrente`). |
| Latencia (RTT) | Tiempo de ida y vuelta de un envío, en ms, medido por el nodo emisor con `time.perf_counter()` desde antes de sellar el envío hasta decodificar la respuesta. Columna `rtt_ms` del CSV de latencias. |
| Rendimiento | Envíos completados / duración de la tanda, en mensajes por segundo. La duración la mide el propio programa con `perf_counter()` y la imprime como `Duración: <s> s`. |
| Condiciones fijas | Interfaz local `127.0.0.1`, puertos 5000–5002, carga ASCII (`"x" * tamaño`), respuesta eco, conexiones/canales abiertos antes de medir, ruta circular A→B, B→C, C→A. |

No usamos `wall_time_utc` para calcular el rendimiento. En Windows, Python 3.12 y las versiones anteriores leen el reloj de pared con una resolución de 15,6 ms (`time.get_clock_info("time").resolution` = 0.015625), mayor que la duración de muchas corridas. `condiciones.json` registra la resolución de ambos relojes en cada sesión.

## 2. Diseño

- Combinaciones: 2 mecanismos × 2 tamaños × 2 modos = 8.
- Por cada combinación: 1 corrida de calentamiento, que se descarta, y 5 corridas medidas de 100 envíos.
- Total por sesión completa: 8 calentamientos + 40 corridas medidas = 48 corridas y 4 000 RTT válidos.
- Primero se ejecutan los calentamientos. Luego, en cada repetición, se recorren las 8 combinaciones en un orden que rota una posición por repetición. Así, si la máquina cambia durante la sesión, el efecto no recae siempre en el mismo mecanismo.
- Prueba concurrente: los tres nodos envían a la vez en grupos de tres (A→B, B→C y C→A), sincronizados con una barrera. Con 100 envíos son 33 grupos de tres y un envío final.

## 3. Preparación de la máquina

Antes de cada sesión oficial:

1. Conectar el portátil a la corriente y anotar el plan de energía (queda en `condiciones.json`).
2. Cerrar navegadores, Teams/Discord, sincronización de OneDrive y descargas. Mantener abierta solo la terminal `cmd.exe`.
3. Activar el entorno virtual con las versiones de `requirements.txt`.
4. Ejecutar TCP y gRPC **en la misma sesión**, con el mismo intérprete y sin reiniciar la máquina entre ambos.
5. No usar el equipo mientras corre la sesión.

## 4. Ejecución

Desde la raíz del repositorio, en `cmd.exe`:

```bat
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
python analysis\entorno_experimento.py
python analysis\ejecutar_protocolo.py --mecanismos tcp grpc
python analysis\estadisticas.py
python analysis\sha256sums.py
python analysis\sha256sums.py --verificar
```

`ejecutar_protocolo.py` acepta `--mecanismos`, `--repeticiones` (mínimo 5) y `--envios`; los tamaños y los modos son fijos. Crea `data/protocolo/sesion_<AAAAMMDDTHHMMSSZ>/`, espera 1 s entre corridas y no sobrescribe nada. Si una corrida falla, la sesión se detiene; el manifiesto y el archivo `_salida.txt` conservan lo ocurrido. Una sesión incompleta no se borra; se ejecuta otra sesión completa.

## 5. Organización de los datos

```text
data/protocolo/sesion_<fecha>/
├── condiciones.json                  SO, procesador, memoria, Python, paquetes, relojes, parámetros
├── manifiesto.csv                    una fila por corrida (incluye la duración de la tanda)
├── tcp_100b_secuencial_cal_*.csv     calentamiento (no entra al análisis)
├── tcp_100b_secuencial_r01_eventos.csv
├── tcp_100b_secuencial_r01_latencias.csv
├── tcp_100b_secuencial_r01_salida.txt
└── ...
```

Nombre de cada corrida: `<mecanismo>_<100b|10kib>_<secuencial|concurrente>_<cal|rNN>`.

Columnas de `manifiesto.csv`: `sesion, orden, mecanismo, tamano_bytes, modo, fase, repeticion, envios, prefijo, inicio_utc, fin_utc, duracion_reportada_s, estado, tipo_ejecucion`. `estado` vale `ok` o describe por qué falló la corrida.

Los CSV generados no se editan. `data/SHA256SUMS` guarda el hash SHA-256 de cada CSV de `data/` en el formato de `sha256sum`; `analysis/sha256sums.py` lo genera y, con `--verificar`, informa qué archivos no coinciden o no tienen hash. El archivo `.gitattributes` indica a git que no convierta los finales de línea dentro de `data/`; sin esa regla, Git para Windows escribe los CSV con CRLF y los hashes no coincidirían entre equipos.

## 6. Interfaz que debe cumplir cada mecanismo

El orquestador invoca a cada mecanismo con los mismos argumentos que ya acepta `src/sockets/client.py`:

```text
python <programa> --count 100 --size {100|10240} [--concurrent] --output <prefijo>
```

| Mecanismo | Programa | Estado |
| --- | --- | --- |
| TCP | `src/sockets/client.py` | Cumple la interfaz. |
| gRPC | `src/grpc/lanzador.py` | Cumple la interfaz; delega en `src/grpc/experimento.py`. |

El programa debe:

1. Escribir `<prefijo>_latencias.csv` con las columnas `run_id,message_id,sender,receiver,payload_bytes,rtt_ms,mode` (`mode` = `sequential` o `concurrent`) y exactamente `--count` filas.
2. Escribir los eventos en `<prefijo>_eventos.csv` o en un archivo por nodo (`<prefijo>_eventos_nodo-A.csv`, etc.) con las columnas de `EVENT_FIELDS`. Deben quedar 4 eventos por envío.
3. Imprimir la línea `Duración: <segundos> s` con la duración de la tanda medida con `perf_counter()`, sin contar el arranque de los nodos ni la apertura de canales.
4. Terminar con código 0 solo si todos los envíos se completaron.

## 7. Análisis

`analysis/estadisticas.py` lee los manifiestos, descarta los calentamientos y las corridas fallidas y valida cada CSV contra el manifiesto: número de filas, tamaño, modo, `run_id` único, RTT positivos y 4 eventos por envío. Si algo no coincide, se detiene sin generar tablas.

Para cada mecanismo, tamaño y modo calcula:

- media, mediana, desviación estándar muestral (n − 1) y percentil 95 (interpolación lineal) de las 500 mediciones;
- intervalo de confianza del 95 % de la media, calculado con las medias de las 5 corridas (t de Student con 4 grados de libertad). La corrida es la unidad independiente: los 100 envíos de una corrida comparten proceso y conexión. Como todas las corridas tienen 100 envíos, la media de las medias coincide con la media global;
- rendimiento medio de las 5 corridas con su intervalo del 95 %.

También compara ambos mecanismos en cada carga y modo con la diferencia porcentual (gRPC − TCP) / TCP × 100 de la media, la mediana, el P95 y el rendimiento.

Salidas en `analysis/resultados/`:

| Archivo | Contenido |
| --- | --- |
| `estadisticas_por_corrida.csv` | una fila por corrida medida |
| `estadisticas_resumen.csv` | una fila por mecanismo, tamaño y modo |
| `comparacion_mecanismos.csv` | TCP y gRPC lado a lado con sus diferencias |
| `tabla_latencias.tex`, `tabla_rendimiento.tex`, `tabla_comparacion.tex` | tablas del informe |
| `grafico_cajas.png` | diagrama de cajas de los RTT (escala logarítmica) |
| `grafico_barras.png` | latencia media y rendimiento con intervalo del 95 % |

El informe incluye las tablas con `\input` y los gráficos con `\includegraphics`; no se copian a mano.

## 8. Factores que pueden distorsionar las mediciones

Se discuten en la sección de amenazas a la validez del informe (`docs/secciones/amenazas_validez.tex`):

- Los tres nodos y el orquestador corren en la misma máquina y comparten CPU; no hay red física.
- TCP ejecuta los tres nodos como hilos de un solo proceso. gRPC usa tres procesos. Esto cambia la planificación de la CPU y el efecto del GIL en la prueba concurrente.
- En gRPC la duración de la tanda incluye una llamada de control (`ControlNodo.Intercambiar`) por cada envío, por lo que su rendimiento queda subestimado frente a TCP. El RTT no se ve afectado.
- El primer envío de cada corrida suele ser más lento. Se conserva porque el protocolo solo descarta la corrida de calentamiento completa.
- Programas en segundo plano, antivirus y cambios de frecuencia del procesador.
- La resolución del reloj de pared limita el uso de `wall_time_utc` para ordenar eventos de distintos nodos.
