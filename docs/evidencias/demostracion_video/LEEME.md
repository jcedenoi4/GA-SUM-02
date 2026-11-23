# Evidencia de la grabación del video de respaldo

Capturas tomadas durante la grabación del video, el **22 de noviembre de 2026 a
las 19:59** (hora local; los banners muestran `2026-11-23T00:59Z`). No forman
parte del informe: están aquí para que se pueda comprobar que la demostración del
video se ejecutó de verdad.

## Qué muestra cada captura

| Archivo | Qué se ve |
|---|---|
| `01_nodo_A_20_eventos.png` | El proceso de nodo-A escuchando en el puerto 5000 y su registro: cinco envíos a nodo-B (sellos 1, 5, 9, 13, 17) y cinco recepciones de nodo-C (sellos 39 a 55). Cierra con «20 eventos». |
| `02_nodo_B_20_eventos.png` | nodo-B en el puerto 5001: cinco recepciones de nodo-A y cinco envíos a nodo-C, que empiezan en el sello 20 porque su reloj ya había avanzado. Cierra con «20 eventos». |
| `03_nodo_C_20_eventos.png` | nodo-C en el puerto 5002: cinco recepciones de nodo-B y cinco envíos a nodo-A, desde el sello 39. Cierra con «20 eventos». |
| `04_cliente_tres_rondas.png` | Las tres rondas del cliente desde una sola consola: A→B, B→C y C→A, cada una con su resumen de media, mediana y P95. |

## Los datos de esa demostración

Los tres CSV están en `data/`, con 20 eventos cada uno y el mismo contenido que se
ve en las capturas:

- `data/demo_nodo-A.csv`
- `data/demo_nodo-B.csv`
- `data/demo_nodo-C.csv`

Cada intercambio deja cuatro eventos (envío y recepción de la solicitud, y envío y
recepción del acuse). Cada nodo participa en dos rutas: cinco intercambios como
emisor y cinco como receptor, de ahí los 20 eventos por nodo.

## La cadena de relojes

Lo que hay que mirar si se quiere comprobar la causalidad:

```
A → B   sello  1 → B recibe 2 → acuse  3 → A queda en  4
A → B   sello 17 → acuse 19                → A queda en 20
B → C   sello 20 (B continúa, no reinicia)
C → A   sello 39 (C continúa desde las recepciones de B)
```

Ningún nodo reinicia su contador entre rondas, que es lo que se quería demostrar.

## Integridad

Estos CSV están incluidos en `data/SHA256SUMS`. Se comprueban con:

```powershell
python analysis\sha256sums.py --verificar
```
