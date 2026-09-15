# Roadmap de ChessBot

Ruta de trabajo basada en [specs.md](specs.md). Las funcionalidades de las fases 0–7 y el pipeline de fase 8 están implementados y verificados localmente. La fase 7 está cerrada; las promociones estadísticas de los candidatos de búsqueda (fase 5) y evaluación manual (fase 8) siguen abiertas porque las campañas no demostraron más fuerza. Las fases 9–10 no se han iniciado.

El orden prioriza reglas correctas, búsqueda fiable, rendimiento medido, evaluación explicable y, finalmente, aprendizaje. No se fijan fechas hasta disponer de una primera medida de esfuerzo y rendimiento.

## Fase 0 — Preparar el proyecto

- [x] Crear el proyecto C++20 con CMake y un ejecutable de consola llamado `chessbot`.
- [x] Crear la estructura `src/`, `tests/`, `tools/`, `data/` y `docs/` propuesta en la especificación.
- [x] Configurar un framework de pruebas, compilaciones Debug/Release, avisos del compilador y sanitizadores donde estén disponibles.
- [x] Preparar el entorno Python 3.12+ y declarar dependencias separando herramientas básicas y entrenamiento neuronal.
- [x] Definir tipos de piezas, colores, casillas, movimientos y puntuaciones; fijar `a1 = 0` y `h8 = 63`.
- [x] Documentar centipeones, perspectiva del bando al turno, puntuaciones de mate y conversiones para informes.
- [x] Configurar CI con compilación, pruebas y formato; incorporar PERFT y benchmarks cuando existan.
- [x] Crear documentación de arquitectura y convenciones, y registrar las decisiones que concreten alternativas de `specs.md`.
- [x] **Cierre:** el ejecutable compila y arranca, y las pruebas pasan localmente y en CI (Windows/Linux, Debug/Release y sanitizadores).

## Fase 1 — Implementar las reglas del ajedrez

- [x] Representar el tablero con bitboards de 64 bits, ocupación por color y estado completo de la posición.
- [x] Implementar lectura y escritura de los seis campos FEN, con validación y errores claros.
- [x] Codificar movimientos normales, capturas, promociones, doble avance, en passant y ambos enroques.
- [x] Precalcular ataques de peones, caballos y reyes; comenzar las piezas deslizantes con recorrido de rayos.
- [x] Generar movimientos pseudolegales y filtrarlos por legalidad, incluidos clavadas, jaques dobles y jaques descubiertos.
- [x] Implementar `makeMove`/`unmakeMove` con restauración exacta de piezas, turno, relojes, enroques y en passant.
- [x] Añadir Zobrist incremental y contrastarlo con el hash recalculado; definir qué estado de en passant afecta a la repetición.
- [x] Detectar jaque, mate, ahogado, triple repetición, regla de cincuenta movimientos y material insuficiente.
- [x] Documentar y probar el tratamiento de tablas reclamables y del historial anterior a la posición de búsqueda.
- [x] Añadir invariantes del tablero y pruebas aleatorias de secuencias de hacer/deshacer movimientos.
- [x] Implementar PERFT y su desglose por movimiento para localizar errores.
- [x] Validar posición inicial hasta profundidad 6: `20`, `400`, `8.902`, `197.281`, `4.865.609` y `119.060.324` nodos.
- [x] Añadir posiciones PERFT específicas para enroques, promociones, en passant y restricciones por jaque; contrastar legalidad con `python-chess` desde las herramientas.
- [x] **Cierre:** toda la suite PERFT pasa y hacer/deshacer restaura exactamente la posición. No comenzar la búsqueda antes de cerrar esta fase.

Evidencia de las fases 0/1: [resultados de validación](docs/validation.md), [guía de desarrollo](docs/development.md) y [contratos de arquitectura](docs/architecture.md). ASan/UBSan está verificado en Linux mediante CI; la máquina local no dispone del runtime ASan de MSVC.

## Fase 2 — Conseguir el primer motor jugable

- [x] Implementar evaluación de material y tablas sencillas de pieza-casilla (PST).
- [x] Implementar negamax con poda alfa-beta y profundidad fija.
- [x] Resolver terminales antes de evaluar; representar la distancia al mate y evitar desbordamientos de puntuación.
- [x] Reconstruir la variante principal (PV) y registrar profundidad, nodos, puntuación y mejor movimiento.
- [x] Definir la API `Engine`, `SearchLimits`, `SearchResult`, evaluación detallada y parada.
- [x] Crear pruebas tácticas de mates cortos, recapturas, pérdidas de dama y tablas.
- [x] Ejecutar partidas completas con una herramienta básica de validación de movimientos.
- [x] **Cierre:** el motor termina partidas legales y devuelve resultados coherentes en la suite táctica inicial.

