# La corrida diaria se queda en la laptop

La corrida diaria (`run_daily.py`) se ejecuta en una laptop con tareas programadas de Windows y no en GitHub Actions, porque las dos fuentes de la NBA rechazan a los servidores de Actions: el 10 nov 2026 el workflow `probar-fuentes` encontró que stats.nba.com no responde (se agotan los 30 segundos de espera) y que cdn.nba.com devuelve 403; ESPN sí respondió. Como compensación, el vigía corre en Actions cada hora y abre un issue si el pronóstico del próximo día con partidos no está publicado poco antes del salto.

## Considered Options

- Mudar las descargas a cdn.nba.com y correr todo en Actions: descartado por el 403. La prueba pidió los JSON sin encabezados de navegador; aunque con ellos pasara, sería una conexión que la NBA puede cortar cualquier día.
