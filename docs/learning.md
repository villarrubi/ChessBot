# Ajuste de la evaluación manual

La fase 8 implementa un ciclo por lotes: PGN y metadatos de búsqueda → dataset → ajuste tipo
Texel → candidato → pruebas → promoción o rechazo. Ninguna partida modifica los parámetros que
usa el motor. `EvalFile` carga un archivo completo al iniciar el experimento y limpia la tabla de
transposición.

## Generar un dataset

```powershell
python tools/generate_dataset.py `
  --pgn data/engine_matches/phase5-final-50ms-64.pgn `
        data/engine_matches/phase5-opt-vs-base-10ms-effective-64.pgn `
  --engine build/Release/chessbot.exe --output build/phase8-dataset.csv `
  --skip-plies 8 --sample-every 3 --max-per-game 40 --max-per-bucket 400 `
  --validation-fraction 0.2 --seed 20260915
```

CSV funciona con las dependencias básicas. Una salida `.parquet` requiere el extra `analysis`.
El archivo lateral `.schema.json` registra versión, filtros, semilla, filas y particiones. Cada
fila contiene Zobrist, FEN, turno, ply, partida, origen, resultado desde blancas y desde el lado al
mover, puntuación de búsqueda cuando existe y todos los componentes estáticos.

Las primeras jugadas y posiciones terminales se descartan; el muestreo limita la correlación,
Zobrist elimina duplicados globalmente y los buckets de 200 cp pueden equilibrarse. La partición
se hace por partida, por lo que una partida nunca aparece en entrenamiento y validación.

## Ajustar y evaluar

```powershell
python tools/tune_eval.py --dataset build/phase8-dataset.csv `
  --reference data/evaluation/hce-default-v1.params `
  --output-dir build/phase8-tuning --iterations 1000 `
  --learning-rate 0.01 --regularization 0.1 --version hce-texel-phase8-v1

python tools/evaluate_candidate.py --engine build/Release/chessbot.exe `
  --candidate build/phase8-tuning/candidate.params `
  --reference build/phase8-tuning/reference.params `
  --tuning-report build/phase8-tuning/tuning.json `
  --openings data/openings/strength-v1.json --games 100 --depth 2 `
  --minimum-independent-samples 32 --output-dir build/phase8-evaluation `
  --promote-to data/evaluation/hce-active.params
```

El ajuste minimiza entropía cruzada logística, calibra la conversión entre centipeones y resultado
y regulariza los multiplicadores hacia la referencia. Exporta `candidate.params`, una copia de
`reference.params` y `tuning.json`.

La evaluación comprueba PERFT, tres regresiones tácticas, coste temporal, mejora de validación y
partidas emparejadas. Solo copia el candidato a `--promote-to` cuando pasan todas las puertas; si
se rechaza, conserva ambos archivos y el informe. La campaña registrada en
`data/evaluation/phase8-experiment-v1.json` rechazó el primer candidato: la pérdida de validación
bajó ligeramente, pero 100 partidas sobre 50 aperturas dieron 25–49–26 e IC95% de −51,0 a +43,9
Elo. `hce-active.params` conserva por ello `hce-default-v1`.

Para usar un archivo explícitamente:

```text
setoption name EvalFile value data/evaluation/hce-active.params
```

Los valores de componentes son multiplicadores por mil: `1000` mantiene el valor compilado,
`500` lo reduce a la mitad y `0` lo desactiva. `calibration` documenta la pendiente probabilística
y no altera la puntuación centipeón que usa la búsqueda.

## Red pequeña y formato NNUE

`train_nnue.py` usa PyTorch en CPU con semilla y algoritmos deterministas. La entrada contiene 768
características binarias: color × tipo de pieza × casilla. La capa oculta ReLU admite de 1 a 64
neuronas y produce una puntuación en centipeones orientada a blancas; C++ cambia el signo según el
turno. La etiqueta puede ser resultado, puntuación de búsqueda o una mezcla documentada de ambas.

