# Hugging Face Robotics Course

- Fuente: https://github.com/huggingface/robotics-course (web: https://huggingface.co/learn/robotics-course).
- Revisado: commit `2a50023` del 2026-10-14. Publicadas las unidades 0, 1 y 2; la 5 (RL), la 6
  (imitation learning) y la 7 (foundation models) están "Coming Soon". La 3 y la 4 no existen en
  el índice.
- El repo del curso no tiene licencia, así que aquí no se copia texto: son resúmenes propios con
  enlaces a cada página. El curso destila el
  [Robot Learning Tutorial](https://huggingface.co/spaces/lerobot/robot-learning-tutorial), que ya
  cubre RL e imitation learning: para ACT hay que ir allí mientras salen las unidades 5–7
  ([notas del tutorial](robot-learning-tutorial.md)).

Las secciones "Resumen" son notas de referencia (hechas por Claude a partir del curso). Las notas
propias de cada sesión de estudio van al final, con la plantilla de [README.md](README.md).

## Unidad 0 · Bienvenida

Páginas: [0.1](https://github.com/huggingface/robotics-course/blob/main/units/en/unit0/1.mdx),
[0.2](https://github.com/huggingface/robotics-course/blob/main/units/en/unit0/2.mdx).

### Resumen

- Recorrido del curso: de la robótica clásica (modelos matemáticos) a la basada en aprendizaje
  (datos), usando LeRobot como herramienta.
- Requisitos: Python básico; álgebra lineal y cálculo ayudan pero no son obligatorios. Unos
  30–45 min por unidad, con quiz al final.
- Se puede seguir sin robot, con datasets y simulación.
- Instalación sugerida: `pip install lerobot`. Aquí no se usa pip: es `uv sync --extra lerobot`
  ([ADR 0002](../decisions/0002-python-tooling-and-pinning.md)).

### Impacto en el gate

Ninguno directo. Es la introducción.

## Unidad 1 · Introducción al robot learning y LeRobot

Páginas: [1.1](https://github.com/huggingface/robotics-course/blob/main/units/en/unit1/1.mdx),
[1.2](https://github.com/huggingface/robotics-course/blob/main/units/en/unit1/2.mdx),
[1.3](https://github.com/huggingface/robotics-course/blob/main/units/en/unit1/3.mdx),
[1.4](https://github.com/huggingface/robotics-course/blob/main/units/en/unit1/4.mdx).

### Resumen

- **Robot learning**: en vez de programar cada comportamiento, el robot aprende de datos
  (demostraciones, sensores) y de feedback. Dos vías:
  - **Reinforcement learning (RL)**: prueba y error con recompensas.
  - **Imitation learning (IL)**: copiar demostraciones humanas. Es lo nuestro: el brazo líder
    graba las demostraciones y ACT aprende de ellas.
- La tendencia es aprender directamente "de lo que ve a lo que hace" (end-to-end), sin módulos
  separados de percepción y control. Es la misma receta que GPT y CLIP: muchos datos y un modelo
  grande.
- **LeRobot** es "verticalmente integrado": control del hardware, formato de datos, algoritmos
  (PyTorch) y despliegue en una sola librería. Soporta SO-100/SO-101 y ALOHA. Separa el "pensar"
  (inferencia de la política) del "hacer" (ejecutar acciones), para que el robot no se quede
  esperando al modelo.
- **LeRobotDataset**: los datos de robótica son multimodales (imágenes + sensores + acciones
  sincronizados), temporales y organizados en episodios. El formato tiene tres partes:
  - **Datos tabulares** (estado de las articulaciones, acciones) en parquet.
  - **Video**: los frames van a MP4, con varios episodios por archivo y una carpeta por cámara.
  - **Metadatos** en `meta/`: `info.json` (esquema, fps, versión), `stats.json` (media, std,
    mín y máx de cada feature, para normalizar), `tasks.jsonl` (texto de la tarea → índice) y
    `episodes/` (dónde empieza y acaba cada episodio dentro de los archivos grandes).
  - Al juntar episodios en pocos archivos se evita el problema de los millones de archivos
    pequeños; a cambio, los metadatos hacen de índice, como en una base de datos.
- **Ventanas temporales (`delta_timestamps`)**: un diccionario de offsets en segundos por feature.
  Cada muestra devuelve varios instantes a la vez:
  - Historia de observaciones, p. ej. `[-0.2, -0.1, 0.0]`: los últimos 200 ms.
  - **Action chunking**, p. ej. `"action": [0.0, 0.1, 0.2, 0.3]`: la política predice una
    secuencia de acciones futuras, no solo la siguiente. Es la idea central de ACT ("Action
    Chunking with Transformers").
  - En los bordes de un episodio rellena con padding y devuelve una máscara de qué frames son
    relleno.
- **Streaming**: `StreamingLeRobotDataset` lee del Hub sin descargar. El curso cita unos
  80–100 it/s con buena conexión. Los dos tipos se enchufan a un `DataLoader` de PyTorch.

### Impacto en el gate

- Lo que hace barato a `eval/dataset_stats.py` es leer solo `meta/`
  ([knowledge/lerobot.md](../knowledge/lerobot.md)). El curso confirma que el orden de lectura
  correcto es `info.json` → `stats.json` → un archivo de `data/` y uno de `videos/`.
- **`stats.json` forma parte de la política.** Las entradas del modelo se normalizan con esas
  estadísticas. Si un PR cambia el dataset de entrenamiento, también cambian las stats con las que
  se normaliza. Hipótesis por verificar con ACT: el checkpoint guarda sus propias stats y el gate
  debe usar las del checkpoint, no las del dataset.
- **Action chunking cambia cómo se cuentan los pasos.** Con ACT, cada inferencia produce varias
  acciones. El evaluador tiene que fijar cuántas se ejecutan antes de volver a inferir, porque eso
  afecta al éxito y al tiempo por episodio. Es un parámetro del test, igual que el timeout:
  ponerlo en el contrato de resultados para que dos ejecuciones sean comparables.
- **Latencia**: separar inferencia de ejecución importa en el robot real. En simulación el tiempo
  se puede pausar, así que el gate de sim no mide latencia. Queda como diferencia sim-vs-real
  para anotar en la prueba de 20 intentos.

### Dudas abiertas

- ~~¿Cuántas acciones del chunk ejecuta LeRobot 0.6 por defecto con ACT (`n_action_steps`)?~~
  Las 100 del chunk: ver [robot-learning-tutorial.md](robot-learning-tutorial.md), cap. 4.
- ~~¿El checkpoint de ACT trae sus propias stats de normalización?~~ Sí, en los pre/post-procesadores
  guardados con el modelo: ver [robot-learning-tutorial.md](robot-learning-tutorial.md), cap. 4.

## Unidad 2 · Robótica clásica

Páginas: [2.1](https://github.com/huggingface/robotics-course/blob/main/units/en/unit2/1.mdx),
[2.2](https://github.com/huggingface/robotics-course/blob/main/units/en/unit2/2.mdx),
[2.3](https://github.com/huggingface/robotics-course/blob/main/units/en/unit2/3.mdx),
[2.4](https://github.com/huggingface/robotics-course/blob/main/units/en/unit2/4.mdx),
[2.5](https://github.com/huggingface/robotics-course/blob/main/units/en/unit2/5.mdx).

### Resumen

- Dos familias para generar movimiento:
  - **Explícitas** (basadas en dinámica): modelos físicos hechos a mano, como PID o MPC.
    Funcionan muy bien en escenarios controlados y exigen mucho experto.
  - **Implícitas** (basadas en aprendizaje): aprenden el patrón de los datos.
  - Los enfoques **híbridos** usan la física para guiar o limitar lo aprendido.
- **Tipos de movimiento**. Pregunta clave: *¿qué cambia?*
  - Cambia el mundo → **manipulación** (nuestro caso: el tubo acaba en el rack).
  - Cambia la posición del robot → **locomoción**.
  - Cambian los dos → **manipulación móvil**.
- **Brazo = cadena de eslabones rígidos unidos por articulaciones**, con un **efector final**
  (end-effector: la pinza) en la punta. El SO-101 tiene 6 grados de libertad (5 de brazo + pinza).
  El curso simplifica el SO-100 a un brazo plano de 2 articulaciones para que salgan las cuentas.
- **Cinemática directa (FK)**: de los ángulos de las articulaciones a la posición de la pinza. Es
  trigonometría y siempre tiene solución.
- **Cinemática inversa (IK)**: de la posición deseada de la pinza a los ángulos. Es difícil por
  varias razones:
  - Puede tener varias soluciones o ninguna.
  - Las ecuaciones no son lineales.
  - Hay límites de articulación y obstáculos.
  - En general se resuelve como un problema de optimización.
- **IK diferencial**: se trabaja con velocidades en vez de posiciones. El **Jacobiano** `J(q)`
  relaciona velocidad de articulaciones con velocidad de la pinza, y su pseudo-inversa da las
  velocidades a pedir.
- **Lazo de realimentación (feedback)**: medir el error entre donde querías estar y donde estás, y
  corregir con una ganancia proporcional `k_p`. El curso recomienda empezar con `k_p` pequeño,
  limitar los comandos y tener una parada de seguridad (watchdog).
- **Cuatro límites de lo clásico**:
  1. Integración: módulos en serie (percepción → estimación → planificación → control) donde los
     errores se acumulan.
  2. Escalabilidad: cuesta meter cámaras y otros datos de alta dimensión, y cada tarea pide su
     propio planificador.
  3. Modelado: el contacto, la fricción y los objetos deformables son difíciles de modelar.
  4. Ignora los datasets abiertos, que no paran de crecer.
- Consejo del curso para un primer proyecto: imitation learning de pick-and-place con SO-101 y
  LeRobotDataset. Es exactamente la Fase 0.

### Impacto en el gate

- **Nuestra política trabaja en espacio de articulaciones, no de la pinza.** La acción del SO-101
  ya son 6 ángulos objetivo ([public-so101-datasets.md](public-so101-datasets.md)), así que ACT
  no necesita IK. La FK sí puede servir en el evaluador para calcular dónde está la pinza a partir
  del estado.
- **El criterio de éxito es sobre el mundo, no sobre el robot.** Como es manipulación, el
  evaluador debe comprobar el estado del objeto (tubo dentro del rack, de pie y soltado), no la
  pose final del brazo. En sim eso sale directamente de la pose del objeto. En el robot real lo
  juzga un humano o una cámara: es otro oráculo, y conviene anotarlo junto a la cifra real.
- **Feedback dentro de cada servo.** Cada STS3215 tiene su propio controlador que persigue la
  posición objetivo. La diferencia entre `action` y `observation.state` es el error de
  seguimiento: una métrica barata para detectar episodios raros (servo bloqueado, choque) aunque
  el episodio "pase".
- **Por qué hace falta el gate.** Una política aprendida no tiene un modelo que se pueda
  demostrar correcto como un PID: es una caja negra entrenada con datos. La única forma de saber
  si un cambio la empeoró es ejecutarla muchas veces y medir. Es el argumento de PipeRobot: el
  modelo clásico se verifica analizando; el aprendido, con tests estadísticos.

### Dudas abiertas

- ¿Isaac Lab-Arena da ya una función de éxito "tubo en el rack" o hay que escribirla?

## Notas de estudio

<!-- Una entrada por sesión, con la plantilla de README.md. -->
