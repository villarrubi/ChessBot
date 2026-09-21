# Estado y próximos pasos

Este documento distingue funcionalidades disponibles de mejoras pendientes. Las instrucciones de uso están en el [README](readme.md) y el [índice de documentación](docs/README.md).

## Disponible

- Reglas propias, FEN, jugadas legales, hacer/deshacer, Zobrist y pruebas PERFT.
- UCI asíncrono, límites de búsqueda, MultiPV, alternativas restringidas y paralelismo configurable.
- Evaluación manual explicable, perfiles de búsqueda y carga opcional de NNUE.
- Aplicación Windows con Jugar, Análisis, Entrenar y Herramientas.
- Análisis PGN/FEN/partida actual, navegación, informes, explicación básica y adaptador local de Ollama.
- Análisis en directo con prioridad por selección, resultados parciales, último movimiento resaltado, recorrido de variantes y gráfico de evaluación.
- Preguntas con una alternativa explícita SAN/UCI, calculada conservando historial, perspectiva y configuración de análisis.
- Partidas contra motores UCI, aperturas, autojuego, datasets, ajuste HCE y entrenamiento NNUE.
- Ciclo de generación, entrenamiento y evaluación con conservación de candidatos y promoción condicionada.
- CI de C++ y Python en Windows/Linux y compilación de la interfaz en Windows.

## Pendiente

- Demostrar mejoras de fuerza de los candidatos de búsqueda y aprendizaje en campañas amplias con controles comparables. Los primeros candidatos fueron rechazados.
- Ampliar las pruebas de calidad de las explicaciones locales. El texto generado no tiene garantía de corrección; los cálculos del motor son la referencia.
- Conversación con memoria entre preguntas y comparación simultánea de varias alternativas solicitadas. Hoy cada pregunta utiliza la posición seleccionada y una alternativa explícita opcional.
- Edición libre del tablero y creación de continuaciones propias durante el análisis.
- Distribución empaquetada que reduzca los pasos de instalación de herramientas de desarrollo.
- Integración de tablas de finales Syzygy y una prueba general de posiciones muertas.

## Criterio de aceptación

Los cambios deben aportar corrección, calidad del análisis, rendimiento o fuerza medible. Una menor pérdida de entrenamiento o un mayor NPS no demuestran por sí solos una mejora ajedrecística. Las mediciones publicadas deben identificar versión, recursos, control de tiempo, aperturas, tamaño de muestra e incertidumbre.
