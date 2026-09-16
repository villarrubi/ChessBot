# Aperturas y partidas reproducibles

`tools/match_runner.py` enfrenta dos ejecutables UCI locales. Cada motor admite su propia ruta,
nombre, opciones UCI, directorio de trabajo y variables de entorno. El runner valida las jugadas,
aplica el control de tiempo, registra los fallos y produce `games.pgn`, `metadata.json` y
`engine.log`.

Una comparación emparejada desde la suite de fuerza se ejecuta así:

```powershell
python tools/match_runner.py `
  --engine-a build/Release/chessbot.exe --name-a candidate `
  --engine-b build/Release/chessbot.exe --name-b reference `
  --options-a '{"EvalFile":"data/evaluation/hce-phase8-candidate-v1.params"}' `
  --options-b '{"EvalFile":"data/evaluation/hce-default-v1.params"}' `
  --openings data/openings/strength-v1.json --games 100 --depth 2 `
  --color-mode paired --seed 1 --output-dir data/engine_matches/experiment
```

Puede usarse `--nodes`, `--movetime-ms` o `--initial-ms` con `--increment-ms` en vez de
`--depth`. Los modos de color son `paired`, `alternate`, `a-white` y `a-black`. `--fen` parte de
una posición concreta; `--moves` añade un prefijo SAN o UCI exacto antes de liberar los motores.
`--opening-id` y `--opening-name` filtran una suite.

Las suites aceptadas son JSON nativo, PGN, EPD, listas FEN/UCI y libros Polyglot. Cada entrada se
normaliza a una FEN inicial y una lista UCI, con identificador, nombre, ECO, fuente y ply de
liberación. `data/openings/core.json` sirve para pruebas funcionales; `strength-v1.json` contiene
50 puntos de partida para comparaciones con mayor diversidad.

El libro nativo del motor es independiente del prefijo del runner. Se activa con estas opciones
UCI:

```text
setoption name BookFile value tests/positions/test_book.tsv
setoption name BookPolicy value weighted
setoption name BookSeed value 1
setoption name OwnBook value true
```

El formato TSV guarda por fila `FEN (cuatro campos)`, jugada UCI, peso, partidas, victorias,
tablas, derrotas, puntuación del motor y fuente. Una línea `# version=...` identifica el libro.
Las políticas disponibles son `best`, `weighted`, `random` y `explore`. Si no existe una entrada
legal, el motor busca normalmente. La línea `info string book` y los metadatos del runner guardan
la decisión y su procedencia.

Los intervalos de las partidas emparejadas se calculan sobre resultados agrupados por apertura.
Repetir una misma apertura no aumenta artificialmente el número de muestras independientes. El
SPRT opcional se configura con `--sprt-elo0`, `--sprt-elo1`, `--sprt-alpha` y `--sprt-beta`.

## Escalera de Elo contra Stockfish

El lanzador incluye **Medir Elo aproximado** en la pestaña Herramientas. Selecciona un ejecutable
UCI nativo de Stockfish, indica las partidas por nivel y la profundidad, y ejecuta la prueba. La
escalera usa los límites `UCI_LimitStrength` y `UCI_Elo` de Stockfish (1320–3190), juega cada nivel
con colores emparejados y guarda `summary.json`, `summary.csv` y una carpeta por nivel. La cifra
estimada suma el Elo configurado de Stockfish y la diferencia medida en la partida; el intervalo
de confianza se muestra junto al valor y suele ser amplio con pocas partidas.

También se puede ejecutar sin el lanzador:

```powershell
python tools/elo_ladder.py --engine build/Release/chessbot.exe `
  --stockfish C:\motores\stockfish\stockfish-windows-x86-64.exe `
  --games-per-level 16 --depth 3 --output-dir build/elo-ladder
```

La versión `.js/.wasm` de Stockfish que usa ChessPrep funciona dentro del navegador y no es un
ejecutable UCI nativo; para esta prueba hay que seleccionar el binario de Windows.
