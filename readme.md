# ChessBot

Motor de ajedrez desarrollado desde cero en C++20 para jugar, analizar partidas, explicar evaluaciones y mejorar mediante autojuego y entrenamiento controlado.

> **Estado actual: funcionalidades de las fases 0–10 implementadas.** Ya funcionan las reglas, búsqueda y evaluación explicable, UCI MultiPV, análisis PGN, libro propio, partidas reproducibles, ajuste tipo Texel, entrenamiento e inferencia NNUE y el ciclo automático de aprendizaje. Los candidatos que no demostraron fuerza quedaron rechazados y la referencia HCE estable sigue activa. El detalle está en [roadmap.md](roadmap.md).

## Aplicación de Windows

`ChessBot Launcher` permite jugar contra el motor, entrenar redes y ejecutar el ciclo completo desde
una interfaz gráfica. El acceso directo **ChessBot** del escritorio abre la aplicación sin mostrar
una terminal.

Para reconstruir el lanzador y volver a crear el acceso directo:

```powershell
.\tools\build_launcher.ps1
```

El ejecutable se genera en `build/launcher/ChessBot Launcher.exe`. La pestaña **Jugar** contiene el
tablero; **Entrenar** permite elegir autojuego o un motor UCI rival, partidas, profundidad, tamaño
de red y objetivo, y muestra el progreso; **Herramientas** permite compilar, ejecutar el benchmark
y abrir los resultados.

## Probar la versión actual

