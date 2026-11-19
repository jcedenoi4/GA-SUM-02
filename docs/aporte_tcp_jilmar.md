# Aporte de Jilmar Cedeño Intriago

**Equipo CMSZ · Práctica experimental de la Unidad 1 · 19 de noviembre de 2026**

## Ejecución

Desde la raíz del repositorio, con Python 3.11 o superior y la biblioteca estándar:

```powershell
python src/sockets/client.py --output data/demo_tcp_100b
python src/sockets/client.py --size 10240 --output data/demo_tcp_10kib
python src/sockets/client.py --size 10240 --count 21 --concurrent --output data/demo_tcp_concurrente
```

Los comandos abren tres servidores en la interfaz local y guardan dos CSV por corrida. Para repetir una ejecución use otro prefijo, porque el programa protege los archivos originales. Para las corridas de 100 intercambios, añada `--count 100` y use un prefijo distinto para cada repetición y para el calentamiento. En modo concurrente el conteo debe ser múltiplo de tres. Para la captura propia, ejecute el primer comando en su terminal y capture la salida que muestra los tres puertos, los 20 intercambios y los archivos producidos.

## Objetivo e hipótesis de trabajo

Implementar y verificar comunicación entre tres nodos mediante sockets TCP y gRPC, comprobar la causalidad de los mensajes mediante relojes lógicos de Lamport y comparar el tiempo de ida y vuelta y el rendimiento bajo condiciones equivalentes.

Como hipótesis de trabajo para acordar con Angello, con conexiones persistentes y cargas de 100 B, el protocolo TCP directo podría mostrar menor mediana de RTT debido al menor número de capas de aplicación. Con 10 KiB, la serialización y el procesamiento de cada implementación podrían modificar la diferencia. Se contrastará la mediana y el percentil 95 de RTT, además del rendimiento en intercambios por segundo, usando las repeticiones definidas por el equipo.

## Implementación TCP para el informe

TCP entrega un flujo de bytes fiable y ordenado [1]. En la práctica, cada mensaje se codifica como JSON UTF-8 y se antepone una cabecera de cuatro bytes con la longitud del cuerpo en orden de red. El emisor usa `sendall()` y el receptor lee en bucle hasta completar la cabecera y el cuerpo. Este encuadre permite recuperar mensajes cuando una lectura del socket devuelve solo parte del contenido y reutilizar una conexión para varios intercambios.

La corrida local inicia tres nodos lógicos con escuchas TCP independientes, `nodo-A:5101`, `nodo-B:5102` y `nodo-C:5103`. Los tres se alojan en un mismo proceso para la prueba en loopback. Las solicitudes se distribuyen en el ciclo A→B, B→C y C→A. El servidor devuelve la misma carga al cliente por la conexión persistente. En el modo concurrente, una barrera sincroniza el comienzo de cada grupo de tres solicitudes.

Cada nodo tiene un contador lógico inicializado en cero. Antes de enviar aplica `L = L + 1`. Al recibir un mensaje con sello `T`, aplica `L = max(L, T) + 1`. La actualización y la escritura del evento en memoria se hacen bajo el mismo bloqueo, de modo que el cliente y el servidor del nodo comparten una secuencia lógica. Cada intercambio completo deja cuatro eventos, correspondientes al envío y la recepción de la solicitud y de la respuesta. Los registros incluyen hora UTC con microsegundos, separada del reloj lógico.

El cliente mide el RTT con `time.perf_counter()` desde antes del envío hasta que se decodifica la respuesta completa. El intervalo incluye el procesamiento remoto y la serialización y decodificación que ocurren en el recorrido. El establecimiento de las conexiones y la escritura de los CSV quedan fuera de la ventana medida. El rendimiento usa el número de intercambios terminados dividido por el tiempo total de la tanda, medido con un solo reloj.

## Formato propuesto para integrar TCP y gRPC

