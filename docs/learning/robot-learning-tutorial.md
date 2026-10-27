# Robot Learning Tutorial (Hugging Face)

- Fuente: https://huggingface.co/spaces/lerobot/robot-learning-tutorial. Repo:
  https://github.com/fracapuano/robot-learning-tutorial. Autores: Capuano, Pascal, Zouitine, Wolf
  y Aractingi.
- Revisado: commit `d288030` del Space (2025-10-15), leído desde la fuente LaTeX.
- Licencia: el texto es CC BY-NC-ND 4.0 (sin obras derivadas; una traducción lo sería). Los
  snippets de código son MIT. Por eso aquí hay resúmenes propios con enlaces, no texto copiado ni
  traducido.
- Es la base del [Hugging Face Robotics Course](hf-robotics-course.md). Los capítulos 1–2 son lo
  mismo que las unidades 1–2 del curso. Los capítulos 3–5 cubren lo que el curso aún no publicó.
- **Los snippets se escribieron para una versión anterior de LeRobot**: dos imports ya no existen
  en 0.6.1. Las rutas correctas están en [knowledge/lerobot.md](../knowledge/lerobot.md).

Las secciones "Resumen" son notas de referencia (hechas por Claude a partir del tutorial). Las
notas propias de cada sesión van al final.

## Cap. 1–2 · Introducción, LeRobotDataset y robótica clásica

Ver las [notas de las unidades 1–2 del curso](hf-robotics-course.md). Lo único que añade el
tutorial es un snippet para grabar un dataset con el brazo líder (`snippets/ch1/02_record_data.py`).

## Cap. 3 · Reinforcement learning (RL)

### Resumen

- **Marco**: un agente interactúa con un entorno. En cada paso ve un estado, elige una acción y
  recibe una **recompensa** (reward): un número que dice lo bien que va. La **política** es la
  regla "estado → acción", y se entrena para maximizar la suma de recompensas del episodio.
  Formalmente es un MDP (proceso de decisión de Markov).
- **Problemas de RL en un robot real**:
  - Al principio explora al azar, con movimientos bruscos que pueden dañar el hardware.
  - Necesita muchísimas interacciones.
  - Alguien tiene que reiniciar la escena a mano entre episodios.
- **Simulación como salida**: entrenar en sim es seguro y rápido, pero existe el **reality gap**
  (el simulador nunca es igual al mundo real).
- **Domain randomization (DR)**: en cada reinicio se cambian parámetros de la simulación (fricción,
  masas, luz…) para que la política sea robusta. Elegir *qué* aleatorizar y *cuánto* es difícil:
  - Poco rango → falla al pasar a lo real.
  - Demasiado rango → la política se vuelve conservadora y rinde peor.
  - Hay métodos que ajustan ese rango automáticamente.
- **Diseñar la recompensa es frágil**:
  - Una recompensa densa (puntos por acercarse, por agarrar…) guía mejor, pero invita a hacer
    trampas (reward hacking).
  - Una recompensa dispersa (solo "éxito sí/no") es honesta, pero aprende muy lento.
- **RL eficiente en el robot real**:
  - Algoritmos off-policy (SAC) que reutilizan experiencia guardada en un *replay buffer*.
  - Mezclar demostraciones humanas en ese buffer (RLPD).
  - Un **clasificador de recompensa** entrenado con fotos de éxito y fracaso (SERL).
  - Un humano que corrige durante el entrenamiento (**HIL-SERL**). Según los autores, logra ~99 %
    de éxito en 1–2 h de entrenamiento real. LeRobot lo implementa como actor + learner, que
    pueden correr en máquinas distintas.
- **Conclusión del capítulo**: por estos problemas, el tutorial pasa a imitation learning, que no
  necesita ni simulador ni recompensa.

### Impacto en el gate

- **La distribución de variaciones de escena es parte de la especificación del test.** Igual que
  en DR, si el evaluador cambia qué se aleatoriza o cuánto, la tasa de éxito cambia sin que cambie
  la política. Por eso el baseline guardado (`stats/baseline.json`) solo es comparable con la
  misma configuración del evaluador; conviene versionarla junto al baseline.
