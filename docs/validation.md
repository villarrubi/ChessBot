# Validación de las fases 0–8

Comprobaciones ejecutadas el 14 y 15 de septiembre de 2026 en Windows x64, con AMD Ryzen 7 7800X3D, MSVC 19.51.36252, CMake 4.4.3 y Python 3.12.7. Son resultados de esta entrega; las cifras de rendimiento dependen del equipo.

| Comprobación | Resultado |
| --- | --- |
| Compilación Release y Debug | Correcta, sin avisos del código propio |
| CTest Release | 3/3 pruebas, incluida PERFT completa |
| CTest Debug sin etiqueta `slow` | 2/2 pruebas |
| Suite doctest rápida | 34 casos y 29.321 aserciones: reglas, evaluación parametrizada, libro, mates, táctica, límites, null-move, MultiPV y transposiciones |
| Restauración aleatoria | Hasta 40 partidas de 150 plies, comprobando todos los estados al retroceder |
| Comparación Release con python-chess | 15.675 posiciones y 24 fixtures PERFT hasta profundidad 3 |
| Comparación Debug con python-chess | 1.874 posiciones y 24 fixtures PERFT hasta profundidad 3 |
| CLI Release/Debug | Entradas inválidas, recuperación JSON, reproducción FEN, PERFT y divide correctos |
| UCI Release/Debug | Handshake, opciones, errores, evaluación, profundidad, nodos, tiempo, infinito, `isready` concurrente y `stop` correctos |
| Simetría de evaluación | 1.600 posiciones aleatorias reflejadas por color/tablero |
| Partidas completas | 2 partidas UCI de autojuego, ambas válidas y terminadas por triple repetición |
| Evaluación posicional frente a básica | 13–3 en 16 partidas, profundidad 3, ocho aperturas con colores invertidos |
| Benchmark Baseline | 567.651 nodos, 1.430 ms y ~396.958 NPS a profundidad 5 |
| Benchmark Optimized | 330.683 nodos, 866 ms y ~381.851 NPS; mismas jugadas/puntuaciones, 41,7 % menos nodos |
| Partidas de búsqueda | Optimized 30,5–33,5 Baseline en 64 partidas a 50 ms; −16 Elo, IC 95 % [−64, +31] |
| Análisis de PGN | JSON, PGN anotado, informe Markdown, MultiPV, `searchmoves` y explicación con búsqueda adicional correctos |
| Runner de fase 7 | Escenarios A–F, importadores JSON/PGN/EPD/FEN/UCI/Polyglot, libro y metadatos correctos |
| Pipeline de fase 8 | Dataset de 2.528 posiciones/126 partidas, particiones sin solapamiento, ajuste, carga y puertas de promoción correctos |
| Candidato HCE de fase 8 | Rechazado: 25–49–26 en 100 partidas/50 aperturas, −3,5 Elo, IC95% [−51,0, +43,9] |
| Formato C++ | Conforme a clang-format 21.1.8 |
| Instalación Python y `pip check` | Extras de desarrollo instalados, dependencias consistentes |

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

## Pendiente de comprobar en otro entorno

- La primera ejecución de GitHub Actions confirmó Windows Debug/Release y descubrió una deducción de tipos no portable en GCC. La inicialización ya usa tipos explícitos; la nueva matriz Windows/Linux y sanitizadores se verificará con el push final.
- La compilación local con MSVC AddressSanitizer llegó al enlazado y falló por falta de `clang_rt.asan_dynamic_runtime_thunk-x86_64.lib`. No se afirma que las pruebas con sanitizadores hayan pasado. Requieren el componente ASan de Visual Studio o ejecutar el job Linux con ASan/UBSan.
- No se ha ejecutado una compilación Linux localmente. Esa validación forma parte de la matriz CI preparada.

Los contratos de FEN, historial, tablas y límites de la validación están documentados en [architecture.md](architecture.md).
