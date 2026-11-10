---
status: proposed
---

# Las ausencias de compañeros no entran como feature hasta poder medirlas con el reporte real

Reabre ADR-0005: con las ausencias definidas solo con partidos jugados y calendario (jugador de rotación = jugó 5+ de los últimos 10 partidos del equipo con 15+ minutos), saber quién falta sí mejora en vivo. Con información perfecta (quién no jugó, sabido después) los minutos bajan de 4.744 a 4.526 en 2025-26 y de 4.651 a 4.562 en vivo, y los puntos de 4.457 a 4.387 y de 4.415 a 4.389. Pero ese mismo modelo, servido solo con las ausencias seguras (las que continúan desde el partido anterior), queda peor en vivo que no usarlas (minutos 4.700 contra 4.651). El modelo solo es tan bueno como se parezca lo que ve al pronosticar a lo que vio al entrenar, y del histórico no hay reportes de lesiones: no se puede saber qué ausencias se conocían en la mañana.

Queda propuesto hasta tener unas 3 semanas de reportes guardados (`predictions/lesiones_<fecha>.csv`, desde el 8 nov 2026) para medir en vivo, con el reporte real, la variante que se entrena y se sirve solo con ausencias que continúan. Con información perfecta sobre ellas ayuda en 2025-26 (minutos 4.744 → 4.687) y empata en vivo (4.651 → 4.646), así que hoy no pasa la regla de mejorar en las dos canchas.

Los números salen de `python src/ausencias.py` (`results/banco_ausencias.csv`), sobre jugadores v4.

## Considered Options

- Solo "quién faltó al partido anterior del equipo", sin mirar hoy (no necesita reporte): no aporta sobre jugadores v4 (minutos 4.744 → 4.743 en 2025-26 y 4.651 → 4.659 en vivo); los minutos recientes del propio jugador ya lo traen.
- Un segundo pronóstico más cerca del salto, cuando el reporte ya está casi completo: es lo que acercaría lo servido a la información perfecta. El candado lo permite mientras no haya empezado el primer partido del día.