- **El gate necesita un detector de éxito aunque la política no use recompensa.** En sim sale de
  la pose del tubo. En el robot real, un **clasificador de éxito por cámara** (la misma idea que el
  clasificador de recompensa de SERL) podría automatizar los 20 intentos en vez de juzgarlos a ojo.
  Hay que tratarlo como un oráculo con su propia tasa de error.
- **Reward hacking ↔ tests que se pueden "pasar" sin hacer la tarea.** El criterio de éxito debe
  ser estricto: el tubo de pie dentro del rack y la pinza abierta, no "el tubo cerca del rack".

## Cap. 4 · Imitation learning: ACT, Diffusion Policy e inferencia

### Resumen

- **Behavioral cloning (BC)**: aprender "observación → acción" copiando demostraciones humanas,
  como un problema supervisado. Ventajas frente a RL:
  - Sin exploración peligrosa.
  - Sin recompensa que diseñar.
  - El fin del episodio ya viene en los datos.
  Límite: nunca supera al demostrador.
- **Dos problemas del BC ingenuo** (predecir una sola acción por observación):
  1. **Errores que se acumulan (covariate shift)**: un error pequeño lleva al robot a un estado
     que nunca vio en las demostraciones; ahí la política se equivoca más, y así hasta fallar.
  2. **Demostraciones multimodales**: si unas veces el humano rodea el objeto por la izquierda y
     otras por la derecha, un modelo que promedia sale "por el medio" y choca.
- **Solución: modelos generativos.** En vez de una acción, se aprende una *distribución* de
  acciones posibles. El tutorial explica tres familias:
  - **VAE**: comprimir en una variable latente y reconstruir.
  - **Difusión**: aprender a quitar ruido paso a paso.
  - **Flow matching**: lo mismo, pero con trayectorias rectas y menos pasos.
- **ACT (Action Chunking with Transformers)**:
  - Es un VAE condicional con transformers. Predice un **bloque de acciones futuras** (chunk) a
    partir de las imágenes y del estado de las articulaciones.
  - El encoder del VAE solo se usa para entrenar. En inferencia la variable latente se fija a
    cero, así que ACT no muestrea al azar.
  - El paper original mide dos ablaciones:
    - Con demostraciones humanas, quitar el VAE (usar solo pérdida L1) baja ~33 puntos el éxito.
    - Quitar el chunking hace caer el éxito de 44 % a 1 %.
  - Opción de **temporal ensembling**: inferir en cada paso y promediar los chunks que se
    solapan.
- **Diffusion Policy**:
  - Parte de un bloque de acciones con ruido y lo limpia, condicionado a las últimas
    observaciones.
  - Funciona con 50–150 demostraciones (15–60 min de teleoperación).
  - DDIM reduce los pasos de inferencia ~10×.
  - Los autores recomiendan empezar con la versión convolucional (U-Net), que es menos sensible
    a hiperparámetros.
- **Inferencia optimizada (async)**:
  - Ejecutar el chunk entero antes de volver a inferir (*sync*) es barato, pero deja al robot
    quieto mientras calcula.
  - En *async*, un `RobotClient` va consumiendo la cola de acciones y, cuando queda por debajo de
    un umbral `g`, manda una observación nueva a un `PolicyServer`, que puede estar en otra
    máquina con GPU.
  - Con 30 fps (33 ms por ciclo), el robot nunca se queda sin acciones si
    `g ≥ (latencia de inferencia / 33 ms) / tamaño del chunk`.
  - Se descartan observaciones casi idénticas para no saturar al servidor.

### Impacto en el gate

- **Probar en lazo cerrado, no con la pérdida de validación.** Por los errores acumulados, una
  política con buena pérdida offline puede fallar al ejecutarse. Solo los rollouts (ejecutar
  episodios completos) miden lo que importa. Es el argumento técnico de por qué el gate ejecuta la
  política en sim en vez de evaluar un split de test.
- **Con los defaults de LeRobot 0.6.1, ACT funciona en lazo abierto durante 3,3 s.**
  - `chunk_size = 100` y `n_action_steps = 100`: predice 100 acciones y las ejecuta todas
    (100 / 30 fps) antes de volver a mirar.
  - `temporal_ensemble_coeff = None`, así que no hay ensembling.
  - Cambiar `n_action_steps` o activar el ensembling cambia la tasa de éxito **sin tocar los
    pesos**. El gate debe dispararse también con cambios en la config de inferencia, y esa config
    debe ir en el contrato de resultados.
