# nba-player-forecasting

Pronósticos probabilísticos de las estadísticas de cada jugador y del resultado de cada partido de la NBA, publicados antes de que empiecen y medidos después contra lo que pasó.

## Temporadas

**Temporada**:
Una temporada de la NBA; en prosa se escribe con sus dos años ("2025-26"). El número suelto (2025) es solo la forma en que la nombra el código: el año en que empieza.
_Avoid_: "la temporada 2025" en texto

**Temporada de calibración**:
La temporada anterior a la que se pronostica; el modelo no la vio al entrenar y en ella se ajustan los intervalos y la dispersión.
_Avoid_: validación (para esta temporada)

## Jugadores

**Jugó**:
Un jugador jugó un partido si registró más de 0 minutos, aunque sea medio minuto al final.
_Avoid_: participó, DNP como sinónimo de "no jugó" sin más

**Media**:
El valor esperado de una estadística de un jugador; es lo que se suma para obtener el total de un equipo.
_Avoid_: pronóstico central, promedio (cuando se habla del pronóstico)

**Mediana**:
El valor entero que deja la mitad de la probabilidad a cada lado; el número que más se parece a "lo que va a hacer" en una noche típica.
_Avoid_: pronóstico central, q50 (fuera del código)

**Intervalo del 80%**:
El rango entre el percentil 10 y el 90 del pronóstico de un jugador-estadística; debe contener el valor real 8 de cada 10 veces.
_Avoid_: rango de confianza, intervalo de confianza

**Reconciliar**:
Ajustar los pronósticos de los jugadores de un equipo para que su suma sea coherente con los puntos esperados del equipo.
_Avoid_: normalizar, escalar

**Recalibración semanal**:
El ajuste del ancho del intervalo del 80% con los errores en vivo de los últimos 28 días.
_Avoid_: recalibración (a secas)

**Corrección del PIT**:
El ajuste de la forma de la distribución de cada estadística para que sus percentiles signifiquen lo que dicen; se hace una vez, en la temporada de calibración.
_Avoid_: recalibración (a secas), recalibración del PIT

## Partidos

**Marcador**:
Los puntos de cada equipo en un partido, reales o pronosticados.
_Avoid_: resultado (cuando se habla del puntaje)

**Rating**:
Los tres números que describen a un equipo en un momento dado: ataque, defensa (puntos por 100 posesiones contra el promedio de la liga) y ritmo.
_Avoid_: Elo, poder

## Modelos

**Versión**:
Un diseño del modelo de jugadores o de partidos (features, tipo de modelo), nombrado siempre con su modelo: "jugadores v3", "partidos v2". Un reentreno del mismo diseño es una subversión (v3.1, v3.2).
_Avoid_: "la v3" sin decir de qué modelo, modelo (para una versión)

**Diseño de features**:
El criterio con que se calculan los features de un jugador. "Por filas" (jugadores v1 a v3): las ventanas recorren filas del box score. "Jugados" (jugadores v4): las ventanas recorren partidos jugados y la ausencia se mide con el calendario del equipo.
_Avoid_: feature set, familia de features (las familias son los grupos del "por qué")

**Campeón**:
La versión activa del modelo de jugadores, la que se publica.
_Avoid_: modelo actual, producción

**Retador**:
El reentreno mensual del campeón con datos más recientes; solo se activa si tiene menos error que el campeón en las 2 semanas que ninguno vio.
_Avoid_: candidato, modelo nuevo

## Mercado

**Casa**:
Una casa de apuestas (DraftKings, FanDuel, etc.).
_Avoid_: book, sportsbook

**Línea**:
El número que una casa ofrece para un partido o jugador: spread, total o prop.
_Avoid_: momio (para el número)

**Momio**:
El precio de una apuesta sobre una línea (−110, +150).
_Avoid_: línea (para el precio), cuota

**Foto**:
La captura de las líneas de todas las casas en un momento dado: de la mañana, de la tarde o de cierre.
_Avoid_: snapshot, captura (como sustantivo suelto)

**Mercado**:
El consenso de las casas para un partido: la mediana de la última foto antes del salto, o la línea de DraftKings si no hay fotos.
_Avoid_: Vegas, las apuestas

**Mezcla**:
El pronóstico publicado de un partido como promedio ponderado del modelo y el mercado; los puntos de los jugadores se escalan para acompañarlo.
_Avoid_: ensamble, blend

**Salto**:
El inicio de un partido; la frontera después de la cual nada sobre ese partido puede pronosticarse ni publicarse.
_Avoid_: tip-off, inicio

## Evaluación

**Walk-forward**:
La forma de evaluar cualquier modelo: para pronosticar la temporada t se entrena con las 8 temporadas anteriores a t−1, se calibra en t−1 y se mide en t.
_Avoid_: validación cruzada, backtest (para el protocolo)

**Banco de pruebas**:
La medición estándar de cualquier cambio del modelo de jugadores, siempre en sus dos canchas y con las mismas métricas.
_Avoid_: benchmark, evaluación (a secas)

**Cancha**:
Una temporada de prueba del banco de pruebas: la histórica completa (2025-26) o la temporada en vivo hasta hoy.
_Avoid_: split, conjunto de prueba

**Backtest**:
Reproducir la corrida de un día pasado como si fuera en vivo, con solo la información de antes del salto.
_Avoid_: walk-forward, simulación

**Récord del modelo**:
Cómo le ha ido a lo publicado contra lo que realmente pasó, por día y estadística.
_Avoid_: marcador (en este sentido), scoreboard

## Operación

**Candado**:
La regla de publicación: una vez que empieza el primer partido de un día, el pronóstico publicado de ese día ya no se reescribe, y ningún partido que ya empezó recibe pronóstico.
_Avoid_: bloqueo, freeze

**Disponibilidad**:
Quién no va a jugar un partido y cómo se reparte lo que iba a producir; en vivo sale del reporte de lesiones de la mañana (Out o Doubtful).
_Avoid_: lesiones (como sinónimo), availability

**Vigía**:
El aviso automático que revisa cada hora si el pronóstico del próximo día con partidos ya se publicó y abre un issue si falta poco para el salto.
_Avoid_: monitor, alerta
