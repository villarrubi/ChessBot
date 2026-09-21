# Contribuir a ChessBot

Prepara el entorno siguiendo [docs/development.md](docs/development.md). Mantén las reglas y la búsqueda en C++; las herramientas Python orquestan procesos UCI y la interfaz Windows consume esos resultados.

## Proponer un cambio

Describe el problema, el comportamiento esperado y cómo reproducirlo. Para un fallo ajedrecístico incluye FEN o PGN, límite de búsqueda, opciones del motor y versión utilizada. Evita adjuntar rutas personales, credenciales o partidas privadas sin revisarlas.

En una contribución de código, explica el cambio y las pruebas ejecutadas. Añade una regresión cuando corrijas un error de reglas, puntuación, análisis o entrenamiento. Actualiza la guía de uso correspondiente si cambia la interfaz o un argumento de consola.

## Comprobaciones

```powershell
.\.venv\Scripts\cmake.exe --build build --config Release --parallel
.\.venv\Scripts\ctest.exe --test-dir build -C Release --output-on-failure
.\.venv\Scripts\python.exe tools/test_analysis.py --engine build/Release/chessbot.exe
.\.venv\Scripts\python.exe tools/test_analysis_session.py --engine build/Release/chessbot.exe
.\.venv\Scripts\python.exe tools/test_explainer.py
.\.venv\Scripts\ruff.exe check tools
.\.venv\Scripts\python.exe tools/check_format.py --clang-format .venv/Scripts/clang-format.exe
dotnet build launcher/ChessBotLauncher.csproj -c Release
dotnet run --project tests/launcher/ChessBotLauncher.Tests.csproj -c Release -- .
```

Las pruebas del adaptador de IA usan respuestas simuladas y no requieren instalar un modelo ni conectarse a Internet. La prueba de interfaz requiere Windows y el motor/Python del entorno local. Consulta la guía de desarrollo para Linux y las suites de partidas y entrenamiento.

No añadas al repositorio modelos descargados de Ollama, credenciales, entornos virtuales ni resultados de campañas locales. Los candidatos pequeños y configuraciones ya versionados forman parte de los ejemplos reproducibles. Los cambios de fuerza deben acompañarse de resultados comparables; no promociones una red solo porque haya terminado de entrenar.
