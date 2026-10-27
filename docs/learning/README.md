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

## Exploraciones

- [Datasets públicos del SO-101](public-so101-datasets.md): qué contienen y qué implican para el gate.
