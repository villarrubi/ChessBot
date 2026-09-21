# ChessBot

Motor de ajedrez en C++20 con una aplicación de Windows para jugar, analizar partidas y experimentar con aprendizaje automático. El motor implementa sus propias reglas y búsqueda; las herramientas Python organizan el análisis y el entrenamiento.

## Qué puedes hacer

- **Jugar** contra ChessBot o un ejecutable UCI de Stockfish desde el tablero.
- **Analizar** un PGN, una posición FEN o la partida actual; recorrer jugadas, comparar alternativas y consultar evaluaciones y variantes.
- **Preguntar por una jugada** con una IA local de Ollama, apoyada en cálculos del motor. Hay explicaciones básicas disponibles sin modelo.
- **Entrenar** evaluadores manuales y redes pequeñas de tipo NNUE, generar partidas y contrastar candidatos antes de promoverlos.
- **Usar UCI** desde otra interfaz de ajedrez o ejecutar partidas reproducibles contra motores externos.

Es un proyecto experimental: no hay una fuerza Elo certificada. La evaluación manual es la referencia predeterminada; las redes incluidas son candidatos de experimentos, no mejoras de fuerza demostradas. Las limitaciones y resultados se describen en la [documentación](docs/README.md).

## Empezar en Windows

Necesitas Python 3.12 o posterior, Visual Studio con las herramientas de C++ y Windows SDK, y el SDK de .NET 9 para compilar la interfaz. Desde la raíz del repositorio:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\cmake.exe -S . -B build -A x64
.\.venv\Scripts\cmake.exe --build build --config Release --parallel
.\.venv\Scripts\ctest.exe --test-dir build -C Release --output-on-failure
.\tools\build_launcher.ps1
```

El último paso genera `build/launcher/ChessBot Launcher.exe` y un acceso directo **ChessBot** en el escritorio. Necesitas el runtime de escritorio .NET 9 para ejecutarlo; el SDK ya lo incluye. La aplicación usa el motor de `build/Release` y el Python de `.venv` de este repositorio.

La pestaña **Análisis** permite importar un PGN o pegar una FEN. La partida aparece desde el inicio, abierta en la última jugada y con el movimiento resaltado. Evaluaciones y variantes llegan en directo; seleccionar una fila pendiente le da prioridad. Puedes recorrer una variante, volver a la partida y desplegar su gráfico de evaluación. **Cancelar** conserva los resultados parciales. Cuando una fila está completa, pulsa **Explicar / preguntar** para obtener un comentario. En **Alternativa** puedes escribir `Nf3` o `g1f3` para que el motor evalúe esa jugada antes de responder. Los resultados se guardan en `data/analysis/` y se abren con **Resultados**.

Para entrenar redes, instala además las dependencias opcionales:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[training]"
```

Las instrucciones de Linux, Debug y sanitizadores están en la [guía de desarrollo](docs/development.md). El motor y las herramientas Python son multiplataforma; la interfaz WinForms requiere Windows.

## IA local opcional

Instala [Ollama](https://ollama.com/download) y descarga un modelo local:

```powershell
ollama pull qwen3.5:9b
```

Mantén Ollama en ejecución y pulsa **Detectar IA** en Análisis. La selección automática prefiere `qwen3.5:9b`, después `qwen3.5:4b` y, si no están, otro modelo local instalado. Puedes elegir uno explícitamente. El modelo de 9B ocupa aproximadamente 6,6 GB descargado; la memoria de ejecución depende del contexto y del equipo.

El adaptador se conecta a `127.0.0.1:11434`, excluye modelos remotos y no descarga modelos durante un análisis. El motor calcula; la IA redacta y puede equivocarse: las puntuaciones y variantes verificables permanecen en **Cálculos del motor**. Si Ollama falla, se muestra el motivo y una explicación básica. [Configuración y uso](docs/analysis.md).

## Motor por consola

```powershell
.\build\Release\chessbot.exe inspect --moves "e2e4 e7e5"
.\build\Release\chessbot.exe eval --moves "e2e4 e7e5"
.\build\Release\chessbot.exe bench 5
```

Sin argumentos, el ejecutable inicia UCI. Una sesión mínima es:

```text
uci
isready
position startpos moves e2e4 e7e5
go depth 4
quit
```

Espera `uciok`, `readyok` y `bestmove` antes de continuar cada paso. El motor empieza con un hilo, 64 MB de hash, evaluación `Positional`, búsqueda `Baseline`, libro y NNUE desactivados. Consulta el [protocolo y desarrollo](docs/development.md) para las opciones.

## Documentación

| Guía | Contenido |
| --- | --- |
| [Análisis y asistente](docs/analysis.md) | PGN, FEN, alternativas, perspectiva y Ollama |
| [Desarrollo](docs/development.md) | Instalación, compilación, pruebas y UCI |
| [Arquitectura](docs/architecture.md) | Módulos y contratos del motor |
| [Evaluación](docs/evaluation.md) y [búsqueda](docs/search.md) | Componentes, perfiles y límites |
| [Aperturas y partidas](docs/openings-and-matches.md) | Rivales UCI y experimentos reproducibles |
| [Aprendizaje](docs/learning.md) | Datasets, HCE, NNUE y promoción |
| [Validación](docs/validation.md) | Resultados fechados y alcance de las pruebas |
| [Roadmap](roadmap.md) | Estado actual y trabajo pendiente |

Para contribuir, consulta [CONTRIBUTING.md](CONTRIBUTING.md). Los modelos de Ollama, motores rivales, datasets generados y binarios se obtienen o generan por separado. Las dependencias de terceros conservan sus propias licencias; doctest incluye la suya en `third_party/doctest/`.
