# Evaluación manual y neuronal

El evaluador devuelve centipeones desde la perspectiva del bando al turno. Una puntuación positiva favorece a quien mueve. `tempo = +10` aplica siempre a ese bando; los demás componentes se calculan primero desde blancas y se invierten cuando juegan negras.

## Perfiles

- `Basic`: material, tablas de pieza-casilla y tempo. Conserva una referencia funcional equivalente a la fase 2.
- `Positional`: añade movilidad, peones, pasados, pareja de alfiles, torres, rey y espacio. Es el perfil predeterminado.

Se seleccionan mediante `setoption name Evaluation value Basic|Positional`. Cambiar el perfil limpia la tabla de transposición para impedir que una búsqueda reutilice puntuaciones del otro evaluador.

## Interpolación de fase

El material sin peones asigna 1 punto a caballo/alfil, 2 a torre y 4 a dama, hasta un máximo de 24. Cada término mantiene valores de medio juego y final y se interpola linealmente. La posición inicial tiene fase 24 y rey contra rey, fase 0.

Los valores materiales iniciales son 100/120 para peón, 320/305 para caballo, 330/325 para alfil, 500/510 para torre y 900 para dama (medio juego/final). El rey no tiene valor material.

## Componentes posicionales

- `pieceSquare`: centralización y avance por pieza, seguridad/actividad del rey según fase, piezas atrapadas, puestos avanzados y alfiles obstaculizados por peones del mismo color.
- `mobility`: destinos disponibles, destinos no controlados por peones y presión sobre piezas valiosas.
- `pawnStructure`: peones doblados, aislados, conectados, bloqueados/retrasados, islas y candidatos a pasados.
- `passedPawns`: bonus creciente por fila, conexión, apoyo, bloqueo, distancia de ambos reyes y torres propias o rivales detrás del peón.
- `bishopPair`: bonus distinto para medio juego y final.
- `rookActivity`: columnas abiertas o semiabiertas, séptima fila y conexión entre torres.
- `kingSafety`: escudo de peones, columnas abiertas próximas y ataques en la zona del rey, con más peso mientras hay damas y material.
- `space`: control de casillas centrales en campo rival.
- `tempo`: bonus fijo de 10 centipeones al bando al turno.

`EvalBreakdown.total` es siempre la suma exacta de los componentes publicados. El comando de consola `eval` devuelve JSON; el comando UCI no estándar `eval` devuelve una línea `info string`. La puntuación estática no debe confundirse con la puntuación tras búsqueda que aparece en `info score`.

## Validación

Las pruebas comprueban suma exacta, cambio de perspectiva, fase, simetría, pasados, pareja de alfiles, actividad de torres y contenido del perfil básico. Además se contrastó la simetría al reflejar colores y tablero en 1.600 posiciones aleatorias.

Como referencia inicial, `Positional` obtuvo 13 puntos frente a 3 de `Basic` en 16 partidas a profundidad 3, con ocho aperturas y colores invertidos. Es una comprobación funcional favorable; la muestra es pequeña y no constituye una estimación Elo fiable. En los experimentos publicados, los candidatos automáticos no superaron las puertas de fuerza. Consulta los [resultados fechados](validation.md) antes de comparar redes o pesos.

## NNUE opcional

`NNUEFile` carga una red `CHESSBOT_NNUE 1` y `NNUE=true` la usa en las hojas de la misma búsqueda
alfa-beta. El acumulador disperso se actualiza al hacer cada movimiento y se restaura al deshacerlo.
Desactivar `NNUE` vuelve inmediatamente a `Basic` o `Positional`, según la opción `Evaluation`.

Cuando NNUE está activa, `total` y `neural` contienen su puntuación y `source` vale `nnue`. Los
componentes posicionales siguen disponibles para explicar la posición, pero se marcan mediante
`manual_auxiliary=true` y su suma se publica en `manual_total`. La versión de pesos aparece en
`network_version`. Así el informe no atribuye la salida de la red a los términos manuales.
