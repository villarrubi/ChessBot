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
