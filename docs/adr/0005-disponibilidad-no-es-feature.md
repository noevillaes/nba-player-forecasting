# La disponibilidad no entra como feature del modelo de jugadores

Se probó (8 nov 2026) darle al modelo de jugadores, como features, quién falta en su equipo. Ayudaba en 2025-26 (minutos 4.77 → 4.69) pero no en la temporada en vivo (4.738 → 4.739) con ninguna definición de ausencia, porque en vivo la plantilla trae filas de 0 minutos para los lesionados que el box score histórico casi nunca tiene: lo que el modelo aprende del histórico no se parece a lo que ve en vivo. La disponibilidad se usa fuera del modelo: no pronosticar a los ausentes y repartir su producción al reconciliar.
