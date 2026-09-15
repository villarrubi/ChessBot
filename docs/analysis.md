# Análisis de partidas y explicaciones

La fase 6 incorpora un flujo local que convierte PGN en tres artefactos: JSON versionado, PGN anotado y un informe Markdown. Usa UCI para la búsqueda y la orden de diagnóstico `chessbot eval` para el desglose estático; los datos propios no alteran la sintaxis de las líneas UCI estándar.

## Analizar un PGN

```powershell
.\.venv\Scripts\python.exe tools/analyze_pgn.py `
  --input partida.pgn `
  --engine build/Release/chessbot.exe `
  --depth 5 `
  --multipv 3 `
  --json data/analysis/partida.json `
  --annotated-pgn data/analysis/partida-anotada.pgn `
  --report data/analysis/partida.md
```

Puede sustituirse `--depth` por `--movetime-ms` o `--nodes`. `--max-plies` limita una prueba. Para un motor externo que no implemente la consola de ChessBot se utiliza `--no-static`; se mantienen puntuaciones, candidatos y PV, pero los desgloses quedan vacíos.

Por cada movimiento se busca MultiPV desde la posición anterior y se repite la búsqueda restringida a la jugada disputada mediante `searchmoves`. Ambas usan el mismo límite y la perspectiva del jugador que movió. El JSON conserva:

- FEN antes/después, historial SAN/UCI, color, ply y cabeceras PGN.
- Mejor jugada, jugada disputada, candidatos, puntuación, profundidad, nodos, tiempo y PV.
- Pérdida en centipeones cuando ambas puntuaciones son normales.
- Distancia y cambio de mate por separado; un mate no se convierte silenciosamente en centipeones.
- Evaluación estática antes/después desde la perspectiva del jugador y todos sus componentes.
- Clasificación mediante umbrales configurables: `--inaccuracy 50`, `--mistake 100` y `--blunder 200` por defecto.

El PGN anotado añade evaluación, pérdida, mejor jugada y una PV breve a cada nodo principal. El Markdown ofrece una tabla por partida. El campo `schema_version` permite evolucionar el JSON sin adivinar su estructura.

## Explicar y preguntar

```powershell
.\.venv\Scripts\python.exe tools/explain_analysis.py `
  --analysis data/analysis/partida.json `
  --game 1 --ply 17 `
  --question "¿Qué cambia con c3c4?" `
  --engine build/Release/chessbot.exe `
  --depth 5
```

Sin LLM, el explicador relaciona clasificación, pérdida, puntuaciones, PV y los tres cambios estáticos principales. Si la pregunta nombra una jugada UCI ausente de los candidatos, exige `--engine`, comprueba su legalidad y ejecuta una búsqueda restringida antes de responder. `--context-output` guarda toda la evidencia usada.

`--llm-command "programa argumentos"` conecta opcionalmente cualquier proceso local. El adaptador envía un objeto JSON por entrada estándar con la pregunta, FEN, historial, candidatos, PV, componentes y búsqueda adicional. Incluye la instrucción de separar cálculos de interpretación y de no afirmar tácticas forzadas sin mate o PV que las respalde. La salida del programa se imprime como respuesta; el flujo básico no necesita ningún modelo.

## Verificación

`tools/test_analysis.py` analiza una partida de muestra, valida el esquema JSON, reproduce el PGN anotado, comprueba el informe y formula una pregunta que obliga a calcular una variante nueva. Se ejecuta en Release dentro de la matriz CI.