## Fase 3 — Completar el MVP con UCI

- [x] Añadir profundización iterativa y conservar el resultado de la última iteración completada.
- [x] Implementar una tabla de transposición de tamaño configurable, cotas, reemplazo y ajuste de puntuaciones de mate al guardar/recuperar.
- [x] Ordenar movimientos con el movimiento de la tabla, capturas MVV-LVA y promociones.
- [x] Añadir búsqueda de quietud con capturas, promociones y todas las evasiones legales cuando haya jaque; no usar evaluación de reposo en jaque.
- [x] Admitir límites por profundidad, nodos, tiempo por movimiento, relojes, incremento, movimientos restantes y análisis infinito.
- [x] Implementar parada atómica, margen de tiempo y respuesta útil al interrumpir una búsqueda.
- [x] Implementar `uci`, `isready`, `ucinewgame`, `position`, `go`, `stop`, `quit` y `setoption`.
- [x] Publicar `info` con puntuación, profundidad, nodos, NPS, tiempo y PV; separar logs de la salida del protocolo.
- [x] Exponer las opciones ya implementadas y rechazar entradas inválidas sin bloquear ni cerrar inesperadamente el proceso.
- [x] Establecer la base inicial: un hilo, 64 MB de hash, evaluación manual, libro y NNUE desactivados, y límite de 128 plies.
- [x] Crear el benchmark de posiciones fijas y registrar una versión de referencia reproducible.
- [x] Adelantar un comparador UCI mínimo entre versiones con partidas emparejadas, colores invertidos, aperturas iguales y control de tiempo fijo. Se ampliará en la fase 7.
- [x] **Cierre / MVP:** el motor funciona desde una GUI UCI, juega partidas completas y respeta límites y órdenes de parada; reglas, búsqueda y protocolo pasan sus pruebas.

## Fase 4 — Evaluación posicional explicable

- [x] Separar términos de medio juego y final e interpolar según la fase de la partida.
- [x] Ampliar PST, movilidad y estructura de peones: doblados, aislados, retrasados, islas, conectados y candidatos a pasados.
- [x] Valorar peones pasados según avance, apoyo, bloqueo, distancia de reyes y posición de las torres.
- [x] Añadir seguridad del rey, pareja de alfiles, actividad de torres, espacio y tempo.
- [x] Incorporar gradualmente puestos avanzados, piezas atrapadas, amenazas y actividad del rey en finales cuando aporten mejoras medibles.
- [x] Exponer `EvalBreakdown` con contribuciones y total consistentes, sin doble contabilización de términos.
- [x] Mostrar por separado evaluación estática y evaluación de búsqueda, indicando siempre su perspectiva.
- [x] Probar simetría, signo, interpolación y suma de componentes; medir coste y fuerza frente a la referencia.
- [x] **Cierre:** el desglose reproduce la evaluación manual y la mejora posicional se valida mediante pruebas e informes de partidas.

Evidencia de las fases 2–4: [búsqueda](docs/search.md), [evaluación](docs/evaluation.md) y [resultados de validación](docs/validation.md). La comparación inicial `Positional`–`Basic` fue 13–3 a profundidad 3; aún no es una estimación Elo.

## Fase 5 — Optimizar búsqueda y rendimiento

- [x] Medir perfiles de ejecución antes de elegir qué optimizar y mantener una referencia por cambio mediante `SearchProfile=Baseline`.
- [x] Incorporar killers e historial, ventanas de aspiración, null-move y reducciones de movimientos tardíos (LMR), en cambios independientes.
- [x] Proteger null-move frente a jaques y finales propensos a zugzwang; verificar las condiciones de reducción y rebúsqueda de LMR.
- [x] Evaluar poda de futilidad, razoring, extensiones de jaque y singulares, SEE y reducciones iterativas internas. Se retiraron del perfil final las variantes sin evidencia favorable.
- [x] Sustituir ataques por rayos por tablas indexadas con PEXT/BMI2 cuando está disponible y compresión compatible por software en el resto.
- [x] Reducir asignaciones mediante listas fijas en búsqueda; el perfil no justificó separar todavía una caché de peones dependiente de reyes y torres.
- [x] Registrar NPS, profundidad, profundidad selectiva, aciertos de TT, cortes beta, cortes con el primer movimiento, quietud, ramificación y memoria de hash.
- [x] Validar corrección, benchmark, suite táctica y partidas automatizadas; conservar decisiones y resultados, incluidas campañas desfavorables.
- [x] Evaluar el salto a multihilo y mantener esta versión monohilo como referencia determinista hasta disponer de una campaña estadística mayor.
- [x] Evaluar Syzygy como ampliación opcional; documentar WDL/DTZ y conservar funcionamiento completo sin tablas externas.
- [ ] **Cierre:** el perfil optimizado conserva jugada/puntuación a profundidad fija y reduce un 41,7 % los nodos, pero obtuvo 30,5–33,5 en 64 partidas a 50 ms: −16 Elo estimados, IC 95 % [−64, +31]. No se promociona como predeterminado hasta demostrar fuerza.

