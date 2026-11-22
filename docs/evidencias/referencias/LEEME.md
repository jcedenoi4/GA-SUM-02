# Evidencia de las referencias de la parte de gRPC

Capturas de pantalla de cada artículo con el fragmento subrayado que respalda una
afirmación del apartado `docs/secciones/grpc.tex`. Todas las referencias están en
`docs/referencias.bib` con su DOI.

| Archivo | Referencia | Ubicación | Qué respalda |
|---|---|---|---|
| `lamport_1978_fragmento.png` | L. Lamport, «Time, clocks, and the ordering of events in a distributed system», *Commun. ACM*, 21(7):558-565, 1978. DOI 10.1145/359545.359563 | Página 1, resumen | Que el reloj lógico define un orden parcial entre los eventos |
| `rfc9113_fragmento.png` | M. Thomson y C. Benfield, «HTTP/2», RFC 9113, 2022. DOI 10.17487/RFC9113 | Página 1, *Abstract* | Que HTTP/2 reduce la latencia y permite varios intercambios concurrentes por conexión, que es el transporte de gRPC |
| `niswar_2024_fragmento.png` | M. Niswar et al., «Performance evaluation of microservices communication with REST, GraphQL, and gRPC», *IJET*, 70(2):429-436, 2024. DOI 10.24425/ijet.2024.149562 | Página 1, resumen | Que gRPC obtuvo el menor tiempo de respuesta frente a REST y GraphQL |
| `ain_2025_fragmento.png` | M. Z. Ain et al., «Comparative Performance Analysis of GRPC and REST API…», *JAIC*, 9(2):450-457, 2025. DOI 10.30871/jaic.v9i2.9276 | Página 1, resumen | Que las diferencias dependen del escenario y que su análisis no halló significancia estadística |
| `traini_2023_fragmento.png` | L. Traini et al., «Towards effective assessment of steady state performance in Java software: are we there yet?», *EMSE*, 28(1):13, 2023. DOI 10.1007/s10664-022-10247-x | Página 1, resumen | Que se descarte la fase de calentamiento y se mida en estado estable |

## Fragmentos subrayados, textuales

1. **Lamport:** «The concept of one event happening before another in a distributed
   system is examined, and is shown to define a partial ordering of the events.»
2. **RFC 9113:** «HTTP/2 enables a more efficient use of network resources and a
   reduced latency by introducing field compression and allowing multiple
   concurrent exchanges on the same connection.»
3. **Niswar:** «The experimental results indicate that gRPC has a faster response
   time, followed by REST and GraphQL.»
4. **Ain:** «REST API has higher throughput in low-traffic scenarios (995 vs. 29.5
   req/min) and faster GET response time (3 ms vs. 20 ms), while gRPC excels in
   large data transfers (276.34 KB/s vs. 134.1 KB/s) and stable latency (0.147 ms).
   However, ANOVA analysis (p > 0.05) indicates no statistically significant
   difference.»
5. **Traini:** «Due to Java Virtual Machine optimizations, microbenchmarks are
   usually subject to severe performance fluctuations in the first phase of their
   execution (also known as warmup). For this reason, software developers typically
   discard measurements of this phase and focus their analysis when benchmarks
   reach a steady state of performance.»

## Cómo comprobar cada referencia

Pegar `https://doi.org/<DOI>` en el navegador abre el registro editorial de la
obra. Los datos de la tabla coinciden con lo que devuelve
`https://api.crossref.org/works/<DOI>`.