- **`policy.reset()` entre episodios es obligatorio.** ACT guarda la cola de acciones dentro de la
  política. Si el evaluador no llama a `reset()` al reiniciar la escena, el episodio N+1 empieza
  ejecutando acciones sobrantes del N. Los episodios dejan de ser independientes, y el intervalo
  de Wilson ([ADR 0003](../decisions/0003-statistical-gate-wilson-newcombe.md)) asume que lo son.
  Merece un test propio en el evaluador.
- **Las stats de normalización viajan con el checkpoint.** Los pre/post-procesadores se guardan con
  `save_pretrained` junto al modelo y `from_pretrained` restaura sus stats. El snippet de
  inferencia del tutorial, en cambio, reconstruye los procesadores con las stats del *dataset*. El
  evaluador debe cargarlos del checkpoint para evaluar exactamente lo que se entrenó.
- **Determinismo**: ACT no muestrea en inferencia, así que con la misma semilla de escena debería
  repetir el episodio, salvo por el no-determinismo de la GPU (hipótesis por medir).
  Diffusion Policy, π0 y SmolVLA sí muestrean ruido: además de la semilla de escena, el
  evaluador tiene que fijar la semilla de torch.
- **PRs de demo "malos a propósito"**: las ablaciones de ACT dan regresiones realistas para el
  criterio "un PR que empeora la política es bloqueado". Por ejemplo, `n_action_steps` absurdo,
  quitar el VAE o entrenar con la mitad de demostraciones.
- **Latencia (robot real)**: en sim el tiempo se puede pausar y el gate no la ve. Para los 20
  intentos reales conviene anotar la latencia de inferencia (CPU del portátil vs. GPU) junto a la
  tasa de éxito. Medir el tiempo por chunk también es barato en sim y podría ir en el contrato de
  resultados.

## Cap. 5 · Políticas generalistas (VLAs)

### Resumen

- La idea es la de los LLM aplicada a robots: preentrenar un modelo grande con datos de muchas
  tareas y robots, y adaptarlo (fine-tuning) a la tarea concreta. Obstáculo: los datos de
  robótica están atados a cada robot y son caros.
- **Datasets agregados**: Open X-Embodiment (1,4 M de trayectorias, 22 robots) y DROID (75 k).
  Demostraron que un modelo entrenado con datos de varios robots puede superar a los
  especialistas.
- **VLA (Vision-Language-Action)**: un modelo de visión y lenguaje preentrenado más un "experto de
  acción" que genera chunks de acciones continuas. Recibe la instrucción en lenguaje natural.
  - **π0** (Physical Intelligence): 3,3 B parámetros, flow matching, 10 M+ trayectorias (solo
    ~9 % públicas). Usa 3 cámaras y rellena con ceros a los robots con menos articulaciones.
  - **SmolVLA** (Hugging Face): ~450 M parámetros, preentrenado solo con ~450 datasets de la
    comunidad, la mayoría de SO-100/SO-101. Según los autores, rinde como π0 siendo ~40 % más
    rápido.
- **Hallazgo de π0**: las demostraciones "perfectas" no contienen errores, así que la política
  nunca aprende a recuperarse. Los datos diversos y algo imperfectos ayudan en eso.

### Impacto en el gate

- **Al grabar las ~50 demostraciones, incluir recuperaciones**: tubo mal agarrado y reintento,
  tubo que se cae. Lo dicen π0 (cap. 5) y la teoría de errores acumulados (cap. 4).
- **SmolVLA es un candidato realista para el SO-101** después de ACT, y cabe en GPUs modestas.
  Para el gate, en un VLA la **instrucción de texto es parte de la entrada del test**: cambiar el
  prompt es como cambiar el input.
- GR00T (NVIDIA, en el plan para más adelante) es de esta misma familia de VLAs.

## Dudas abiertas

- ¿Isaac Lab-Arena llama a `policy.reset()` entre episodios, o lo tiene que hacer nuestro
  evaluador?
- ¿Qué `n_action_steps` o ensembling usa la ruta de NVIDIA Sim-to-Real con ACT?
- ¿ACT da episodios idénticos con la misma semilla en la GPU del PC de casa? Medirlo: decide si un
  episodio fallido se puede reproducir para depurar.

## Notas de estudio

<!-- Una entrada por sesión, con la plantilla de README.md. -->