```powershell
python tools/train_nnue.py --dataset build/phase8-dataset.csv `
  --output-dir build/nnue-training --version nnue-example-v1 `
  --hidden 32 --epochs 20 --target mixed --teacher-weight 0.25 --seed 7 `
  --shard-dir build/nnue-training/shards
```

La salida conserva `checkpoint.pt`, `candidate.nnue` y `training.json`. Este último registra el hash
del dataset, arquitectura, etiquetas, cuantización, versiones, hiperparámetros, pérdida, Brier,
error de calibración WDL, error respecto al profesor y memoria de la red. Los shards NPZ comprimidos
son opcionales; sirven para datasets grandes sin cambiar el formato que consume el motor.

`CHESSBOT_NNUE 1` es un formato de texto portable y versionado. Guarda sesgos y pesos enteros,
factores de cuantización y arquitectura. `nnue_format.py` implementa la referencia Python;
`test_nnue.py` exige igualdad exacta con C++ en posiciones fijas y aleatorias. La búsqueda conserva
un acumulador por nodo: quita y añade las características afectadas por cada movimiento y restaura
la copia anterior al deshacer. Las pruebas cubren capturas, en passant, enroques, promociones y
secuencias aleatorias.

Para evaluar un candidato neuronal frente a HCE:

```powershell
python tools/evaluate_candidate.py --engine build/Release/chessbot.exe `
  --candidate build/nnue-training/candidate.nnue --candidate-kind nnue `
  --reference data/evaluation/hce-active.params --reference-kind hce `
  --training-report build/nnue-training/training.json `
  --games 32 --depth 3 --minimum-independent-samples 16 `
  --output-dir build/nnue-evaluation --promote-to data/networks/nnue-active.nnue
```

En UCI se carga primero `NNUEFile` y se activa después `NNUE`. `eval --nnue-file FILE` devuelve la
puntuación neuronal como `total`, `source=nnue` y la versión de red. Los componentes HCE aparecen
con `manual_auxiliary=true` y `manual_total`; no se presentan como sumandos de la salida neuronal.
El analizador PGN acepta el mismo archivo con `--nnue-file` y conserva esa procedencia.

## Ciclo completo y presupuestos

`learning_cycle.py` ejecuta por lotes partidas, dataset, entrenamiento y evaluación. Su JSON permite
fijar partidas de generación y evaluación, segundos máximos, almacenamiento máximo, hilos, semilla,
filtros del dataset, arquitectura y puertas de aceptación. El directorio de salida debe ser nuevo.
Así una partida aislada nunca modifica el motor activo ni sobrescribe un experimento.

```powershell
python tools/learning_cycle.py --config data/training/phase10-config-v1.json `
  --engine build/Release/chessbot.exe --output-dir build/cycle-v1
```

El manifiesto final incluye los comandos ejecutados, duración, uso de almacenamiento, commit,
Python, plataforma, CPU, compilador, semilla y versiones de búsqueda, evaluación, libro, dataset y
red. Cada artefacto lleva tamaño y SHA-256. `evaluate_candidate.py` solo copia a `promote_to` si
pasan corrección/táctica, validación, rendimiento y fuerza; antes de reemplazar una referencia crea
una copia en el directorio del experimento. Un rechazo conserva el candidato y deja intacta la
referencia activa.

El CI rápido compila y comprueba reglas, UCI, análisis, NNUE y formato sin instalar PyTorch. El
workflow manual `learning.yml` instala el extra `training`, ejecuta la campaña y publica todos sus
artefactos durante 30 días. Para diagnosticar un fallo, se consulta `manifest.json`, después el
registro del comando de la etapa fallida y finalmente `engine.log` si el problema ocurrió durante
una partida.

La campaña `nnue-phase9-v1` perdió 0–16 y quedó rechazada. La ejecución registrada de fase 10 creó
1.406 muestras, entrenó una red `768×16×1`, pasó PERFT y táctica, pero logró solo el 28,0 % del NPS
de HCE en su benchmark y 0–1–1 en la prueba corta. Se rechazó sin modificar `hce-active.params`.
Los datos resumidos están en `data/networks/phase9-experiment-v1.json` y
`data/training/phase10-experiment-v1.json`.
