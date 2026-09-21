# Revisión histórica del entrenamiento (septiembre de 2026)

Este registro documenta experimentos locales; sus rutas `build/` no forman parte de la distribución. Para configurar un entrenamiento actual, consulta [la guía de aprendizaje](../learning.md).

## Diagnóstico comprobado

Experimento original: `build/ciclo-20260916-181434`.

- Las 108 derrotas fueron jaques mates; no hubo fallos de proceso contabilizados como derrotas.
- Las 1008 partidas generadas solo contenían 223 secuencias de juego diferentes.
- El filtrado dejó 1832 posiciones, con 1442 para entrenamiento.
- La red evaluaba todas las muestras entre −94 y +94 cp. En la posición inicial daba −16 cp;
  quitar la dama negra producía −19 cp y quitar la blanca −14 cp. No había aprendido el material.
- Los scores de búsqueda se asignaban al tablero posterior a la jugada, aunque UCI evalúa el anterior.
- El lanzador exigía 54 muestras independientes en una campaña que solo proporcionaba 18 aperturas.
- La prueba táctica rechazaba Kxe2 aunque tanto Kxe2 como Qxe2 ganan la dama en su posición de prueba.
- La puerta de velocidad solo comprobaba NPS y no detectaba la explosión del número de nodos.

## Cambios

1. Salida del entrenador en unidades útiles para optimizar, multiplicadas por 400 para obtener cp.
   La exportación incorpora ese factor y comprueba que no se recorten pesos.
2. Inicialización explícita con valores de material mediante dos neuronas ReLU. Los pesos son
   entrenables; no se ha añadido una evaluación HCE oculta al motor C++.
3. Elección de la mejor época de validación, incluida la inicial. Parada tras diez épocas sin mejora.
4. Etiquetas de búsqueda alineadas con el tablero anterior a la jugada, también para logs antiguos.
5. Muestreo distribuido por toda la partida y exclusión del prefijo forzado. La nueva configuración
   admite hasta 64 posiciones por partida y elimina el tope de 500 posiciones por bucket.
6. Variación reproducible de seis plies mediante alternativas próximas a la mejor jugada.
   Cada pareja comparte el prefijo y el motor recibe un inicio de partida nuevo.
7. Evaluación con otra semilla y prefijos elegidos por la referencia; umbral de 16 posiciones
   independientes. Intervalos conservadores que mantienen incertidumbre con resultados unánimes.
8. Benchmark limitado por nodos que exige profundidad completa y comprueba el tiempo además de NPS.
9. Popup con aceptación/rechazo explícito. Nuevos valores iniciales en el lanzador y configuración
   `data/training/learning-v2.json`.

## Pruebas realizadas

- Regresiones de material, escala, exportación, alineación de etiquetas e incertidumbre: correctas.
- Runner: aperturas variadas, parejas con el mismo prefijo y repetibilidad de la semilla: correcto.
- Generación del dataset, ajuste HCE y rechazo seguro: correcto.
- Ciclo completo reducido, con exploración y protección de la referencia activa: correcto.
- Inferencia de la red realmente entrenada: 63 posiciones con igualdad exacta entre Python y C++.
  Diferencia máxima frente a PyTorch sin cuantizar en esas posiciones: 4,367 cp.
- Ruff, comprobación del diff y compilación del lanzador: correctos.

El piloto `build/learning-v2-pilot` generó 1559 posiciones a partir de 108 partidas, con 54 prefijos
distintos. El entrenamiento corto no mejoró la validación y conservó la inicialización de material.
Su evaluación dio 0 victorias, 4 tablas y 32 derrotas; pasó reglas, táctica y rendimiento.

Reprocesando las partidas antiguas junto con el piloto se recuperaron 5846 posiciones.
El nuevo entrenamiento eligió la época 11 y paró en la 21: pérdida de validación 0,84322 → 0,82437.
En `build/learning-v2-reused-evaluation`, sobre 36 partidas con prefijos nuevos, obtuvo
0 victorias, 10 tablas y 26 derrotas. Pasó reglas, táctica, validación y rendimiento, pero fue rechazado
por fuerza. El tiempo total del benchmark fue aproximadamente 1,05 veces el de la referencia.
Las campañas usan posiciones distintas: estos resultados no cuantifican una ganancia de Elo.

Ninguna de estas pruebas promocionó una red. La referencia HCE sigue activa. La campaña nueva de
1008 partidas queda preparada para ejecutarse desde el lanzador; no se ha ejecutado en esta revisión.
La ubicación del lanzador se configura actualmente con `tools/build_launcher.ps1`; no depende de las carpetas de estos experimentos.
