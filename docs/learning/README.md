# Learning log

Notas de los cursos de la Fase 0. Una sección por curso; una entrada por sesión de estudio.
Lo importante no es resumir el curso sino anotar **qué cambia en el gate** por lo aprendido.

## Glosario (robótica → equivalente en testing)

| Término | Qué es | Analogía QA |
| --- | --- | --- |
| Política (policy) | El modelo que, dada una observación (imágenes + posición de las articulaciones), decide la siguiente acción del brazo | El "sistema bajo prueba" |
| Episodio | Un intento completo de la tarea, de la posición inicial hasta éxito, fallo o timeout | Una ejecución de un test |
| Acción | Vector de posiciones objetivo para cada articulación (6 en el SO-101: 5 de brazo + pinza) | Un paso del test |
| Observación / estado | Lo que el robot "ve" y "siente" en cada instante (cámaras + posición actual de los servos) | El DOM / estado de la app |
| Aprendizaje por imitación | Entrenar la política copiando demostraciones humanas hechas con el brazo líder | Grabar y reproducir, pero generalizando |
| Líder / seguidor | El líder lo mueves tú con la mano; el seguidor copia sus movimientos y es el que ejecuta la tarea | — |
| Sim-to-real | Entrenar/evaluar en simulación y comprobar que funciona en el robot físico | Staging vs. producción |
| Semilla (seed) | Fija la aleatoriedad de la escena (posición de los tubos, luz) para que un episodio sea reproducible | Datos de prueba deterministas |
| Grado de libertad (DOF) | Cada articulación que se puede mover de forma independiente; el SO-101 tiene 6 | Cada parámetro de entrada |
| Efector final (end-effector) | Lo que está en la punta del brazo y actúa sobre el mundo: la pinza | — |
| Cinemática directa / inversa (FK / IK) | FK: de ángulos a posición de la pinza (cálculo directo). IK: de posición deseada a ángulos (búsqueda; puede no tener solución o tener varias) | Función vs. su inversa |
| Lazo de realimentación (feedback) | Medir el error entre objetivo y realidad y corregir en cada ciclo | Retry con backoff, pero continuo |
| Ventana temporal (`delta_timestamps`) | Pedir al dataset varios instantes por muestra: historia de observaciones y acciones futuras | Contexto del test |
| Action chunking | La política predice varias acciones futuras de una vez (la "AC" de ACT) | Un batch de pasos |
| Behavioral cloning (BC) | La forma más simple de imitation learning: aprendizaje supervisado de observación → acción sobre demostraciones | Snapshot testing al revés: el "golden" es el humano |
| Errores acumulados (covariate shift) | Un error pequeño lleva al robot a estados no vistos en el entrenamiento, donde falla más | Un test que pasa unitario y falla en e2e |
| Recompensa (reward) | Número que en RL dice lo bien que va el agente; ACT no la usa | Una aserción con puntuación |
| VLA | Modelo visión-lenguaje-acción: recibe imágenes e instrucción en texto y genera acciones (π0, SmolVLA, GR00T) | — |

## Plantilla de entrada

```markdown
### YYYY-MM-DD — <curso> · <unidad>
- Qué aprendí:
- Comandos verificados (versión de LeRobot / Isaac Lab):
- Impacto en el gate:
- Dudas abiertas:
```

## Cursos

<!-- Añade aquí cada curso: nombre, enlace, unidad actual. -->

### Hugging Face Robotics Course

- Enlace: https://huggingface.co/learn/robotics-course/en/unit0/1
- Unidad actual: 0 (empezado el 2026-10-26).
- Notas: [hf-robotics-course.md](hf-robotics-course.md). Hay resumen e impacto en el gate de las
  unidades publicadas (0–2); las de RL, IL y foundation models aún no existen.

### Robot Learning Tutorial (Hugging Face)

- Enlace: https://huggingface.co/spaces/lerobot/robot-learning-tutorial
- Base del curso anterior; ya cubre RL, imitation learning (ACT) y VLAs.
- Notas: [robot-learning-tutorial.md](robot-learning-tutorial.md).

### Pendientes en la Fase 0

- Isaac Sim.
- Isaac Lab.
- Ruta de NVIDIA "Train an SO-101 Robot From Sim-to-Real With NVIDIA Isaac".
- Isaac Lab-Arena + LeRobot (evaluación).

Práctica con hardware (al volver de viaje): armar el SO-101 (líder + seguidor), calibrar,
teleoperar, grabar ~50 episodios y entrenar ACT.

## Exploraciones

- [Datasets públicos del SO-101](public-so101-datasets.md): qué contienen y qué implican para el gate.
