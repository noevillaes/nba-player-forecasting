---
status: proposed
---

# La corrida diaria se queda en la laptop

La corrida diaria (`run_daily.py`) se ejecuta en una laptop con tareas programadas de Windows y no en GitHub Actions, porque stats.nba.com suele bloquear las IP de la nube (cdn.nba.com normalmente no). Como compensación, el vigía corre en Actions cada hora y abre un issue si el pronóstico del próximo día con partidos no está publicado poco antes del salto. Queda propuesto hasta ver el resultado del workflow `probar-fuentes`, que decide si la corrida puede mudarse a Actions.
