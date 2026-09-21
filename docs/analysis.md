# Análisis y explicaciones

ChessBot separa tres tareas: el motor calcula jugadas y puntuaciones; Python organiza esa evidencia; un modelo local opcional la explica en español. El LLM no selecciona la jugada del motor ni modifica sus evaluaciones.

## Pestaña Análisis

1. **Importar PGN** abre y analiza un archivo, o pega el texto y pulsa **Analizar**. Un archivo puede contener varias partidas; el selector superior permite cambiar de partida.
2. Para una posición, selecciona **FEN**, pega sus seis campos y pulsa **Analizar**. **Partida actual** toma una copia del historial de Jugar; una partida aún sin jugadas analiza la posición inicial.
3. Elige profundidad, número de variantes e hilos. La profundidad admite hasta el máximo técnico de la búsqueda (126); las variantes pueden llegar a todas las jugadas legales (256 como máximo técnico). Análisis usa el perfil de búsqueda optimizado, una tabla hash de 256 MB y por defecto hasta ocho hilos. El estado muestra la profundidad alcanzada dentro de cada jugada. En la máquina de validación, la posición inicial con una variante y profundidad 20 tardó 33,1 s; cada variante adicional y cada jugada de una partida aumentan el trabajo. **Cancelar** interrumpe Python y sus procesos de motor sin bloquear la interfaz.
4. Selecciona una fila o usa las flechas. El tablero muestra por defecto la posición posterior a la jugada seleccionada, de modo que una fila como `16…f6` ya refleja `f6`. Desmarca **Después de la jugada** para ver la posición anterior. La FEN inferior se puede copiar y **Girar** cambia la orientación.
5. Pulsa **Gráfico de evaluación** para desplegar la evolución de la evaluación durante la partida. Se expresa desde la perspectiva de blancas: positivo favorece a blancas y negativo a negras; el punto seleccionado queda resaltado.
6. **Cálculos del motor** muestra clasificación, pérdida, variantes SAN y componentes estáticos. **Explicar / preguntar** genera un comentario sobre la fila seleccionada.

El análisis usa ChessBot con evaluación manual y sin libro. No hereda el Elo de un rival Stockfish de la pestaña Jugar ni carga automáticamente una red entrenada. Una FEN aislada no contiene las repeticiones anteriores; la opción Partida actual conserva el historial disponible. Una posición terminal se muestra sin inventar una jugada recomendada.

Cada ejecución crea una carpeta en `data/analysis/` con la petición, `analysis.json`, `report.md` y, para partidas, `annotated.pgn`. **Resultados** abre esa carpeta. Las preguntas guardan la última respuesta en `explanation.json` y su evidencia en `explanation-context.json`. Estos archivos se quedan en tu equipo y están excluidos de Git.

## IA con Ollama

