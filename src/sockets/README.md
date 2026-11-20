# Sockets TCP

Esta es mi implementación de sockets TCP para la práctica experimental de la Unidad 1.

**Jilmar Cedeño Intriago**

## Ejecución

En la interfaz local usamos los puertos TCP del enunciado. El nodo A escucha en `5000`, el nodo B en `5001` y el nodo C en `5002`.

Desde la raíz del repositorio, con Python 3.11 o superior y la biblioteca estándar:

```powershell
python src/sockets/client.py --output data/demo_tcp_100b
python src/sockets/client.py --size 10240 --output data/demo_tcp_10kib
python src/sockets/client.py --size 10240 --count 100 --concurrent --output data/demo_tcp_concurrente
```

Los comandos abren tres servidores en la interfaz local y guardan dos CSV por corrida. Para repetir una ejecución use otro prefijo, porque el programa protege los archivos originales. Para las corridas de 100 intercambios, añada `--count 100` y use un prefijo distinto para cada repetición y para el calentamiento. En modo concurrente, arrancamos hasta tres solicitudes por grupo. Con 100 intercambios ejecutamos 33 grupos de tres y un intercambio final. Para la captura propia, ejecute el primer comando en su terminal y capture la salida que muestra los tres puertos, los 20 intercambios y los archivos producidos.

## Formato de intercambio y CSV

- Mensaje de aplicación: `sender`, `timestamp`, `message`, `run_id`, `message_id`, `kind`. La solicitud y su respuesta comparten identificador y se distinguen con `request` y `response`.
- Eventos: `run_id,message_id,node,peer,event,clock,wall_time_utc,kind,payload_bytes`. Agrupar por `(run_id, message_id, kind)`, emparejar `send` con `receive` y verificar que la recepción tenga el reloj mayor. El CSV agrupa las filas por nodo.
- Latencias: `run_id,message_id,sender,receiver,payload_bytes,rtt_ms,mode`. Los modos son `sequential` y `concurrent`.
- Comparación: usar la misma carga de texto ASCII de 100 o 10 240 bytes (10 KiB), respuesta eco, conexiones persistentes, ruta circular y la misma topología de ejecución. El tamaño corresponde al campo `message` antes de serializar y excluye las cabeceras. Usar la misma política de calentamiento y medir desde el cliente.

## Pruebas locales del 19 de noviembre de 2026

Registré las pruebas realizadas en Windows con Python 3.14.6 y tráfico local en `127.0.0.1`. Los seis CSV originales están en `data/`.

| Corrida | Intercambios | Eventos | Mediana RTT (ms) | Intercambios/s |
| --- | ---: | ---: | ---: | ---: |
| 100 B, secuencial | 20 | 80 | 0,118300 | 5 212,95 |
| 10 KiB, secuencial | 20 | 80 | 0,317150 | 2 938,89 |
| 10 KiB, tres clientes concurrentes | 21 | 84 | 0,751600 | 2 425,03 |

En los 122 pares de envío y recepción registré un reloj de recepción estrictamente mayor que el de envío. Las medianas describen estas corridas locales. La comparación con gRPC requiere las mediciones equivalentes y las repeticiones del protocolo experimental común.

## Nota para la bitácora y la declaración de IA del equipo

- **19 de noviembre de 2026.** Mi aporte cubrió el cliente y el servidor TCP, el reloj de Lamport y la exportación de eventos y RTT. Para delimitar los mensajes, usé una cabecera de longitud y lecturas completas.
- **Declaración de uso de IA.** Utilicé ChatGPT Codex durante la preparación de mi aporte sobre sockets TCP y relojes de Lamport. Como parte de ese trabajo, usé la herramienta para ejecutar pruebas locales con mensajes de 100 B y 10 KiB y comprobar en los CSV que el reloj de cada recepción fuera mayor que el del envío correspondiente. Conservé los CSV originales para que el equipo pueda revisar los eventos y las latencias.

## Propuesta de objetivo e hipótesis para acordar con Angello

Nuestro objetivo es implementar y verificar la comunicación entre tres nodos mediante sockets TCP y gRPC, comprobar la causalidad de los mensajes mediante relojes lógicos de Lamport y comparar el tiempo de ida y vuelta y el rendimiento bajo condiciones equivalentes.

Como hipótesis para acordar con Angello, planteo que, con conexiones persistentes y cargas de 100 B, TCP directo podría mostrar una mediana de RTT menor debido al menor número de capas de aplicación. Con 10 KiB, la serialización y el procesamiento de cada implementación podrían modificar la diferencia. Contrastaremos la mediana y el percentil 95 de RTT, además del rendimiento en intercambios por segundo, con las repeticiones acordadas.

Para la aplicación al PFC, identificaremos sus componentes reales y justificaremos dónde usar TCP y dónde gRPC.

## Integración del informe

Desde el archivo principal en `docs/`, incluya el aporte con `\input{secciones/sockets_tcp}`.
Cargue la bibliografía en el preámbulo con `\usepackage[backend=biber,style=ieee]{biblatex}` y `\addbibresource{referencias.bib}`. Use `\printbibliography` donde corresponda.
Desde docs/, el orden es pdflatex → biber → pdflatex → pdflatex.
