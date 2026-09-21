# Resultados de validación

Comprobaciones ejecutadas del 14 al 21 de septiembre de 2026 en Windows x64, con AMD Ryzen 7 7800X3D, MSVC 19.51.36252, CMake 4.4.3 y Python 3.12.7. Son resultados históricos, no una certificación del estado de cada clon; las cifras de rendimiento dependen del equipo. Para repetir las comprobaciones, consulta [desarrollo](development.md).

| Comprobación | Resultado |
| --- | --- |
| Compilación Release y Debug | Correcta, sin avisos del código propio |
| CTest Release | 3/3 pruebas, incluida PERFT completa |
| CTest Debug sin etiqueta `slow` | 2/2 pruebas |
| Suite doctest rápida | 41 casos y más de 29.500 aserciones: reglas, evaluación parametrizada, NNUE incremental, libro, mates, táctica, límites, null-move, MultiPV y transposiciones |
| Restauración aleatoria | Hasta 40 partidas de 150 plies, comprobando todos los estados al retroceder |
| Comparación Release con python-chess | 15.675 posiciones y 24 fixtures PERFT hasta profundidad 3 |
| Comparación Debug con python-chess | 1.874 posiciones y 24 fixtures PERFT hasta profundidad 3 |
| CLI Release/Debug | Entradas inválidas, recuperación JSON, reproducción FEN, PERFT y divide correctos |
| UCI Release/Debug | Handshake, opciones, errores, evaluación, profundidad, nodos, tiempo, infinito, `isready` concurrente y `stop` correctos |
| Simetría de evaluación | 1.600 posiciones aleatorias reflejadas por color/tablero |
| Partidas completas | 2 partidas UCI de autojuego, ambas válidas y terminadas por triple repetición |
| Evaluación posicional frente a básica | 13–3 en 16 partidas, profundidad 3, ocho aperturas con colores invertidos |
| Benchmark Baseline | 567.651 nodos, 1.415 ms y ~401.166 NPS a profundidad 5 |
| Benchmark Optimized actual | 33.351 nodos y 42 ms; 94,1 % menos nodos que Baseline |
| Partidas de búsqueda actuales | Comprobación corta: Optimized 10–6 Baseline en 16 partidas a 20 ms; 5 victorias, 10 tablas y 1 derrota |
| Análisis de PGN | JSON, PGN anotado, informe Markdown, MultiPV, `searchmoves` y explicación con búsqueda adicional correctos |
| Runner de fase 7 | Escenarios A–F, importadores JSON/PGN/EPD/FEN/UCI/Polyglot, libro y metadatos correctos |
| Pipeline de fase 8 | Dataset de 2.528 posiciones/126 partidas, particiones sin solapamiento, ajuste, carga y puertas de promoción correctos |
| Candidato HCE de fase 8 | Rechazado: 25–49–26 en 100 partidas/50 aperturas, −3,5 Elo, IC95% [−51,0, +43,9] |
| Equivalencia NNUE | 63 posiciones con puntuación entera idéntica en Python/C++, más activación UCI y retorno a HCE |
| Candidato NNUE de fase 9 | Rechazado: 0–0–16 frente a HCE; conserva red, entrenamiento, calibración y decisión |
| Ciclo de fase 10 | 1.406 muestras, 18 artefactos con SHA-256 y rechazo seguro sin cambiar la referencia activa |
| Formato C++ | Conforme a clang-format 21.1.8 |
| Instalación Python y `pip check` | Extras de desarrollo instalados, dependencias consistentes |
| GitHub Actions | Windows/Linux Debug/Release y ASan/UBSan: 5/5 jobs correctos en la ejecución `34999479369` |

Los fixtures cubren posición inicial, Kiwipete, final de torres y peones, enroques, promociones, clavadas, jaque doble, jaque descubierto y en passant legal/ilegal. La herramienta incorpora también sus reflejos con colores invertidos.

## PERFT de posición inicial

| Profundidad | Nodos verificados |
| --- | ---: |
| 0 | 1 |
| 1 | 20 |
| 2 | 400 |
| 3 | 8.902 |
| 4 | 197.281 |
| 5 | 4.865.609 |
| 6 | 119.060.324 |

## Reproducción de las comparaciones externas

```powershell
.\.venv\Scripts\python.exe tools/validate_rules.py --engine build/Release/chessbot.exe --games 80 --plies 200 --seed 20260914 --perft-depth 3
.\.venv\Scripts\python.exe tools/validate_rules.py --engine build/Debug/chessbot.exe --games 12 --plies 80 --seed 20260914 --perft-depth 2
.\.venv\Scripts\python.exe tools/test_cli.py --engine build/Release/chessbot.exe
.\.venv\Scripts\python.exe tools/test_cli.py --engine build/Debug/chessbot.exe
.\.venv\Scripts\python.exe tools/test_uci.py --engine build/Release/chessbot.exe
.\.venv\Scripts\python.exe tools/test_uci.py --engine build/Debug/chessbot.exe
.\.venv\Scripts\python.exe tools/test_match_runner.py --engine build/Release/chessbot.exe
.\.venv\Scripts\python.exe tools/test_tuning.py --engine build/Release/chessbot.exe
.\.venv\Scripts\python.exe tools/test_nnue.py --engine build/Release/chessbot.exe
.\build\Release\chessbot.exe bench 5
```