Con Visual Studio y sus herramientas C++ instaladas, desde PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\cmake.exe -S . -B build -A x64 -DCHESSBOT_SLOW_TESTS=ON
.\.venv\Scripts\cmake.exe --build build --config Release --parallel
.\.venv\Scripts\ctest.exe --test-dir build -C Release --output-on-failure
.\build\Release\chessbot.exe inspect --moves "e2e4 e7e5"
.\build\Release\chessbot.exe eval --moves "e2e4 e7e5"
.\build\Release\chessbot.exe bench 5
.\build\Release\chessbot.exe perft 6
.\build\Release\chessbot.exe divide 3
.\.venv\Scripts\python.exe tools/test_match_runner.py --engine build/Release/chessbot.exe
.\.venv\Scripts\python.exe tools/test_tuning.py --engine build/Release/chessbot.exe
.\.venv\Scripts\python.exe tools/test_nnue.py --engine build/Release/chessbot.exe
```

PERFT de la posición inicial a profundidad 6 devuelve `119060324`. `inspect` muestra el estado y las jugadas legales; `eval`, el desglose de evaluación; `bench`, una referencia de búsqueda; y `divide`, los nodos por jugada. Al ejecutar el binario sin argumentos se inicia UCI y ya puede añadirse a una GUI compatible.

Las instrucciones para Debug, Linux, validación con python-chess y sanitizadores están en [docs/development.md](docs/development.md). Los resultados locales y las comprobaciones pendientes están en [docs/validation.md](docs/validation.md).

Las secciones siguientes describen el proyecto completo y el estado medido de sus candidatos.

## Qué ofrecerá el proyecto terminado

- Juego autónomo con reglas propias, búsqueda alfa-beta y límites configurables de tiempo, profundidad o nodos.
- Compatibilidad UCI para jugar y analizar desde interfaces gráficas de ajedrez.
- Análisis de posiciones FEN y partidas PGN, con alternativas, variantes principales y clasificación de errores.
- Evaluación manual explicable: material, colocación, movilidad, peones, seguridad del rey, espacio y otros componentes.
- Partidas contra sí mismo, Stockfish, cualquier motor UCI local o versiones anteriores de ChessBot.
- Entrenamiento desde aperturas concretas, posiciones arbitrarias o líneas exactas, con control de colores y del uso del libro.
- Ajuste de parámetros y evaluación neuronal con inferencia CPU de tipo NNUE.
- Asistente local opcional para preguntar por posiciones y jugadas a partir de los cálculos del motor.
- Experimentos reproducibles y promoción de mejoras respaldada por pruebas y partidas.

El núcleo implementa sus propias reglas y elige sus jugadas. Los motores externos sirven como rivales, referencias de validación o fuentes de datos comparativos. El funcionamiento básico, el análisis y las explicaciones locales no requieren servicios de nube.

## Cómo funciona

La GUI o las herramientas Python envían posiciones y órdenes a través de UCI. El motor genera movimientos legales, explora continuaciones y evalúa las posiciones con el evaluador manual o neuronal configurado.

El analizador convierte esos resultados en informes estructurados. El asistente local recibe las evidencias del análisis y las explica; cuando una pregunta exige calcular otra variante, solicita una nueva búsqueda al motor.

El aprendizaje se realiza por lotes: las partidas generan datos, el entrenamiento produce un candidato y las pruebas determinan si sustituye a la referencia anterior.

## Requisitos previstos

| Componente | Requisito | Uso |
| --- | --- | --- |
| Núcleo | Compilador compatible con C++20 y CMake | Compilar el motor |
| Herramientas | Python 3.12+ | Análisis, partidas y experimentos |
| Validación y datos | python-chess, NumPy y pandas | Herramientas Python; reglas del núcleo implementadas en C++ |
| Entrenamiento neuronal | PyTorch | Entrenar y exportar redes |
| Gráficas | matplotlib | Informes de benchmarks y experimentos |
| Juego desde GUI | ChessBot Launcher incluido; interfaces UCI externas opcionales | Jugar y administrar el proyecto |
| Rivales | Ejecutables locales compatibles con UCI | Opcionales para partidas externas |
| Explicación conversacional | Runtime y modelo local compatibles con el adaptador | Opcionales; por ejemplo, Ollama o llama.cpp |
| Finales exactos | Tablas Syzygy | Opcionales |

El motor y la inferencia de evaluación funcionan en CPU. No se requiere GPU para jugar. Los motores externos, modelos de lenguaje, libros y tablas se configuran por separado.

## Compilación y primera ejecución

Ejemplo desde la raíz del repositorio en Windows, usando un generador CMake con configuraciones Debug/Release:

```powershell
cmake -S . -B build
cmake --build build --config Release
ctest --test-dir build -C Release --output-on-failure
.\build\Release\chessbot.exe
```

Con un generador de una sola configuración, como Ninja, se configura `-DCMAKE_BUILD_TYPE=Release` y el ejecutable queda en `build/chessbot.exe` en Windows o `build/chessbot` en sistemas Unix.

`ChessBot Launcher` proporciona la interfaz gráfica propia. Para usar una GUI externa, se añade
`build/Release/chessbot.exe` como motor UCI y se ajustan sus opciones desde esa interfaz.

## Uso mediante UCI

Después de iniciar el ejecutable, enviar las órdenes de forma interactiva. Esperar `uciok` tras `uci` y `readyok` tras `isready`:

```text
uci
setoption name Hash value 64
setoption name Threads value 1
setoption name OwnBook value false
isready
ucinewgame
position startpos moves e2e4 e7e5 g1f3
go movetime 3000
```

El motor informa del avance mediante líneas `info` y termina con `bestmove`. Para analizar una FEN o aplicar otros límites, usar una de estas órdenes de búsqueda cada vez y esperar su finalización:

```text
position fen rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1
go depth 12
```

```text
go nodes 1000000
```

```text
go wtime 120000 btime 120000 winc 1000 binc 1000
```

`go infinite` mantiene el análisis hasta recibir `stop`. `quit` cierra el proceso.

### Opciones del motor

| Opción | Función |
| --- | --- |
| `Hash` | Memoria de la tabla de transposición, en MB |
| `Threads` | Número de hilos de búsqueda |
| `Move Overhead` | Margen de tiempo para comunicación y ejecución |
| `SearchProfile` | `Baseline` conserva la referencia de fase 4; `Optimized` activa PVS, aspiración y podas verificadas |
| `Evaluation` | `Basic` reproduce material/PST de fase 2; `Positional` activa el desglose de fase 4 |
| `EvalFile` | Archivo versionado de multiplicadores de la evaluación manual |
| `OwnBook` | Activa o desactiva el libro nativo |
| `BookFile` | Ruta del libro TSV versionado |
| `BookPolicy` | Selección `best`, `weighted`, `random` o `explore` |
| `BookSeed` | Semilla reproducible de selección |
| `MultiPV` | Número de alternativas de raíz, entre 1 y 10 |
| `AnalysisDetail` | `Full` añade evaluación estática y métricas internas de búsqueda |
| `NNUEFile` | Carga una red cuantizada `CHESSBOT_NNUE 1` desde disco |
| `NNUE` | Activa la red cargada o vuelve al evaluador manual |

La configuración inicial utiliza un hilo, 64 MB de hash y evaluación manual posicional, con NNUE y libro desactivados. Para usar una red, se establece primero `NNUEFile` y después `NNUE=true`; los errores se devuelven mediante `info string error`.

```text
setoption name NNUEFile value data/networks/nnue-phase9-candidate-v1.nnue
setoption name NNUE value true
isready
```

La red incluida es un candidato reproducible rechazado, útil para pruebas y desarrollo. No es la referencia de juego recomendada.

## Analizar posiciones y partidas

El análisis de una posición muestra mejor jugada, alternativas MultiPV, variante principal, profundidad, nodos, NPS y uso de hash. La vista detallada añade evaluación estática, evaluación de búsqueda, componentes posicionales y estado del libro.

Para analizar una partida completa con la versión actual:

```powershell
.\.venv\Scripts\python.exe tools/analyze_pgn.py --input partida.pgn --engine build/Release/chessbot.exe --depth 5 --multipv 3 --json data/analysis/partida.json --annotated-pgn data/analysis/partida-anotada.pgn --report data/analysis/partida.md
```

Los límites `--movetime-ms` y `--nodes` pueden sustituir a `--depth`. La guía completa del esquema, los umbrales y el uso con motores externos está en [docs/analysis.md](docs/analysis.md).

La evaluación estática describe la posición actual; la evaluación de búsqueda incorpora las continuaciones exploradas. Se muestran separadas y con la perspectiva identificada. Internamente, 100 centipeones equivalen a un peón; los mates se presentan como distancia al mate.

El analizador PGN compara cada movimiento jugado con la mejor alternativa, calcula la pérdida desde una misma perspectiva y aplica umbrales configurables para imprecisiones, errores y errores graves. Genera JSON estructurado, PGN anotado y un informe legible.

Las cifras de un desglose manual suman su evaluación estática. Si está activa NNUE, el desglose manual se identifica como evaluación auxiliar y la salida neuronal se presenta por separado.

## Partidas entre motores y entrenamiento de aperturas

`tools/match_runner.py` ejecuta partidas entre dos motores UCI locales, valida cada jugada y guarda PGN, metadatos JSON y logs. Admite profundidad, nodos, tiempo por jugada o reloj completo, además de líneas forzadas, aperturas y opciones independientes por motor.

Ejemplo de la interfaz actual para organizar partidas a profundidad fija contra un rival local:

```powershell
python tools/match_runner.py --engine-a .\build\Release\chessbot.exe --engine-b C:\motores\stockfish.exe --games 16 --depth 3 --openings data/openings/core.json --color-mode paired --output-dir data/engine_matches/prueba
```

La ruta del rival debe sustituirse por la instalación local. En comparaciones de fuerza, el runner utiliza parejas con colores invertidos y la misma posición de salida. Cada experimento registra configuración, relojes, opciones de libro, evaluadores y procedencia. La guía completa está en [docs/openings-and-matches.md](docs/openings-and-matches.md).

Se admiten estos puntos de partida:

- Posición inicial, con cálculo desde la primera jugada.
- Una FEN concreta para practicar un medio juego, final o posición táctica.
- Una línea PGN/UCI validada que el runner fuerza antes de liberar a los motores.
- Una apertura o variante identificada en una suite reproducible, con posiciones y líneas concretas.

Es posible mantener ChessBot siempre con blancas o negras, alternar colores o jugar parejas. Por ejemplo, un trabajo puede programar 200 partidas de la Grünfeld con ChessBot como negras, un prefijo forzado y el libro propio desactivado.

El prefijo forzado pertenece al runner. El libro propio pertenece al motor: con `OwnBook = false`, calcula desde la posición recibida; con `OwnBook = true`, consulta el libro y vuelve a buscar cuando no encuentra una entrada utilizable. Cada partida conserva la apertura, el ply de liberación, la versión del libro y su configuración.

Los resultados incluyen PGN, FEN final, relojes, causa de terminación y metadatos. Los fallos de proceso, tiempos agotados y movimientos ilegales quedan registrados según la política del experimento.

## Preguntar al asistente local

El asistente responde preguntas como «¿Por qué negras están mejor?», «¿Qué falla en este sacrificio?» o «¿Qué cambia si juego Dd2?» utilizando la posición, las puntuaciones, los componentes y las variantes que proporciona el motor.

El adaptador permite cambiar de runtime local o usar explicaciones estructuradas sin LLM. Las respuestas distinguen los datos calculados de la interpretación y explicitan cuándo falta evidencia. El motor conserva la responsabilidad sobre legalidad, puntuaciones, mates y selección de jugadas.

```powershell
.\.venv\Scripts\python.exe tools/explain_analysis.py --analysis data/analysis/partida.json --game 1 --ply 17 --question "¿Qué cambia con c3c4?" --engine build/Release/chessbot.exe --depth 5
```

Si la jugada preguntada no estaba en MultiPV, la herramienta realiza una búsqueda restringida y añade esa evidencia. Sin `--llm-command` genera la explicación local determinista; con esa opción envía el contexto JSON a cualquier proceso local compatible.

## Aprendizaje y comparación de versiones

La mejora automática ajusta pesos del evaluador manual o entrena redes pequeñas con acumuladores NNUE. La búsqueda sigue siendo alfa-beta.

```text
Autojuego y partidas externas
    → posiciones filtradas y datasets versionados
    → ajuste de parámetros o entrenamiento de red
    → candidato
    → pruebas, benchmark, táctica y partidas contra la referencia
    → promoción o rechazo
