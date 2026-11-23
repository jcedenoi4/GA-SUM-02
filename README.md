# GA-SUM-02

Comunicación entre procesos distribuidos con sockets TCP y gRPC.
Práctica experimental de la Unidad 1 (GA-SUM-01 / PE-U1), equipo CMSZ.

| Integrante | Usuario de GitHub |
|---|---|
| Jilmar Jesús Cedeño Intriago | [jcedenoi4](https://github.com/Amendozab5/GA-SUM-02/commits?author=jcedenoi4) |
| Angello Agustín Mendoza Bermello | [Amendozab5](https://github.com/Amendozab5/GA-SUM-02/commits?author=Amendozab5) |
| Darwin Joel Sánchez Vera | [DarwinDevCode](https://github.com/Amendozab5/GA-SUM-02/commits?author=DarwinDevCode) |
| Leonel Leonidas Zambrano Triviño | [lzambranot6-sys](https://github.com/Amendozab5/GA-SUM-02/commits?author=lzambranot6-sys) |

**Video de respaldo:** https://youtu.be/6JPvw8qsWWo

## Estructura

| Carpeta | Contenido |
|---|---|
| `src/sockets/` | Nodos con sockets TCP ([instrucciones](src/sockets/README.md)) |
| `src/grpc/` | Nodos con gRPC ([instrucciones](src/grpc/README.md)) |
| `proto/` | Contrato `lamport.proto` |
| `data/` | CSV crudos de todas las corridas y `SHA256SUMS` |
| `analysis/` | Protocolo, estadísticas, verificación de Lamport y gráficos ([protocolo](analysis/PROTOCOLO_EXPERIMENTAL.md)) |
| `docs/` | Informe LaTeX (`informe.tex`), bibliografía, PDF y evidencias |
| `BITACORA.md` | Sesiones de trabajo del equipo |

## Requisitos

Python 3.11 o superior. Las versiones exactas están en `requirements.txt`. En Windows se recomienda `cmd.exe`.

```
python -m pip install -r requirements.txt
```

## Ejecutar los nodos

Puertos: nodo-A 5000, nodo-B 5001, nodo-C 5002.

**Sockets TCP** (los tres nodos en un mismo proceso):
```
python src\sockets\client.py --output data\demo_tcp_100b
python src\sockets\client.py --size 10240 --count 100 --concurrent --output data\demo_tcp_concurrente
```

**gRPC** (un nodo por consola):
```
python src\grpc\server.py --node nodo-A --output data\demo_nodo-A.csv --verbose
python src\grpc\server.py --node nodo-B --output data\demo_nodo-B.csv --verbose
python src\grpc\server.py --node nodo-C --output data\demo_nodo-C.csv --verbose
python src\grpc\cliente.py --desde nodo-A --hasta nodo-B --count 5 --size 100
```

Más opciones en [src/sockets/README.md](src/sockets/README.md) y [src/grpc/README.md](src/grpc/README.md).

## Protocolo experimental y análisis

```
python analysis\entorno_experimento.py
python analysis\ejecutar_protocolo.py --mecanismos tcp grpc
python analysis\estadisticas.py
python analysis\verificar_lamport.py
python analysis\sha256sums.py --verificar
```

- `estadisticas.py` genera las tablas y gráficos de latencia y rendimiento en `analysis/resultados/`.
- `verificar_lamport.py` lee todos los CSV de eventos de `data/` (no los modifica), comprueba que en cada mensaje el reloj de recepción sea mayor que el de envío y busca eventos concurrentes con el mismo reloj. Deja `lamport_resumen.*`, `lamport_ejemplos.*`, `lamport_por_archivo.csv` y `lamport_pares.csv` en `analysis/resultados/`. Termina con código 0 si todo cumple.
- `sha256sums.py --verificar` comprueba que los CSV no cambiaron desde que se generaron.

## Evidencias

- `docs/evidencias/` reúne las capturas de ejecución de los cuatro integrantes.
- `docs/evidencias/demostracion_video/` contiene las capturas de la grabación del
  video de respaldo, con sus CSV en `data/demo_nodo-*.csv`.
- `docs/evidencias/referencias/` contiene el fragmento subrayado de cada
  referencia usada en el apartado de gRPC.

## Compilar el informe

- **Compilador:** `pdflatex` y `biber` (MiKTeX o TeX Live).
- **Archivo principal:** `docs/informe.tex`.
- **Dependencias LaTeX:** `babel` (spanish), `biblatex` (estilo ieee, backend biber), `lmodern`, `geometry`, `graphicx`, `amsmath`, `booktabs`, `tikz`, `listings`, `hyperref`.
- Las tablas y gráficos se incluyen desde `analysis/resultados/`. Ya están en el repositorio; para regenerarlos, ejecutar antes `estadisticas.py` y `verificar_lamport.py`.

Orden de comandos, desde la carpeta `docs/`:

```
cd docs
pdflatex informe
biber informe
pdflatex informe
pdflatex informe
```
