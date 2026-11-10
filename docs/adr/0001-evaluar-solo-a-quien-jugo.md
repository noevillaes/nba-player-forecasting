# Se evalúa solo a quien jugó; la disponibilidad queda fuera del modelo de jugadores

El modelo de jugadores pronostica qué hará cada jugador **si juega**, y sus métricas se calculan solo sobre jugador-partidos en los que jugó (más de 0 minutos). Predecir quién no va a jugar (lesiones, descansos) es otro problema: lo resuelve la disponibilidad, que decide a quién no se pronostica y reparte su producción entre los demás al reconciliar con el total del equipo. Mezclar ambos problemas en un solo número escondería qué parte del error viene de cada uno.
