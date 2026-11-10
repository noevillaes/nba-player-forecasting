# Protocolo walk-forward: 8 temporadas de entrenamiento, calibración en t−1

Para pronosticar la temporada t, todo modelo se entrena con las 8 temporadas anteriores a t−1, se calibra en t−1 (que el modelo no vio) y se mide en t. Es el mismo protocolo con el que se entrena el modelo publicado al inicio de cada temporada, así que lo que se mide en el banco de pruebas es lo que se va a publicar. Se descartó la validación cruzada aleatoria porque mezcla futuro y pasado y sobreestima la precisión en una serie que cambia con el tiempo.