La referencia es python-chess 1.999 con módulo chess 1.11.2. El número de posiciones depende de la semilla, los límites y la terminación de las partidas.

## Comparación del evaluador

La referencia `Basic` contiene material, PST y tempo. `Positional` añadió el resto de componentes sin cambiar búsqueda, profundidad, binario ni aperturas:

```powershell
.\.venv\Scripts\python.exe tools/compare_engines.py --engine-a build/Release/chessbot.exe --engine-b build/Release/chessbot.exe --evaluation-a Positional --evaluation-b Basic --games 16 --depth 3 --max-plies 180 --openings tests/positions/benchmark.fen --output data/engine_matches/phase4-positional-vs-basic-d3.pgn
```

`Positional` consiguió 13/16. El runner validó todos los movimientos y alternó colores para cada FEN. Dieciséis partidas no permiten inferir Elo con confianza; el resultado confirma el flujo y da una señal favorable que deberá repetirse a mayor escala.

## Candidato de búsqueda de fase 5

Las cuatro posiciones de benchmark devolvieron la misma jugada y puntuación en `Baseline` y `Optimized` a profundidad 5. Una comprobación adicional sobre 32 aperturas confirmó igualdad exacta a profundidad 4. El perfil optimizado redujo el benchmark de 567.651 a 330.683 nodos.

La campaña final usó 32 posiciones reproducibles de `tests/positions/phase5_openings.fen`, colores invertidos, 50 ms por jugada, 2 ms de margen y un máximo de 100 plies:

```powershell
.\.venv\Scripts\python.exe tools/compare_engines.py --engine-a build/Release/chessbot.exe --engine-b build/Release/chessbot.exe --search-a Optimized --search-b Baseline --games 64 --movetime-ms 50 --move-overhead 2 --max-plies 100 --openings tests/positions/phase5_openings.fen --output data/engine_matches/phase5-final-50ms-64.pgn
```

`Optimized` obtuvo 10 victorias, 41 tablas y 13 derrotas: 30,5/64 (47,7 %). La aproximación normal sobre los resultados por pareja da −16 Elo y un intervalo del 95 % de [−64, +31]. El intervalo incluye paridad y el punto estimado no es favorable, por lo que el perfil permanece disponible para experimentar pero `Baseline` sigue predeterminado. Esto deja abierto únicamente el criterio de promoción estadística de la fase 5.

El 21 de septiembre se revisó `Optimized` para el análisis interactivo: candidatos pseudo-legales validados durante la búsqueda, quietud táctica, poda delta, razoring, poda por evaluación estática y movimientos tardíos, null-move desde profundidad 3, LMR graduada, reducción iterativa interna y reutilización segura de transposiciones lejos del límite de 50 jugadas. Lazy SMP publica los nodos por lotes y diversifica los ayudantes omitiendo iteraciones. El benchmark bajó de 567.651 a 33.351 nodos. Una comprobación nueva de 16 partidas a 20 ms terminó 5–10–1 para el perfil revisado, equivalente a 10–6 puntos; por su tamaño reducido no sustituye una campaña larga. `Baseline` permanece como referencia reproducible, mientras la pestaña Análisis usa explícitamente el perfil rápido. En la posición inicial, una variante a profundidad 20 y ocho hilos pasó de 144,5 s al inicio de esta revisión a 33,1 s.

## Análisis de fase 6

La prueba integral toma `tests/positions/analysis_sample.pgn`, analiza tres plies con dos variantes, genera JSON/PGN/Markdown y formula una pregunta sobre una jugada que no estaba entre las candidatas:

```powershell
.\.venv\Scripts\python.exe tools/test_analysis.py --engine build/Release/chessbot.exe
```

Se verifican el esquema versionado, la perspectiva de la jugada disputada, dos candidatos distintos, los desgloses antes/después, los comentarios PGN reproducibles y el contexto de una búsqueda adicional.

## Partidas y aperturas de fase 7

`tools/test_match_runner.py` importa todas las fuentes admitidas y ejecuta los escenarios A–F: partida libre emparejada sin libro, Grünfeld con ChessBot fijo con negras, línea SAN exacta, FEN arbitraria y libro propio con procedencia. Todos los PGN se vuelven a analizar con python-chess y cada experimento exige sus tres artefactos.

El libro de prueba seleccionó `e2e4` con política `best`, eligió de forma reproducible con `weighted` y devolvió a búsqueda al salir de sus entradas. La suite `strength-v1.json` contiene 50 aperturas o posiciones iniciales distintas. Los intervalos agrupan parejas repetidas por apertura para no aumentar artificialmente la muestra.

