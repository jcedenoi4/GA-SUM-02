# gRPC con Protocol Buffers

Implementación de la comunicación entre los tres nodos mediante gRPC, con reloj
lógico de Lamport y el mismo protocolo de medición que el transporte TCP.

**Angello Agustín Mendoza Bermello**

## Requisitos

Python 3.11 o superior y las dependencias de la raíz del repositorio:

```powershell
python -m pip install -r requirements.txt
```

El contrato está en `proto/lamport.proto` y el código generado
(`src/grpc/lamport_pb2.py` y `src/grpc/lamport_pb2_grpc.py`) se conserva en el
repositorio. Si se modifica el contrato, se regenera con:

```powershell
python src/grpc/generar_stubs.py
```

## Tres nodos en tres consolas

Abre tres terminales en la raíz del repositorio y ejecuta una en cada una. Cada
nodo muestra su banner con fecha UTC, equipo, usuario y versión de Python, y
escribe su CSV al detenerse con `Ctrl+C`.

```powershell
python src/grpc/server.py --node nodo-A --output data/demo_nodo-A.csv --verbose
python src/grpc/server.py --node nodo-B --output data/demo_nodo-B.csv --verbose
python src/grpc/server.py --node nodo-C --output data/demo_nodo-C.csv --verbose
```

Puertos: `nodo-A:5000`, `nodo-B:5001` y `nodo-C:5002`, como pide el enunciado.
`--verbose` imprime cada intercambio; conviene usarlo en la demostración y no en
las mediciones, para no sumar escritura en consola al tiempo medido.

## Un intercambio contra nodos que ya están en marcha

Con los tres nodos levantados, otra terminal puede ordenar envíos y ver el RTT:

```powershell
python src/grpc/cliente.py --desde nodo-A --hasta nodo-B --count 5 --size 100
```

Cambiar `--size` permite repetir la medición con otra carga en el momento, por
ejemplo `--size 5000`. Este comando no escribe CSV: los eventos quedan en los
nodos y se guardan cuando cada uno se detiene con `Ctrl+C`.

## Una corrida

```powershell
python src/grpc/experimento.py --count 20  --size 100   --output data/grpc_20_100b
python src/grpc/experimento.py --count 20  --size 10240 --output data/grpc_20_10kib
python src/grpc/experimento.py --count 100 --size 100   --output data/grpc_100_100b_r1
python src/grpc/experimento.py --count 102 --size 10240 --concurrent --output data/grpc_concurrente_10kib_r1
```

El lanzador levanta los tres procesos, espera a que los canales estén
establecidos, ordena los envíos, detiene los nodos y reúne los registros. No
sobrescribe archivos: para repetir una corrida hay que usar otro prefijo.

## Campaña completa

```powershell
python src/grpc/campana.py
```

Ejecuta, en orden, un calentamiento por tamaño, cinco repeticiones de 100 envíos
por tamaño, los 20 intercambios para verificar Lamport y dos corridas
concurrentes. Deja los CSV en `data/` y el manifiesto en
`data/runs_manifest.csv`, con las condiciones de la máquina de cada corrida.

## Formato de los CSV

Idéntico al del transporte TCP, para que un mismo script analice ambos
mecanismos.

- Eventos: `run_id,message_id,node,peer,event,clock,wall_time_utc,kind,payload_bytes`.
  Cada intercambio produce cuatro eventos: envío y recepción de la solicitud y
  del acuse. Las filas se agrupan por nodo.
- Latencias: `run_id,message_id,sender,receiver,payload_bytes,rtt_ms,mode`. Los
  modos son `sequential` y `concurrent`.
- Nombres: `grpc_<envíos>_<tamaño>_r<repetición>_{eventos,latencias}.csv`, por
  ejemplo `grpc_100_10kib_r3_latencias.csv`.

## Reloj de Lamport

Cada nodo tiene un solo reloj, aunque también origine envíos: el nodo aplica
`L = L + 1` antes de enviar y `L = max(L, T) + 1` al recibir, con `T` el sello del
mensaje recibido. Como el nodo que origina el envío es el mismo proceso que lo
registra, la secuencia de relojes de cada nodo es monótona y verificable.

## Dos servicios en el mismo puerto

- `NodoLamport.EnviarMensaje` es el servicio del enunciado y es la única llamada
  que se cronometra.
- `ControlNodo.Preparar` e `ControlNodo.Intercambiar` son el canal de control:
  ordenan los envíos y devuelven el RTT medido dentro del nodo emisor. No forman
  parte del intercambio medido.

El RTT se toma con `time.perf_counter()` desde antes de sellar el envío hasta que
regresa el acuse, de modo que incluye serialización, transporte HTTP/2 y
decodificación, igual que el cliente TCP mide desde antes de `sendall()`.

## Manejo de errores

El nodo valida el emisor, el tipo de mensaje y los campos obligatorios, y
responde con un código de estado de gRPC (`INVALID_ARGUMENT`) en lugar de fallar
en silencio. El cliente comprueba que el acuse corresponda a la solicitud y
lanza un error si no coincide.

## Diferencia con el transporte TCP de este repositorio

En TCP los tres nodos se levantan como hilos dentro de un mismo proceso; aquí son
tres procesos independientes, como pide el enunciado. Esa diferencia se discute
en el informe como amenaza a la validez de la comparación.

## Nota para la bitácora y la declaración de IA

- **20 de noviembre de 2026.** Definí el contrato Protobuf, generé los stubs con
  grpcio-tools, implementé el nodo gRPC con reloj de Lamport, el canal de control,
  el lanzador de corridas y la campaña de medición.
- **Declaración de uso de IA.** Usé un asistente de inteligencia artificial
  (DeepSeek Harness) como apoyo para estructurar el contrato, revisar el código y
  redactar esta documentación. Ejecuté y verifiqué cada corrida en mi equipo, y
  conservé los CSV originales para que el equipo pueda auditarlos.
