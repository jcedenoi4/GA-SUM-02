# Bitácora del equipo

**Actividad:** GA-SUM-02 / PE-U1 · Práctica experimental de la Unidad 1
**Equipo:** CMSZ · **Repositorio:** https://github.com/jcedenoi4/GA-SUM-02

Este registro recoge las sesiones de trabajo, lo realizado en cada una, los
problemas encontrados y cómo se resolvieron. Cada entrada se puede comprobar en
el historial de commits del repositorio.

| Fecha | Presentes | Trabajo principal |
|---|---|---|
| Mié 19 de noviembre | Jilmar Cedeño | Transporte TCP y relojes de Lamport |
| Jue 20 de noviembre | Jilmar Cedeño, Angello Mendoza | Puertos 5000-5002 y contrato de gRPC |
| Vie 20 de noviembre (noche) | Darwin Sánchez | Protocolo experimental y análisis |
| Sáb 21 de noviembre | Los cuatro integrantes | Datos del protocolo, verificación y figuras |
| Dom 22 de noviembre | Angello Mendoza y el equipo | Integración del informe y entrega |

---

## Miércoles 19 de noviembre de 2026

**Presentes:** Jilmar Cedeño (trabajo individual).

**Realizado.** Servidor y cliente TCP con mensajes JSON, encuadre por cabecera de
longitud y conexiones persistentes. Reloj lógico de Lamport en los tres nodos, con
registro de los cuatro eventos de cada intercambio y exportación a CSV. Mediciones
de RTT con `time.perf_counter()` y corridas de 20 intercambios en 100 B y 10 KiB.
Commits `7f0c6ac` y `1c0b752`.

**Problemas y solución.** Un flujo TCP no conserva los límites de los mensajes, así
que una lectura puede devolver el mensaje incompleto o dos mensajes juntos. Se
resolvió anteponiendo una cabecera de cuatro bytes con la longitud del cuerpo y
leyendo en bucle hasta completarla.

---

## Jueves 20 de noviembre de 2026

**Presentes:** Jilmar Cedeño y Angello Mendoza (trabajo individual de cada uno).

**Realizado por Jilmar.** Ajuste de los puertos TCP a `5000`, `5001` y `5002`, como
pide el enunciado, y habilitación de tandas de 100 intercambios en modo concurrente.
Integración de su aporte en el informe. Commits `647e63d` y `8b1eb9e`.

**Realizado por Angello.** Contrato en `proto/lamport.proto`, generación de los
stubs con `grpcio-tools`, nodo gRPC con reloj de Lamport, cliente de intercambios y
campaña de medición. Commits `aa91b2f`, `6a515d8` y `ec32f49`.

**Problemas y solución.**

- El `push` de Angello fue rechazado porque el repositorio ya tenía commits nuevos.
  Se resolvió con `git pull --rebase` antes de publicar.
- Los nodos de gRPC escribían su CSV en la carpeta temporal del sistema y la corrida
  fallaba. Se cambió a una carpeta de trabajo junto a los datos (`data/_nodos/`),
  que queda excluida del control de versiones.
- El primer diseño de gRPC dejaba dos relojes por nodo: uno al enviar y otro al
  recibir. Se corrigió con un canal de control, de modo que el nodo que origina el
  mensaje es el mismo proceso que lo registra y cada nodo tiene un solo reloj.

---

## Viernes 20 de noviembre de 2026 (noche)

**Presentes:** Darwin Sánchez (trabajo individual).

**Realizado.** Protocolo experimental común para los dos mecanismos, con una corrida
de calentamiento por combinación y cinco repeticiones en orden rotado. Registro de
las condiciones de la máquina y cálculo de media, mediana, desviación, percentil 95,
rendimiento e intervalo de confianza, con las tablas en LaTeX generadas por el
script. Commits `8e9ebf4`, `a961ac4` y `bfe59f7`.

**Problemas y solución.** El protocolo esperaba un programa `src/grpc/lanzador.py` y
una línea de salida con la duración de la tanda. Ninguno de los dos existía en la
parte de gRPC; se resolvió al día siguiente adaptando el lanzador.

