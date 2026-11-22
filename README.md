# GA-SUM-02 · Comunicación entre procesos distribuidos con sockets TCP y gRPC

Práctica experimental de la Unidad 1 (**GA-SUM-01 / PE-U1**). Tres nodos en
localhost que se comunican por sockets TCP y por gRPC, con relojes lógicos de
Lamport, medición de latencia y comparación de los dos mecanismos.

**Equipo CMSZ**
Jilmar Jesús Cedeño Intriago · Angello Agustín Mendoza Bermello ·
Darwin Joel Sánchez Vera · Leonel Leonidas Zambrano Triviño

Repositorio: https://github.com/jcedenoi4/GA-SUM-02

## Contenido del repositorio

| Ruta | Qué hay |
|---|---|
| `src/sockets/` | Servidor y cliente TCP, reloj de Lamport y registro de eventos |
| `src/grpc/` | Contrato generado, nodo gRPC, cliente, lanzador y campaña |
| `proto/` | Contrato en Protocol Buffers |
| `data/` | CSV crudos de las corridas y `SHA256SUMS` |
| `analysis/` | Protocolo experimental, estadísticas, verificador de Lamport y resultados |
| `docs/` | Informe en LaTeX, bibliografía, PDF compilado y capturas |
| `requirements.txt` | Versiones exactas de las dependencias |
| `BITACORA.md` | Sesiones de trabajo, problemas y soluciones |

## Requisitos

- Python 3.11 o superior (las mediciones se hicieron con 3.14.8 en Windows).
- Dependencias: `python -m pip install -r requirements.txt`
- Para compilar el informe: una distribución de LaTeX con `biber`.

## Cómo ejecutar

Los dos mecanismos usan los mismos puertos (`nodo-A:5000`, `nodo-B:5001` y
`nodo-C:5002`), así que **no se ejecutan al mismo tiempo**: primero uno y después
el otro. Todos los comandos se ejecutan desde la raíz del repositorio.

### 1. Sockets TCP

Tres nodos en tres consolas:

```
python src\sockets\server.py nodo-A --output data\demo_tcp_nodo-A.csv
python src\sockets\server.py nodo-B --output data\demo_tcp_nodo-B.csv
python src\sockets\server.py nodo-C --output data\demo_tcp_nodo-C.csv
```

Una corrida completa, que levanta los tres nodos y mide:

```
python src\sockets\client.py --count 20 --size 100 --output data\demo_tcp_20
python src\sockets\client.py --count 100 --size 10240 --concurrent --output data\demo_tcp_conc
```

### 2. gRPC

Tres nodos en tres consolas (`--verbose` muestra cada intercambio):

```
python src\grpc\server.py --node nodo-A --output data\demo_grpc_nodo-A.csv --verbose
python src\grpc\server.py --node nodo-B --output data\demo_grpc_nodo-B.csv --verbose
python src\grpc\server.py --node nodo-C --output data\demo_grpc_nodo-C.csv --verbose
```

Con los nodos en marcha, otra terminal ordena envíos y muestra el RTT:

```
python src\grpc\cliente.py --desde nodo-A --hasta nodo-B --count 5 --size 100
```

Una corrida completa, que levanta sus propios nodos:

```
python src\grpc\lanzador.py --count 100 --size 10240 --output data\prueba_grpc
```

Si se modifica el contrato, el código se regenera con:

```
python src\grpc\generar_stubs.py
```

### 3. Protocolo experimental y análisis

```
python analysis\ejecutar_protocolo.py --mecanismos tcp grpc
python analysis\estadisticas.py
```

El primero crea `data/protocolo/sesion_<fecha>/` con las condiciones de la máquina,
el manifiesto y los CSV de las 48 corridas (calentamiento y cinco repeticiones por
combinación). El segundo descarta los calentamientos y escribe en
`analysis/resultados/` las estadísticas, las tablas LaTeX y los dos gráficos.

### 4. Verificación de Lamport y hashes

```
python analysis\verificar_lamport.py
python analysis\sha256sums.py
python analysis\sha256sums.py --verificar
```

El verificador comprueba sobre los CSV reales que el reloj de cada recepción sea
mayor que el del envío y busca eventos concurrentes con el mismo valor. El segundo
comando regenera `data/SHA256SUMS` y `--verificar` comprueba que los archivos no
hayan cambiado.

## Datos y evidencias

- `data/` contiene los CSV de los 20 intercambios de cada mecanismo, los de la
  demostración de los tres nodos y la sesión completa del protocolo.
- `data/SHA256SUMS` permite comprobar que los CSV no se modificaron.
- `docs/evidencias/` reúne las capturas de ejecución de los cuatro integrantes.

## Informe

El documento principal es `docs/informe.tex` y el PDF compilado está en
`docs/informe.pdf`. Se compila desde la carpeta `docs/`, en este orden:

```
cd docs
pdflatex informe.tex
biber informe
pdflatex informe.tex
pdflatex informe.tex
```

Dependencias de LaTeX: `biblatex` con backend `biber` y estilo IEEE, `babel` con
opción `spanish`, `geometry`, `graphicx`, `fontenc` y `lmodern` (fuentes Type1).

## Video de respaldo

Enlace: **PENDIENTE** — reemplazar por la dirección del video antes de la entrega.

## Uso de inteligencia artificial

Cada integrante declara su uso en el apartado correspondiente del informe. En este
repositorio consta el detalle en `src/sockets/README.md` (Jilmar Cedeño) y en
`src/grpc/README.md` (Angello Mendoza). La herramienta se usó como apoyo para
estructurar el código y redactar documentación; cada integrante ejecutó, revisó y
verificó su parte.