## Ajuste manual de fase 8

El dataset registrado tomó dos campañas previas, descartó ocho plies iniciales, muestreó uno de cada tres y limitó a 40 posiciones por partida y 400 por bucket de 200 cp. Quedaron 2.528 posiciones únicas de 126 partidas: 2.011 para entrenamiento y 517 para validación, con separación por partida y deduplicación Zobrist global.

El candidato `hce-texel-phase8-v1` redujo la entropía cruzada de validación de 0,634433 a 0,634411. Superó PERFT, tres posiciones tácticas y el límite de rendimiento. En la campaña decisiva a profundidad 2 obtuvo 25 victorias, 49 tablas y 26 derrotas contra `hce-default-v1`: −3,5 Elo, IC95% [−51,0, +43,9], sobre 50 parejas de apertura independientes. La puerta de fuerza lo rechazó y `hce-active.params` permanece idéntico a la referencia. El informe reproducible está en `data/evaluation/phase8-experiment-v1.json`.

## Validación remota y limitación local

La ejecución [GitHub Actions 34999479369](https://github.com/villarrubi/ChessBot/actions/runs/34999479369) completó correctamente los cinco jobs: Windows y Ubuntu en Debug/Release, más el job Linux con AddressSanitizer y UndefinedBehaviorSanitizer. Incluyó reglas, CLI, UCI, análisis, runner, ajuste, equivalencia NNUE y formato.

La compilación local con MSVC AddressSanitizer sigue sin poder enlazarse porque esta máquina no tiene `clang_rt.asan_dynamic_runtime_thunk-x86_64.lib`. Esta limitación del entorno local queda cubierta por el job ASan/UBSan de Linux.

Los contratos de FEN, historial, tablas y límites de la validación están documentados en [architecture.md](architecture.md).

## Evaluación neuronal y ciclo completo

La red `nnue-phase9-v1` usa 768 entradas, 32 neuronas ocultas ReLU y salida cuantizada. Su
validación registró pérdida 0,92940, Brier 0,07081, error de calibración WDL 0,10793 y MAE respecto
al profesor de 430,42 cp. La prueba de paridad reprodujo exactamente 63 puntuaciones entre Python
y C++; doctest contrastó refresco y actualización incremental tras movimientos normales,
capturas, en passant, enroques y promociones. El candidato perdió las 16 partidas de ocho parejas
de apertura y no pasó táctica, por lo que fue rechazado.

`phase10-cycle-v1` ejecutó partidas → datos → entrenamiento → candidato → evaluación bajo límites
de 300 segundos, 50 MB y un hilo. Generó 1.406 filas separadas en 1.113 de entrenamiento y 293 de
validación. La red `768×16×1` ocupó 24.680 bytes; pasó PERFT, las tres posiciones tácticas y produjo
pérdida 0,91096, Brier 0,08806 y ECE 0,07148. El benchmark midió 165.007 NPS frente a 382.026 de
HCE y la campaña mínima terminó 0–1–1. Las puertas de rendimiento y fuerza la rechazaron. El ciclo
terminó en 4,766 segundos, conservó 18 artefactos y no ejecutó la promoción.

Los escenarios A–F continúan cubiertos por `test_match_runner.py`; G y H, incluida una búsqueda
restringida adicional para una jugada ausente de MultiPV, por `test_analysis.py`. `test_nnue.py`
añade procedencia neuronal al análisis, y `test_learning_cycle.py` verifica manifiesto, hashes,
presupuestos y que un rechazo no reemplaza el archivo activo.

## Análisis de escritorio y asistente local

La ampliación de análisis añade pruebas reproducibles de PGN, FEN, historial, alternativas SAN, mates y adaptadores de IA en `test_analysis_session.py` y `test_explainer.py`. La interfaz tiene una prueba Windows en `tests/launcher/` que genera capturas y comprueba navegación, explicaciones y cancelación. Estas comprobaciones complementan la suite C++ y el análisis PGN existente; no miden fuerza Elo ni demuestran que cualquier respuesta de un LLM sea correcta.

Comprobaciones locales del 21 de septiembre de 2026:

- Compilación Release del lanzador sin errores ni advertencias.
- CTest Release: 3/3, incluida PERFT completa.
- Análisis PGN y sesión de escritorio: pruebas completas correctas.
- Adaptador y explicaciones: ocho regresiones correctas sin depender de un modelo.
- WinForms: navegación, tablero posterior, explicación básica y cancelación de una búsqueda en curso correctas; capturas revisadas a 1040×760 y 900×690.
- Ollama con `qwen3.5:9b`: respuesta real sobre un mate y una alternativa SAN con búsqueda adicional; fallback comprobado solicitando un modelo inexistente.
- Ruff, formato C++ y enlaces relativos de la documentación comprobados.

La automatización remota de ventanas no estaba disponible; la comprobación visual utilizó las capturas de la prueba WinForms. Estas comprobaciones locales no sustituyen una nueva ejecución de CI en Linux y Windows.
