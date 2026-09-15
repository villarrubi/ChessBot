# Arquitectura actual

Las fases 0–6 implementan una biblioteca `chessbot_core`, un motor UCI monohilo, una consola de diagnóstico, análisis PGN y explicaciones basadas en evidencias. Aperturas y aprendizaje pertenecen a fases posteriores.

## Dependencias y módulos

- `board/types.h`, `bitboard.h` y `move.*`: convenciones, operaciones de bits y movimientos compactos.
- `board/attack_tables.*`: tablas inmutables de ataques; las piezas deslizantes usan PEXT/BMI2 o un índice compatible por software.
- `board/board.*`: FEN, estado, ataques recibidos, hacer/deshacer, historial y terminación.
- `board/movegen.*`: listas fijas internas, movimientos pseudolegales, filtrado de legalidad y PERFT/divide.
- `board/zobrist.*`: claves de 64 bits reproducibles mediante una semilla fija de SplitMix64.
- `eval/evaluation.*`: perfiles básico/posicional, interpolación de fase y desglose.
- `search/`: alfa-beta/PVS, MultiPV, quietud, heurísticas, tabla de transposición y tiempo.
- `engine/`: API estable, límites, resultados, configuración y parada.
- `protocol/uci.*`: protocolo asíncrono y salida sincronizada.
- `main.cpp`: entrada UCI, diagnóstico JSON y benchmark.
- `tools/`: validación, partidas, análisis PGN y explicaciones mediante python-chess. El núcleo no enlaza Python ni motores externos.

`Board` mantiene doce bitboards, ocupación por color y un array de piezas por casilla. El array permite consultar capturas y serializar FEN sin recorrer todos los bitboards. Las mutaciones actualizan las tres representaciones; las aserciones Debug comprueban su coherencia.

`StateInfo` guarda lo necesario para deshacer una jugada o un pase de null-move: hash, derechos, en passant, relojes, pieza capturada y tamaño del historial. El motor no copia el tablero en cada nodo. Las pruebas sí guardan copias completas como referencia independiente para comprobar la restauración.

## Contratos y convenciones

- `a1 = 0`, `b1 = 1`, `h8 = 63`; blancas avanzan sumando ocho.
- `Move` ocupa 32 bits y codifica origen, destino, promoción, flags, pieza movida y capturada. Su texto usa coordenadas UCI, por ejemplo `e2e4` o `a7a8n`.
- `makeMove` es una operación interna: acepta movimientos generados para la posición actual. No valida entradas arbitrarias. `playUci` comprueba la jugada contra la lista legal y rechaza entradas inválidas sin alterar el tablero.
- El estado no se modifica directamente desde el exterior. `fromFen` construye una posición validada y `playUci` conserva su historial.
- `legalMoves` hace/deshace candidatos y descarta los que dejan al rey propio en jaque. El enroque comprueba además casillas libres y ausencia de ataque en origen, tránsito y destino.
- PERFT cuenta secuencias legales, sin terminar por repetición, cincuenta movimientos o material insuficiente. Profundidad cero devuelve un nodo; divide necesita profundidad positiva.
- Los ataques cuentan incluso piezas clavadas: una casilla atacada por una pieza clavada sigue estando prohibida para el rey contrario.
- No hay estado global mutable del motor. Las tablas compartidas se inicializan una vez y son constantes.

## FEN y validación

Se exigen seis campos y ocho filas completas. Se rechazan símbolos inválidos, reyes ausentes o duplicados, reyes adyacentes, peones en primera/última fila, exceso de piezas, promociones incompatibles con los peones disponibles, derechos de enroque inconsistentes, más de dos jaques simultáneos y jaque al bando que acaba de mover.

La casilla en passant requiere el peón que hizo el doble avance, destino y origen vacíos, fila correcta y reloj de medias jugadas a cero. Se admite una casilla FEN en passant aunque no haya capturador, y se conserva al serializar.

Los contadores de entrada se limitan a `0..1.000.000.000` y `1..1.000.000.000`; internamente usan enteros de 64 bits. La validación detecta incoherencias estructurales y legales locales, pero no realiza una demostración retrógrada de que una posición arbitraria sea alcanzable desde el inicio.

## Hash y repetición

El hash incluye piezas, turno, derechos de enroque y archivo en passant **solo si existe una captura en passant legal**. Una captura impedida por clavada o por jaque descubierto no cambia la identidad de repetición. Los relojes no forman parte del hash.

Las piezas, derechos, turno y en passant actualizan el hash incrementalmente. `recomputeKey` ofrece una referencia completa que se contrasta tras las mutaciones en Debug y en pruebas.

Una FEN crea un historial con una única posición. Para detectar repeticiones anteriores se carga la FEN de origen y se reproducen las jugadas; el historial perdido no puede deducirse de la FEN final. `Board` conserva las claves al jugar y restaura la longitud del historial al deshacer.

La detección cuenta tres apariciones de la posición actual dentro del tramo reversible disponible. Usa claves Zobrist de 64 bits; comparte la limitación probabilística de colisión de este esquema.

## Política de tablas

`status(true)` comprueba, por orden: mate/ahogado, material insuficiente, triple repetición actual y reloj de al menos 100 medias jugadas. `status(false)` omite las dos condiciones reclamables. La consola utiliza `true`.

La implementación detecta una reclamación ya disponible en la posición actual. No predice la posibilidad de reclamar anunciando la próxima jugada. El historial se debe conservar durante una partida. Mate tiene prioridad sobre la regla de cincuenta movimientos.

Material insuficiente cubre rey contra rey, rey y alfil/caballo contra rey y posiciones con solo reyes y alfiles que circulan por casillas del mismo color. No declara automáticamente tablas con dos caballos contra rey ni con alfiles de colores opuestos. No se implementa una prueba general de todas las posiciones muertas ni arbitraje adicional de cinco repeticiones/75 movimientos en esta fase.

## Puntuaciones de búsqueda

`Score` es entero: 100 centipeones equivalen a un peón. La búsqueda usa perspectiva del bando al turno; al pasar al oponente se invierte el signo. `ScoreDraw = 0`, `ScoreMate = 32000`, `ScoreInfinity = 32767`, `MaxPly = 128`.

Un mate favorable usa `ScoreMate - ply`; uno desfavorable, `-ScoreMate + ply`. Así se prefiere dar mate antes y retrasar el mate propio. UCI convierte estas puntuaciones a `score mate N`; las demás se publican como centipeones.

## Decisiones de esta entrega

- CMake y CTest para construcción y ejecución; doctest 2.4.12 incluido con su licencia para que las pruebas C++ no necesiten descargas.
- Tablas de subconjuntos de ocupación para deslizantes, con selección PEXT en tiempo de ejecución y alternativa por software.
- `MoveList` fijo dentro de búsqueda y vectores en las fronteras públicas donde simplifican la interoperabilidad.
- Consola de diagnóstico y protocolo UCI comparten el ejecutable, pero tienen entradas separadas: sin argumentos se inicia UCI.
- Búsqueda monohilo determinista con perfiles `Baseline`/`Optimized`; el hilo asíncrono pertenece al adaptador UCI.
- UCI transporta búsqueda y MultiPV; la consola `eval` transporta el desglose JSON que consumen las herramientas de análisis.

La referencia externa de las comprobaciones diferenciales es la [API oficial de python-chess](https://python-chess.readthedocs.io/en/latest/core.html). El uso de FEN con en passant explícito y la comparación de repetición actual se ajustan a esos contratos.
