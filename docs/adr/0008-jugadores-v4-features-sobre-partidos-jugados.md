# Jugadores v4: los features se calculan sobre partidos jugados y el calendario del equipo

Hasta jugadores v3 las ventanas de features recorrían filas del box score (últimas 10 filas, días desde la fila anterior). El box score en vivo trae unas 1.4 filas más de "no jugó" por equipo-partido que el histórico de Kaggle (14.7 contra 13.3), así que el mismo jugador se veía distinto al entrenar que al pronosticar: un lesionado que regresa no tiene filas de 0 minutos en el histórico y sí las tiene en vivo. Desde jugadores v4 las mismas ideas se calculan sobre partidos jugados (`j_*`) y la ausencia se mide con el calendario del equipo (`cal_*`: partidos del equipo que se perdió, proporción de los últimos 10 que jugó), de modo que agregar o quitar filas de 0 minutos no cambia ningún feature. La tabla conserva las columnas del diseño anterior ("por filas") para que los paquetes v1 a v3 sigan funcionando.

## Considered Options

- Filtrar las filas de más en la descarga en vivo para que se parezca a Kaggle: no se sabe qué regla usa Kaggle para omitir filas, y la descarga en vivo no guarda el motivo de cada "no jugó".
- Agregar lo que el rating de partidos v2 espera del marcador (margen y total) como features: mejoraba un pelo los minutos en 2025-26 (4.773 → 4.767) y los empeoraba en vivo (4.693 → 4.698). No entra.