## Fase 6 — Analizar partidas y explicar posiciones

- [x] Implementar MultiPV y acceso a alternativas, evaluación estática, evaluación de búsqueda y metadatos.
- [x] Importar PGN en Python, reproducir las partidas y analizar cada movimiento con límites comparables.
- [x] Comparar mejor movimiento y movimiento jugado desde una misma perspectiva; calcular pérdida en centipeones y tratar mates por separado.
- [x] Clasificar jugadas con umbrales configurables para imprecisiones, errores y errores graves.
- [x] Exportar JSON estructurado, PGN anotado y un informe legible con PV, alternativas y desglose antes/después.
- [x] Definir el transporte mediante UCI estándar y la consola JSON de evaluación, sin introducir extensiones en las líneas de búsqueda.
- [x] Generar contexto de explicación con FEN, turno, jugada, candidatos, PV, componentes, historial y evidencias disponibles.
- [x] Implementar una explicación básica sin LLM y un adaptador opcional para cualquier proceso local intercambiable.
- [x] Permitir preguntas sobre posiciones y comparaciones de jugadas; solicitar nueva búsqueda al motor si falta una candidata.
- [x] Exigir al adaptador que use las puntuaciones y variantes proporcionadas, distinga hechos de interpretación y no afirme tácticas forzadas sin evidencia.
- [x] **Cierre:** una partida se transforma en análisis por jugada, JSON, informe y PGN anotado; el asistente explica datos verificables y funciona sin LLM.

Evidencia de las fases 5/6: [búsqueda y benchmark](docs/search.md), [análisis y explicaciones](docs/analysis.md) y [resultados de validación](docs/validation.md).

## Fase 7 — Partidas entre motores, aperturas y autojuego

- [x] Ampliar el comparador mínimo a un runner para ChessBot, Stockfish, cualquier ejecutable UCI local y versiones o redes anteriores.
- [x] Configurar por motor su ejecutable, opciones UCI, hash, hilos, evaluador/red, directorio de trabajo y entorno.
- [x] Gestionar arranque, handshake, disponibilidad, sincronización de posición, relojes, `bestmove` y terminación.
- [x] Detectar movimientos ilegales, timeouts y caídas; aplicar una política explícita y guardar los logs del fallo.
- [x] Admitir posición inicial, FEN arbitrario, prefijos PGN/UCI, aperturas con nombre y variantes exactas.
- [x] Validar y normalizar aperturas a FEN más movimientos UCI, con identificador, ECO cuando exista y ply de liberación.
- [x] Importar suites PGN, EPD, listas FEN/UCI, datos Polyglot y base nativa.
- [x] Permitir color fijo, alternancia y parejas de partidas con colores invertidos desde la misma posición.
- [x] Implementar libro propio opcional con `OwnBook`, `BookFile` y `BookPolicy`, validación de jugadas y vuelta a búsqueda fuera de libro.
- [x] Guardar estadísticas, procedencia y motivo de selección de las jugadas del libro; versionarlo de forma independiente.
- [x] Separar el prefijo que fuerza el runner del libro que cada motor puede consultar después de liberarse.
- [x] Generar diversidad controlada en autojuego con aperturas, semillas y versiones; mantener estables las condiciones de las pruebas de fuerza.
- [x] Guardar PGN, FEN final, resultado, causa de terminación, relojes y metadatos reproducibles de cada experimento.
- [x] Automatizar comparación con referencia mediante victorias/tablas/derrotas, porcentaje, Elo estimado e intervalo de confianza; añadir SPRT cuando corresponda.
- [x] **Cierre:** funcionan los escenarios A–F de `specs.md`, incluido entrenamiento desde una línea exacta, con color fijo y libro activado o desactivado.

