# Desarrollo y validación

## Preparación en Windows

Se necesita Visual Studio con las herramientas de escritorio C++ y Windows SDK, además de Python 3.12+. Estos comandos no requieren activar scripts PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\cmake.exe -S . -B build -A x64 -DCHESSBOT_SLOW_TESTS=ON
.\.venv\Scripts\cmake.exe --build build --config Release --parallel
.\.venv\Scripts\ctest.exe --test-dir build -C Release --output-on-failure
```

CMake detecta la instalación de Visual Studio. La validación histórica utilizó Visual Studio 2026 y CMake 4.4.3. Un CMake antiguo puede no reconocer generadores de Visual Studio posteriores.

```powershell
.\.venv\Scripts\cmake.exe --build build --config Debug --parallel
.\.venv\Scripts\ctest.exe --test-dir build -C Debug -LE slow --output-on-failure
.\.venv\Scripts\python.exe tools/validate_rules.py --engine build/Release/chessbot.exe --games 80 --plies 200
.\.venv\Scripts\python.exe tools/test_cli.py --engine build/Release/chessbot.exe
.\.venv\Scripts\python.exe tools/test_uci.py --engine build/Release/chessbot.exe
.\.venv\Scripts\python.exe tools/test_analysis.py --engine build/Release/chessbot.exe
.\.venv\Scripts\python.exe tools/test_match_runner.py --engine build/Release/chessbot.exe
.\.venv\Scripts\python.exe tools/test_tuning.py --engine build/Release/chessbot.exe
.\.venv\Scripts\python.exe tools/test_nnue.py --engine build/Release/chessbot.exe
.\.venv\Scripts\python.exe tools/check_format.py --clang-format .venv/Scripts/clang-format.exe
.\.venv\Scripts\ruff.exe check tools
```

El modificador `--fix` de `check_format.py` aplica el formato. Solo procesa C++ propio y excluye el código de terceros. El paquete del formateador está fijado a 21.1.8 para evitar diferencias entre máquinas.

## Preparación en Linux

Con compilador C++20 y CMake instalados:

```bash
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DCHESSBOT_SLOW_TESTS=ON
cmake --build build --parallel
ctest --test-dir build --output-on-failure
python tools/validate_rules.py --engine build/chessbot
python tools/test_cli.py --engine build/chessbot
python tools/test_uci.py --engine build/chessbot
python tools/test_analysis.py --engine build/chessbot
python tools/test_match_runner.py --engine build/chessbot
python tools/test_tuning.py --engine build/chessbot
python tools/test_nnue.py --engine build/chessbot
python tools/check_format.py
ruff check tools
```

## Sanitizadores

GCC/Clang utilizan AddressSanitizer y UndefinedBehaviorSanitizer:

```bash
cmake -S . -B build-sanitize -DCMAKE_BUILD_TYPE=Debug -DCHESSBOT_SANITIZERS=ON
cmake --build build-sanitize --parallel
ctest --test-dir build-sanitize --output-on-failure
```

En MSVC la opción activa AddressSanitizer. Requiere instalar el componente de sanitizador C++ correspondiente a la arquitectura del compilador. Ejemplo:

```powershell
.\.venv\Scripts\cmake.exe -S . -B build-asan -A x64 -DCHESSBOT_SANITIZERS=ON
.\.venv\Scripts\cmake.exe --build build-asan --config RelWithDebInfo --parallel
.\.venv\Scripts\ctest.exe --test-dir build-asan -C RelWithDebInfo --output-on-failure
```

Si falta `clang_rt.asan_dynamic_runtime_thunk-x86_64.lib`, instala el componente ASan de MSVC antes de compilar esta configuración. El workflow incluye una comprobación ASan/UBSan en Linux.

## Consola disponible

```powershell
.\build\Release\chessbot.exe --help
.\build\Release\chessbot.exe inspect
.\build\Release\chessbot.exe legal --moves "e2e4 e7e5"
.\build\Release\chessbot.exe inspect --moves "e2e4 e7e5 g1f3"
.\build\Release\chessbot.exe eval --moves "e2e4 e7e5 g1f3"
.\build\Release\chessbot.exe bench 5
.\build\Release\chessbot.exe perft 6
.\build\Release\chessbot.exe divide 3
.\build\Release\chessbot.exe perft 3 --fen "4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 2"
```

`inspect` devuelve JSON con FEN, hash, jaque, repetición, material insuficiente, estado y jugadas legales ordenadas. `legal` imprime una jugada por línea. `perft` imprime el total y `divide` lo separa por jugada de raíz. La profundidad de consola admite `0..10`; divide requiere al menos 1.

`validate-stream` admite una petición por línea: `FEN`, opcionalmente un tabulador y una secuencia de jugadas UCI separadas por espacios. Devuelve un JSON por petición y continúa tras errores. Esta interfaz permite comparar muchas posiciones sin arrancar un proceso por posición.

`features-stream` usa el mismo transporte y devuelve Zobrist, turno, versión de evaluación y todos los componentes. Acepta `--eval-file FILE` y permite generar datasets sin arrancar un proceso por posición.

Las órdenes de diagnóstico inválidas devuelven código 2 y un mensaje por stderr. La notación de las jugadas es UCI.

## Motor UCI

Ejecutar `chessbot.exe` sin argumentos inicia el protocolo. Admite `uci`, `isready`, `ucinewgame`, `position startpos`, `position fen`, `go`, `stop`, `quit` y `setoption`. La búsqueda acepta profundidad, nodos, tiempo fijo, relojes con incremento, movimientos restantes e infinito. Se ejecuta en un hilo de trabajo para responder a `stop` e `isready`.

```text
uci
setoption name Hash value 64
setoption name Evaluation value Positional
setoption name SearchProfile value Optimized
setoption name MultiPV value 3
isready
position startpos moves e2e4 e7e5 g1f3
go movetime 1000
```

El comando de depuración `eval` devuelve en una línea `info string` la evaluación estática y sus componentes desde la perspectiva del bando al turno. `AnalysisDetail=Full` añade métricas de búsqueda. El analizador usa `MultiPV` y `go searchmoves`, que sí pertenecen al flujo UCI, y consume el desglose mediante la consola JSON separada.

El runner reproducible se ejecuta así:

```powershell
.\.venv\Scripts\python.exe tools/match_runner.py --engine-a build/Release/chessbot.exe --engine-b build/Release/chessbot.exe --games 16 --depth 3 --openings data/openings/core.json --color-mode paired --output-dir data/engine_matches/comparison
```

Admite límites de profundidad, nodos o tiempo, relojes completos, colores fijos o emparejados, FEN, líneas forzadas y suites JSON/PGN/EPD/FEN/UCI/Polyglot. Véanse [openings-and-matches.md](openings-and-matches.md) y [learning.md](learning.md).

El análisis PGN y su prueba integral se ejecutan así:

```powershell
.\.venv\Scripts\python.exe tools/analyze_pgn.py --input tests/positions/analysis_sample.pgn --engine build/Release/chessbot.exe --depth 3 --multipv 2 --json data/analysis/sample.json --annotated-pgn data/analysis/sample.pgn --report data/analysis/sample.md
.\.venv\Scripts\python.exe tools/test_analysis.py --engine build/Release/chessbot.exe
```

## Cobertura y CI

CTest ejecuta tipos, ataques, FEN, legalidad, terminales, hash, restauración aleatoria, PERFT, evaluación parametrizada, libro, tácticas, búsqueda, límites y tabla de transposición. `CHESSBOT_SLOW_TESTS=ON` añade profundidad 5/6 de la posición inicial como prueba etiquetada `slow`. Se excluye en Debug para mantener rápidas las aserciones de invariantes.

`validate_rules.py` verifica conjuntos completos de jugadas legales, FEN tras reproducir líneas, jaque, material insuficiente, repetición y terminación frente a python-chess. Incluye fixtures especiales y sus reflejos de color, más partidas aleatorias reproducibles. Contrasta también los totales PERFT mediante un recorrido independiente.

El workflow de GitHub Actions compila Debug/Release en Windows/Linux, comprueba formato, reglas, CLI, UCI, análisis, partidas, ajuste y equivalencia NNUE, y añade un job Linux de sanitizadores. `learning.yml` ejecuta por separado campañas manuales que instalan PyTorch y conserva sus artefactos.

Las dependencias de análisis y entrenamiento están declaradas como extras `analysis` y `training`, separadas del entorno básico. El análisis PGN usa la dependencia básica `python-chess`; PyTorch solo se instala para entrenar o probar el ciclo largo.

## Interfaz de Windows y análisis local

La interfaz requiere el SDK de .NET 9 para compilar y el runtime de escritorio de .NET 9 para ejecutar. `tools/build_launcher.ps1` publica en `build/launcher/` y crea el acceso directo del escritorio. Cierra esa instancia antes de republicar para evitar archivos bloqueados; el parámetro `-Destination` permite otra carpeta de salida.

```powershell
dotnet build launcher/ChessBotLauncher.csproj -c Release
dotnet run --project tests/launcher/ChessBotLauncher.Tests.csproj -c Release -- .
.\.venv\Scripts\python.exe tools/test_explainer.py
.\.venv\Scripts\python.exe tools/test_analysis_session.py --engine build/Release/chessbot.exe
```

La prueba WinForms requiere Windows, `build/Release/chessbot.exe` y `.venv/Scripts/python.exe`. Genera capturas en `build/launcher-qa/`. Las pruebas del adaptador usan respuestas simuladas; Ollama no es necesario para CI. Para comprobar la generación real, sigue [analysis.md](analysis.md).

Opciones UCI principales: `Hash`, `Threads`, `Move Overhead`, `SearchProfile`, `Evaluation`, `EvalFile`, `MultiPV`, `AnalysisDetail`, `OwnBook`, `BookFile`, `BookPolicy`, `BookSeed`, `NNUEFile` y `NNUE`. El comando `uci` devuelve los rangos y valores por defecto del binario compilado. Configura `NNUEFile` antes de activar `NNUE`; una red incluida puede ser un candidato rechazado, no la referencia de juego.
