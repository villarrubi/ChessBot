# Búsqueda

ChessBot usa negamax con alfa-beta, PVS, profundización iterativa y búsqueda de quietud. Mantiene la variante principal y el resultado de la última iteración terminada. Si una orden de parada llega antes de completar profundidad 1, devuelve una jugada legal de respaldo.

## Perfiles comparables

La opción UCI `SearchProfile` permite seleccionar `Baseline` u `Optimized`. Ambos perfiles usan el mismo tablero, evaluador, tabla de transposición y backend de ataques. `Baseline`, que sigue siendo el valor predeterminado, conserva la búsqueda completa de la fase 4. `Optimized` añade PVS, killers, historial, ventanas de aspiración y podas selectivas. Cambiar el perfil limpia la tabla para que una medición no reutilice resultados del otro.

```text
setoption name SearchProfile value Optimized
position startpos
go depth 8
```

## Flujo optimizado

1. Comprobar parada, límites, tablas y terminales. Jaque mate tiene prioridad sobre una reclamación de tablas.
2. Consultar la tabla de transposición y ordenar mediante movimiento TT, promociones, MVV-LVA, killers e historial.
3. Buscar el primer movimiento con ventana completa y los siguientes con PVS. Una mejora dentro de la ventana provoca una búsqueda completa.
4. En profundidad cero, entrar en quietud. En jaque se exploran todas las evasiones; fuera de jaque se generan directamente capturas y promociones, con poda delta de capturas que no pueden alcanzar alfa. En el perfil optimizado los candidatos pseudo-legales se validan al buscarlos, evitando hacer y deshacer cada movimiento dos veces.
5. A partir de profundidad 3, reducir jugadas tranquilas tardías que no dan jaque. La reducción crece con profundidad y orden; toda jugada que supera alfa se repite a profundidad completa.
6. A partir de profundidad 3, probar null-move únicamente fuera de jaque, con evaluación al menos beta y material no peón. No se permite otro null-move consecutivo.
7. En nodos de ventana estrecha aplicar razoring, poda por evaluación estática, futilidad y poda de movimientos tranquilos tardíos con márgenes dependientes de profundidad.
8. Aplicar una reducción iterativa interna de un ply en nodos profundos sin movimiento de transposición y reutilizar entradas alejadas del límite de 50 jugadas aunque su reloj no sea idéntico.
9. Guardar mejor movimiento, profundidad, cota y puntuación de mate normalizada.

Null-move queda desactivado en finales de solo rey y peones, donde el zugzwang es frecuente. Las posiciones artificiales creadas por esa poda no se usan para declarar triple repetición o cincuenta movimientos. Hacer y deshacer el pase restaura hash, turno, en passant, relojes e historial.

Las extensiones generales de jaque, SEE como criterio de poda, extensiones singulares y reducciones iterativas internas no forman parte del perfil. Las podas nuevas solo se activan en `Optimized`; `Baseline` conserva la referencia completa para comparaciones y regresiones.

## MultiPV y movimientos de raíz

`SearchLimits.multiPv` solicita alternativas ordenadas hasta cubrir todas las jugadas legales de la posición (el protocolo UCI admite 1–256). Cada `RootVariation` contiene jugada, puntuación y PV. `SearchLimits.rootMoves` limita las candidatas; UCI lo expone mediante `go ... searchmoves`. Esto permite valorar la jugada de una partida con el mismo límite usado para buscar la mejor alternativa.

```text
setoption name MultiPV value 3
position startpos moves e2e4 e7e5
go depth 6
go depth 6 searchmoves g1f3 f1c4
```

## Ataques y asignaciones

Las listas internas de búsqueda usan `MoveList`, un array fijo para el máximo de movimientos de una posición, por lo que no reservan un vector en cada nodo. La API pública conserva vectores donde facilitan diagnóstico y pruebas.

Los ataques de alfil y torre se precalculan para todos los subconjuntos relevantes de ocupación. En x64 se usa PEXT cuando la CPU anuncia BMI2; las demás arquitecturas comprimen la ocupación por software sobre las mismas tablas. `chessbot bench` informa `sliders pext` o `sliders lookup-software`.

No se añadió caché de peones: el perfil seguía dominado por generación y quietud, y los términos de pasados dependen también de reyes y torres. Separarlos sin cambiar la evaluación exige una medición específica posterior.

## Límites y parada

`SearchLimits` admite profundidad, nodos, tiempo por movimiento, relojes, incrementos, movimientos restantes e infinito. Los relojes usan `-1` para «no suministrado» y aceptan `0` como tiempo agotado. El gestor resta `Move Overhead`, calcula límites blando y duro y usa un reloj monotónico. La parada externa es atómica.

El límite blando decide si se inicia otra iteración y el duro interrumpe la actual. Los análisis con reloj conservan la última profundidad completa. El límite de nodos es global: con varios hilos no se multiplica por el número de trabajadores.

## Búsqueda paralela

La opción UCI `Threads`, entre 1 y 256, activa Lazy SMP. Cada trabajador mantiene su tablero, acumulador NNUE, PV, killers e historial y comparte una tabla de transposición protegida por bloqueos segmentados. Los ayudantes omiten distintas iteraciones intermedias para reducir trabajo duplicado. El contador global se publica por lotes en búsquedas por profundidad para evitar serializar cada nodo; los límites explícitos de nodos conservan contabilidad exacta. La señal de parada y el reloj coordinan todos los trabajadores, y las métricas finales agregan su trabajo.

`Threads=1` conserva la ruta monohilo y es la configuración predeterminada para pruebas reproducibles. Valores mayores aprovechan varios núcleos; la mejora depende de la posición, la duración y la CPU.

## Métricas y referencia

`SearchResult` registra profundidad, profundidad selectiva, nodos, quietud, tiempo, TT, cortes beta, cortes con el primer movimiento, movimientos generados, ramificación máxima, reintentos de aspiración, intentos/cortes null-move, reducciones/rebúsquedas LMR y podas de futilidad. `AnalysisDetail=Full` publica estos contadores en líneas `info string search_metrics`.

En la máquina de validación, `bench 5 Baseline` produjo 567.651 nodos en 1.415 ms. La revisión actual de `Optimized` produjo 33.351 nodos en 42 ms: 94,1 % menos nodos. Tres de las cuatro posiciones conservaron jugada y puntuación; la posición inicial cambió de `e3` a `d4` con una diferencia de 6 cp. Una comprobación corta de 16 partidas a 20 ms dio 5 victorias, 10 tablas y 1 derrota para `Optimized`; es una señal favorable, no una estimación definitiva de fuerza.

```powershell
.\build\Release\chessbot.exe bench 5 Baseline
.\build\Release\chessbot.exe bench 5 Optimized
```

Syzygy se evaluó como ampliación opcional. No está integrado porque requiere archivos externos, configuración WDL/DTZ y una política de cincuenta movimientos; el motor funciona completamente sin tablas.