## Fase 8 — Ajustar automáticamente la evaluación manual

- [x] Generar datasets de partidas, posiciones, características, evaluaciones de búsqueda y resultados.
- [x] Empezar con CSV/Parquet y definir un esquema versionado con Zobrist, FEN, turno, ply y procedencia.
- [x] Filtrar posiciones de poca utilidad, deduplicar, equilibrar rangos y limitar muestras correlacionadas.
- [x] Separar entrenamiento y validación por partidas/origen, evitando posiciones duplicadas entre conjuntos.
- [x] Implementar un ajuste inicial tipo Texel u otro método documentado para pesos de material, movilidad, peones y seguridad del rey.
- [x] Calibrar la transformación entre centipeones y probabilidad de resultado con datos.
- [x] Exportar parámetros candidatos y conservar siempre la referencia anterior.
- [x] Automatizar aceptación/rechazo según corrección, rendimiento, táctica, regresiones y fuerza en partidas.
- [ ] **Cierre:** un candidato ajustado mejora la referencia en validación ajedrecística; una menor pérdida de entrenamiento no basta.

  Evidencia 2026-09-15: el pipeline produjo y rechazó `hce-texel-phase8-v1`. Mejoró ligeramente la pérdida de validación (0,634433 → 0,634411), pero quedó 25–49–26 en 100 partidas sobre 50 aperturas independientes: −3,5 Elo estimados, IC95% [−51,0, +43,9]. La referencia sigue activa.

## Fase 9 — Incorporar evaluación neuronal

- [ ] Definir características de entrada y etiquetas de búsqueda, resultado o una combinación documentada.
- [ ] Entrenar una red pequeña en Python/PyTorch manteniendo búsqueda alfa-beta.
- [ ] Versionar arquitectura, dataset, pesos, normalización y formato de exportación.
- [ ] Integrar inferencia CPU en C++ y comprobar equivalencia con la salida de Python.
- [ ] Evolucionar hacia NNUE con acumuladores incrementales y pruebas de actualización/restauración.
- [ ] Exponer `NNUE` y `NNUEFile`; mantener disponible el evaluador manual.
- [ ] En modo neuronal, identificar el origen de cada puntuación y presentar el desglose manual como referencia, sin atribuirle la suma de la salida neuronal.
- [ ] Medir latencia, NPS, memoria, pérdida de validación, calibración WDL y fuerza real tras integrar la red.
- [ ] Escalar a shards binarios cuando el volumen lo justifique.
- [ ] **Cierre:** red reproducible, inferencia validada y candidato aceptado mediante partidas y suite de regresión.

## Fase 10 — Cerrar el ciclo de aprendizaje continuo

- [ ] Orquestar el ciclo `partidas → datos → filtrado → entrenamiento → candidato → pruebas → promoción o rechazo`.
- [ ] Ejecutar trabajos por lotes con presupuesto de partidas, tiempo, almacenamiento y recursos configurable.
- [ ] Guardar versión del binario, búsqueda, evaluación, libro, red y dataset, además de commit, semilla, compilador, opciones y hardware.
- [ ] Conservar los artefactos y resultados necesarios para reproducir cada promoción y restaurar la referencia anterior.
- [ ] Separar el CI rápido de las campañas largas de fuerza y entrenamiento.
- [ ] Evitar que una partida individual modifique directamente el motor activo.
- [ ] Documentar compilación, uso UCI, análisis, aperturas, entrenamiento, comparación y resolución de errores.
- [ ] Ejecutar de extremo a extremo todos los escenarios A–H de `specs.md`, incluida la explicación local con búsqueda adicional cuando sea necesaria.
- [ ] **Cierre:** una ejecución completa produce un candidato, lo evalúa y lo promociona o rechaza con evidencia reproducible.

## Reglas de seguimiento

- [ ] Mantener las casillas pendientes hasta verificar el entregable y su criterio de cierre.
- [ ] Vincular cada mejora a al menos un resultado: corrección, fuerza, calidad de análisis, velocidad, memoria o explicabilidad.
- [ ] Registrar regresiones y límites de la medición; tratar las metas de NPS de la especificación como orientativas y dependientes del hardware.
- [ ] Mantener el núcleo independiente de `python-chess`, motores externos, servicios de nube y LLM.
- [ ] Actualizar [readme.md](readme.md) conforme las capacidades previstas se conviertan en funcionalidades disponibles.
