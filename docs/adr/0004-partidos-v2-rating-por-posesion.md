# Partidos v2: rating de equipo partido a partido, sin ajuste por ausencias

El modelo de partidos usa, por equipo, un rating de ataque, defensa y ritmo (en puntos por 100 posesiones) que se mueve una fracción K del error después de cada partido, como un Elo, y regresa hacia la media entre temporadas. Reemplazó al promedio de los últimos 10 partidos, que olvidaba demasiado rápido y daba márgenes comprimidos (desviación de 4.7 puntos contra 7.4 del mercado); el rating fue mejor en las 7 temporadas de validación y en vivo. K, K_RITMO y REGRESO se eligieron en 2015-2018, antes de ver 2019 en adelante.

## Considered Options

- Sumar encima el ajuste por ausencias de la v1: ayudaba un pelo en 2019-2025 (margen 10.94 → 10.92) pero empeoraba en vivo (11.52 → 11.70). No entra.
