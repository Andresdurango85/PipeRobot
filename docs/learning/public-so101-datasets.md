# Datasets públicos del SO-101 (2026-10-26)

Exploración con `uv run python -m eval.dataset_stats --repo-id <id>` (LeRobot 0.6.1). Solo se
descarga `meta/`, nunca los videos. Elegidos entre los más descargados al buscar "so101" en el Hub.

| Dataset | Real / sim | Episodios | Duración media | Cámaras | `robot_type` | Resultado |
| --- | --- | ---: | ---: | --- | --- | --- |
| `lerobot/svla_so101_pickplace` | Real | 50 | 8,0 s | side, up | `so100_follower` | OK (exit 0) |
| `maximilianofir/so101-left-rack-balanced-1000-dr-speed05-1-20261005` | Sim | 1000 | 10,9 s | external, wrist | `so101_follower` | OK (exit 0) |
| `SO-101-robot-learning/so101_pick_place` | Real | 0 (!) | — | side, top | `so_follower` | Vacío (exit 1) |
| `youliangtan/so101-table-cleanup` | Real | — | — | — | — | Formato v2.1, no carga (exit 2) |
| `aswinkumar99/so101-eval-gallery` | — | — | — | — | — | Sin tag de versión, no carga (exit 2) |

Todos los que cargan comparten 30 FPS y la misma acción de 6 dimensiones:
`shoulder_pan, shoulder_lift, elbow_flex, wrist_flex, wrist_roll, gripper` (`.pos`).

## Conceptos de robótica que aparecen

- **Acción = posición objetivo de cada articulación.** En cada frame (30 por segundo) la política
  dice a dónde debe ir cada uno de los 6 servos: hombro (giro y elevación), codo, muñeca (flexión y
  giro) y pinza. No son velocidades ni coordenadas del espacio: son ángulos objetivo.
- **`observation.state`** es la posición *real* de esos mismos 6 servos. Acción = lo que pides;
  estado = dónde está. La diferencia entre ambos es el "error de seguimiento".
- **Cámaras.** Casi siempre una fija de escena (side/up/top/external) y otra en la muñeca. Nuestro
  montaje es igual: C920 de escena + cámara USB de muñeca.
- **Domain randomization (DR)** en el dataset sim del rack: en cada reinicio cambian posición de
  objetos, rotación de la alfombrilla, inclinación y zoom de la cámara, iluminación (HDRI,
  exposición, temperatura de color) y hasta la velocidad máxima de las articulaciones (0,5–1,0×).
  Se hace para que la política no memorice una escena concreta y sobreviva al salto sim-to-real.
  Es exactamente lo que en el gate llamamos "variaciones de escena": la semilla decide la variación.

## Qué cambia en el gate

1. **El formato del dataset es una dependencia más, y rompe.** LeRobot 0.6 usa el formato v3.0 y
   no lee el v2.1 (hay script de conversión). Para la reproducibilidad hay que fijar la versión de
   LeRobot *y* la revisión del dataset (`--revision`), igual que fijamos `uv.lock`.
2. **Un dataset vacío no puede dar verde.** El primer intento de `dataset_stats` reportó 0 episodios
   con exit 0: un falso positivo. Corregido: ahora es un warning con exit 1, y un dataset que no
   carga es exit 2. Si el gate llega a consumir datasets (por ejemplo para el baseline), necesita
   estas comprobaciones antes de evaluar.
3. **`robot_type` no es fiable.** El mismo brazo aparece como `so100_follower`, `so_follower` y
   `so101_follower` (el SO-101 es una revisión del SO-100 con las mismas articulaciones). Para
   comprobar compatibilidad con nuestra política hay que mirar la dimensión y los nombres de la
   acción, no la etiqueta.
4. **Los nombres de las cámaras cambian entre datasets** (side/up, side/top, external/wrist). Una
   política entrenada espera claves concretas; la configuración del entorno en `envs/` tendrá que
   mapear las cámaras de la simulación a esas claves, y el gate debería fallar si falta alguna.
5. **Presupuesto de tiempo.** Los episodios duran 8–11 s (máximo ~15 s). 50 episodios ≈ 7–13 min
   de tiempo simulado. Si Isaac Sim corre cerca de tiempo real en la RTX de casa, cabe en los
   30 min por PR con margen para arrancar el simulador. A verificar cuando tengamos la simulación.
   El timeout por episodio puede salir de aquí: ~2× la duración máxima de las demostraciones.

## Dudas abiertas

- El dataset sim del rack (viales en un rack, cámara externa + muñeca, DR) se parece mucho a nuestra
  tarea. ¿Viene de la ruta de NVIDIA "Sim-to-Real" que seguimos? Su card cita un commit pero no el
  repositorio. Puede servir como datos de entrenamiento iniciales para ACT.
- ¿Cuánto tarda de verdad un episodio en Isaac Sim headless en la GPU de casa (más rápido o más
  lento que tiempo real)? Define cuántos episodios caben en 30 min.