- Mensaje de aplicación: `sender`, `timestamp`, `message`, `run_id`, `message_id`, `kind`. La solicitud y su respuesta comparten identificador y se distinguen con `request` y `response`.
- Eventos: `run_id,message_id,node,peer,event,clock,wall_time_utc,kind,payload_bytes`. Agrupar por `(run_id, message_id, kind)`, emparejar `send` con `receive` y verificar que la recepción tenga el reloj mayor. El CSV agrupa las filas por nodo.
- Latencias: `run_id,message_id,sender,receiver,payload_bytes,rtt_ms,mode`. Los modos son `sequential` y `concurrent`.
- Comparación: usar la misma carga de texto ASCII de 100 o 10 240 bytes (10 KiB), respuesta eco, conexiones persistentes, ruta circular y la misma topología de ejecución. El tamaño corresponde al campo `message` antes de serializar y excluye las cabeceras. Usar la misma política de calentamiento y medir desde el cliente.

## Resultados preliminares

Pruebas en Windows con Python 3.14.6 y tráfico local en `127.0.0.1`. Los seis CSV originales están en `data/`.

| Corrida | Intercambios | Eventos | Mediana RTT (ms) | Intercambios/s |
| --- | ---: | ---: | ---: | ---: |
| 100 B, secuencial | 20 | 80 | 0,118300 | 5 212,95 |
| 10 KiB, secuencial | 20 | 80 | 0,317150 | 2 938,89 |
| 10 KiB, tres clientes concurrentes | 21 | 84 | 0,751600 | 2 425,03 |

En los 122 pares de envío y recepción, el reloj de recepción fue estrictamente mayor que el de envío. Las medianas describen estas corridas locales. La comparación con gRPC requiere las mediciones equivalentes y las repeticiones del protocolo experimental común.

## Discusión técnica

Con sockets TCP, la biblioteca estándar permite controlar directamente el formato del mensaje y el flujo de lectura y escritura. Definir el encuadre, validar los campos, tratar respuestas incompletas y manejar los tiempos de espera son responsabilidades de la aplicación. JSON permite inspeccionar el contenido fácilmente y la implementación comprueba los tipos de los campos recibidos. gRPC usa HTTP/2 [2] y permite definir el contrato con Protocol Buffers, generar interfaces de cliente y servidor y comunicar errores mediante estados RPC [3]. El estudio de Niswar y colaboradores [3] ofrece un antecedente experimental en microservicios con una arquitectura distinta a la de esta práctica.

Para aplicar esta discusión al PFC, el equipo debe identificar una conexión concreta que requiera intercambiar tramas con un componente que ya exponga TCP y una llamada concreta entre servicios internos que se beneficie de un contrato tipado. Quedan por identificar esos componentes a partir de la arquitectura real del PFC.

## Bitácora y uso de IA

- **19 de noviembre de 2026.** Aporte asignado a Jilmar Cedeño Intriago. Se implementaron el cliente y el servidor TCP, el reloj de Lamport y la exportación de eventos y RTT. Se probaron las dos cargas y el modo concurrente. El problema de delimitar mensajes sobre el flujo TCP se resolvió con una cabecera de longitud y lecturas completas.
- **Declaración para revisar antes de integrar.** Se utilizó ChatGPT Codex para redactar el código y el apartado técnico, ejecutar pruebas locales y comprobar los CSV. Los valores presentados proceden de las corridas ejecutadas.

## Referencias propuestas para la bibliografía común

[1] W. Eddy, Ed., “Transmission Control Protocol (TCP),” RFC 9293, ago. 2022. [doi: 10.17487/RFC9293](https://doi.org/10.17487/RFC9293).

[2] M. Thomson y C. Benfield, Eds., “HTTP/2,” RFC 9113, jun. 2022. [doi: 10.17487/RFC9113](https://doi.org/10.17487/RFC9113).

[3] M. Niswar, R. A. Safruddin, A. Bustamin e I. Aswad, “Performance evaluation of microservices communication with REST, GraphQL, and gRPC,” *International Journal of Electronics and Telecommunications*, vol. 70, n.º 2, pp. 429–436, 2024. [doi: 10.24425/ijet.2024.149562](https://doi.org/10.24425/ijet.2024.149562).