Instala [Ollama](https://ollama.com/download) y descarga un modelo antes de utilizarlo:

```powershell
ollama pull qwen3.5:9b
```

El [catálogo oficial de Qwen 3.5](https://ollama.com/library/qwen3.5) publica tamaños y variantes. La descarga de 9B ocupa aproximadamente 6,6 GB; la de 4B, 3,4 GB. Se necesita memoria adicional para ejecutarlos. GPU es opcional y la latencia depende del hardware.

En Windows, deja Ollama abierto; si solo usas la CLI, inicia `ollama serve`. Pulsa **Detectar IA** para listar modelos locales. **Automático** prefiere 9B y después 4B; también puedes seleccionar un modelo instalado. **Solo motor** produce una explicación determinista sin LLM.

El adaptador usa [la API local de chat](https://docs.ollama.com/api/chat) en `http://127.0.0.1:11434`, sin proxy ni proveedor de nube. Filtra modelos remotos; no descarga ni instala nada al explicar. Si el servicio, modelo o respuesta fallan, vuelve a la explicación del motor e indica el motivo. El tiempo de espera de una respuesta es de 120 segundos.

Las instrucciones del modelo exigen no inventar puntuaciones, piezas, variantes o mates y distinguir cálculo de interpretación. Esto reduce errores, pero no verifica todas las afirmaciones del texto generado. Contrasta las respuestas con Cálculos del motor; una PV es una continuación calculada, no una prueba de que cada jugada sea forzada.

## Preguntar por alternativas

Escribe una pregunta y, si quieres comparar otra jugada, indícala en **Alternativa** con notación SAN (`Nf3`) o UCI (`g1f3`). La jugada se valida en la posición anterior a la fila seleccionada. Si no estaba calculada, se ejecuta `searchmoves` con el historial, opciones y límite originales antes de enviarla al modelo. Las preguntas que contienen una jugada UCI también se reconocen.

Cada pregunta es independiente. No hay memoria conversacional ni cálculo automático de líneas arbitrarias descritas solo en lenguaje natural. Para esos casos, especifica la alternativa o analiza otra FEN.

## Cómo leer las puntuaciones

- 100 centipeones equivalen a un peón. La búsqueda y los componentes antes/después se expresan desde la perspectiva del jugador que mueve en la fila: positivo le favorece. Esta perspectiva cambia al pasar de una fila blanca a una negra.
- La pérdida compara la mejor alternativa con la jugada realizada. Los umbrales iniciales son 50/100/200 cp para imprecisión/error/error grave; pérdidas de hasta 10 cp se etiquetan como buenas. Son criterios orientativos y dependen de la búsqueda.
- Los mates se conservan separados de los centipeones. Un mate ya inevitable no se atribuye automáticamente a la última jugada como un nuevo error.
- El desglose estático evalúa la posición inmediata. Sus deltas no son una descomposición del resultado de la búsqueda. Con NNUE, los componentes HCE son auxiliares, no una explicación exacta de la red.

También se calcula el desglose estático tras la mejor alternativa (`static_best_after`), separado del de la jugada realizada, para evitar atribuir a una posición los componentes de otra.

## Consola

```powershell
.\.venv\Scripts\python.exe tools/analyze_pgn.py `
  --input tests/positions/analysis_sample.pgn `
  --engine build/Release/chessbot.exe --depth 4 --multipv 3 `
  --json data/analysis/sample.json `
  --annotated-pgn data/analysis/sample.pgn `
  --report data/analysis/sample.md

.\.venv\Scripts\python.exe tools/explain_analysis.py `
  --analysis data/analysis/sample.json --game 1 --ply 1 `
  --question "¿Qué cambia con esta alternativa?" --move h4 `
  --engine build/Release/chessbot.exe --provider auto
```

`--provider none` es el valor predeterminado de la CLI. `auto` y `ollama` intentan usar Ollama y conservan el fallback; `--model` elige un modelo local. `--json-output` guarda texto, origen y posible aviso; `--context-output` conserva la evidencia. El adaptador anterior `--llm-command` sigue disponible para un proceso local que lea JSON en stdin, con un límite de 120 segundos.

El analizador admite `--movetime-ms` o `--nodes` en lugar de profundidad; `--max-plies` limita la partida. Con motores externos usa `--no-static`; `--nnue-file` activa una red ChessBot para búsqueda y diagnósticos. Los artefactos JSON tienen `schema_version: 1`, cabeceras, FEN inicial y antes/después, historial, candidatos, profundidad, PV y evaluación. Los JSON antiguos sin FEN inicial no permiten reconstruir todo el historial en búsquedas adicionales.

`tools/analysis_session.py` es el puente de la interfaz. Acepta `--request`, `--engine` y `--output-dir`; la petición JSON contiene `kind` (`pgn`, `fen` o `game`), `text`, `moves` (UCI para `game`), `depth`, `multipv` y `threads`. Si la jugada realizada ya está entre las variantes calculadas, se reutiliza ese resultado en vez de repetir la búsqueda.

## Verificación

`test_analysis.py` valida los artefactos PGN/JSON/Markdown y una búsqueda adicional. `test_analysis_session.py` cubre FEN, terminales, historial, SAN y numeración desde una FEN personalizada. `test_explainer.py` cubre mates, perspectiva, contexto y respuestas del adaptador sin requerir un modelo. La prueba WinForms de `tests/launcher/` comprueba navegación, tablero, explicación y cancelación, y genera capturas en `build/launcher-qa/`.