```

Cada experimento guarda versiones, commit, configuración, semilla, límites, compilador y hardware. Los informes comparan victorias, tablas y derrotas, estimación Elo e incertidumbre, rendimiento y regresiones. Una menor pérdida de entrenamiento o más nodos por segundo no bastan para promover un candidato.

El ciclo completo se lanza con una configuración versionada. El directorio de salida debe ser nuevo para que una ejecución anterior nunca se sobrescriba:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[training]"
.\.venv\Scripts\python.exe tools/learning_cycle.py `
  --config data/training/phase10-config-v1.json `
  --engine build/Release/chessbot.exe `
  --output-dir build/learning-20260915
```

La promoción solo ocurre cuando todas las puertas pasan. Cada ejecución conserva `config.json`, dataset, checkpoint, red, partidas, decisión y `manifest.json` con comandos, versiones, entorno y SHA-256. GitHub Actions mantiene este trabajo largo en `learning.yml`, separado del CI rápido.

La evaluación manual acepta parámetros externos mediante `EvalFile`. `tools/generate_dataset.py` crea CSV/Parquet con particiones por partida; `tools/tune_eval.py` ajusta multiplicadores; `tools/train_nnue.py` entrena y exporta una red cuantizada; y `tools/evaluate_candidate.py` comprueba corrección, táctica, rendimiento y fuerza. `tools/learning_cycle.py` une todas las etapas con presupuestos y un manifiesto de artefactos. Véase [docs/learning.md](docs/learning.md). Los primeros candidatos HCE y NNUE fueron rechazados, por lo que la referencia estable permanece activa.

## Organización del repositorio terminado

```text
ChessBot/
├── CMakeLists.txt
├── specs.md
├── roadmap.md
├── readme.md
├── src/
│   ├── main.cpp
│   ├── board/        # Bitboards, reglas, movimientos y Zobrist
│   ├── search/       # Alfa-beta, ordenación, TT y tiempo
│   ├── eval/         # Evaluación manual, NNUE y desglose
│   ├── engine/       # API, límites y resultados
│   ├── protocol/     # UCI
│   └── openings/     # Libro y base de aperturas
├── tests/            # Reglas, PERFT, búsqueda y regresiones
├── tools/            # Scripts Python de análisis y experimentos
├── data/
│   ├── games/
│   ├── training/
│   ├── benchmarks/
│   ├── openings/
│   ├── engine_matches/
│   └── networks/
└── docs/             # Arquitectura, evaluación, búsqueda y aprendizaje
```

Ya están disponibles `compare_engines.py`, `match_runner.py`, `analyze_pgn.py`, `explain_analysis.py`, `generate_dataset.py`, `tune_eval.py`, `train_nnue.py`, `evaluate_candidate.py` y `learning_cycle.py`.

FEN se usa para posiciones; PGN con metadatos JSON, para partidas; y CSV/Parquet o shards binarios opcionales, para entrenamiento. El binario, la búsqueda, el evaluador, el libro, las redes y los datasets se versionan de forma independiente.

## Calidad y alcance

La validación incluye PERFT, invariantes, restauración de posiciones, coherencia Zobrist, tácticas, protocolo UCI y regresiones. El CI ejecuta compilación, pruebas, sanitizadores compatibles, formato y un benchmark pequeño; las campañas largas de fuerza se ejecutan por separado.

El modo determinista permite reproducir resultados bajo una configuración controlada, inicialmente monohilo y con límite de nodos. Los cambios se aceptan por mejoras verificables en corrección, fuerza, análisis, velocidad, memoria o explicabilidad.

El objetivo es un motor correcto, observable y ampliable. No se promete una cifra Elo ni fuerza equivalente a Stockfish. La búsqueda distribuida, búsqueda en GPU, multihilo real y Syzygy integrado quedan fuera del alcance actual.

La definición técnica completa está en [specs.md](specs.md), y las tareas y criterios de aceptación están en [roadmap.md](roadmap.md).