---

## Sábado 21 de noviembre de 2026

**Presentes:** los cuatro integrantes.

**Realizado por Leonel.** Verificador de Lamport sobre los CSV reales, con la
reconstrucción de la relación «ocurrió antes», el conteo de pares que cumplen y la
búsqueda de eventos concurrentes con el mismo valor de reloj. Commits `641c678` y
`22e745f`.

**Realizado por Angello.** Adaptación del lanzador al protocolo común (`lanzador.py`,
corrección de la concurrencia y línea «Duración»), publicación de los 20
intercambios de gRPC con sus latencias, ejecución de la sesión del protocolo común
(48 corridas) y generación de los resultados. Commits `c479fe3`, `8b26104`,
`8776e99` y `02ecaa9`.

**Realizado por Jilmar.** Capturas de las pruebas TCP y de la verificación de
Lamport. Commit `b70d393`.

**Realizado por Darwin.** `SHA256SUMS` de los CSV originales, boxplot y gráfico de
barras con intervalos, tabla de comparación entre mecanismos y redacción de las
secciones de protocolo, resultados y amenazas a la validez. Commits `a6369f4`,
`e9ba494` y `414f79a`.

**Problemas y solución.**

- El lanzador de gRPC exigía un número de envíos múltiplo de tres en modo
  concurrente, pero el protocolo usa 100. Se corrigió para procesar el último lote
  con las rutas que queden, y se añadió la línea `Duración: <s> s` que el script de
  análisis necesita leer.
- Se había corrido una campaña piloto de 16 tandas antes de que existiera el
  protocolo común. Se descartó para no tener dos juegos de datos: sus archivos se
  guardaron fuera del repositorio y la sesión se repitió con las 48 corridas del
  protocolo.
- Una de las corridas de gRPC con 10 KiB resultó anómala (mediana 1,01 ms frente a
  0,65 ms de las demás). Se conservó tal cual, porque los datos no se editan; el
  boxplot la muestra como valor atípico.

---

## Domingo 22 de noviembre de 2026

**Presentes:** Angello Mendoza y el resto del equipo.

**Realizado por Angello.** Redacción del apartado de gRPC del informe, con el
contrato, la generación del código, el reloj de Lamport, la ventana de medición y la
comparación de desarrollo, tipado y manejo de errores. Incorporación de la quinta
referencia con DOI verificado y compilación del PDF. Commit `e234287`.

**Problemas y solución.**

- El informe no compilaba: faltaba `graphicx` para las figuras y PDFLaTeX fallaba al
  buscar las fuentes EC (`Font ecrm1000 not found`). Se añadió `lmodern`, que usa
  fuentes Type1 y viene en cualquier distribución de LaTeX.
- La sección «Resultados preliminares de TCP» tenía una tabla escrita a mano con
  números fijos. Se eliminó, porque el enunciado exige que las tablas salgan del
  script de análisis y esa información ya está en la sección de resultados.

---

## Decisiones del equipo

- Los dos mecanismos usan los mismos puertos (`5000`, `5001`, `5002`), como pide el
  enunciado. Por eso no se ejecutan al mismo tiempo: primero un mecanismo y después
  el otro.
- Los dos mecanismos escriben CSV con las mismas columnas, para que un solo script
  analice ambos.
- El protocolo experimental es común: calentamiento descartado, cinco repeticiones,
  dos tamaños y dos modos.
- Se declara como amenaza a la validez que TCP ejecuta los tres nodos como hilos de
  un mismo proceso y gRPC como tres procesos independientes.

## Declaración de uso de inteligencia artificial

Cada integrante declara su uso en el apartado correspondiente del informe. En el
repositorio consta lo siguiente: Jilmar Cedeño documentó el uso de ChatGPT Codex en
`src/sockets/README.md`; Angello Mendoza documentó el uso de DeepSeek Harness en
`src/grpc/README.md`. En todos los casos la herramienta se usó como apoyo para
estructurar el código y redactar documentación, y cada integrante ejecutó, revisó y
verificó su parte.
