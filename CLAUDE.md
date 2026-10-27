# Contexto del proyecto: so101-policy-ci

## Quién soy
Soy Andrés, Lead QA Automation Engineer / SDET con 9+ años en calidad de software. Mi fuerte es arquitectura de automatización de pruebas: Playwright, TypeScript, CI/CD (GitHub Actions, Jenkins), AWS y pruebas de rendimiento. Soy NUEVO en robótica: no asumas que conozco ROS, cinemática ni aprendizaje por imitación; explícame los conceptos de robótica cuando aparezcan, pero no los de CI/CD o testing.

## Qué estamos construyendo
Una idea de empresa: un "gate" de calidad para robots. En cada pull request que cambia código o pesos de una política de robot, el CI corre la política en simulación muchas veces, compara la tasa de éxito contra un baseline con un intervalo de confianza y bloquea el PR si hay regresión. Es lo que Playwright + GitHub Actions hacen para la web, aplicado a robots.

Este repo es la Fase 0 (aprendizaje, ~8 semanas, 8–10 h por semana) y su entregable es el gate funcionando en UNA tarea.

## Hardware y stack
- Robot: brazo SO-101 (líder + seguidor), impreso en mi Bambu Lab X2D.
  - Líder: 6 servos Feetech STS3215 de 7,4 V (1× 1/345, 2× 1/191, 3× 1/147), fuente de 5 V.
  - Seguidor: 6 servos STS3215 de 12 V, fuente de 12 V. Nunca mezclar fuentes.
- Cámaras: webcam Logitech C920 (escena) + cámara USB 720P en la muñeca.
- Tarea: recoger tubos de centrífuga de 50 ml y ponerlos en un rack amarillo, dentro de una caja de luz, siguiendo la ruta "Train an SO-101 Robot From Sim-to-Real With NVIDIA Isaac".
- Software: LeRobot 0.6+ (Hugging Face), Isaac Sim + Isaac Lab, Isaac Lab-Arena para evaluación, Rerun para visualizar episodios, GitHub Actions con runner self-hosted con GPU.
- Política inicial: ACT (pequeña, entrenable sin GPU grande). GR00T solo vía checkpoints de NVIDIA o nube.
- GPU: Isaac Sim necesita NVIDIA RTX (mínimo 3070 de 8 GB). Tengo dos PCs sincronizados vía GitHub:
  - PC de casa (con RTX): ahí corre todo lo pesado (Isaac Sim, entrenamiento) y el runner self-hosted de GitHub Actions.
  - Este portátil (sin RTX, poca RAM): para trabajar de viaje; solo código, tests ligeros, datasets y CPU.
  - Si hace falta GPU estando de viaje: NVIDIA Brev o una instancia con GPU en la nube.
- Ahora mismo estoy de viaje sin el hardware: las primeras semanas son cursos, datasets públicos y simulación en la nube.

## Estructura objetivo del repo
```
so101-policy-ci/
  policies/          # checkpoints o enlaces al Hub
  envs/              # configuración de Arena / Isaac Lab
  eval/              # script de evaluación, semillas, métricas
  stats/             # comparación contra baseline (intervalos de confianza)
  reports/           # plantilla del comentario en el PR
  docs/learning/     # mis notas de los cursos
  .github/workflows/ # pr-gate.yml y nightly.yml
```

## Criterios de terminado de la Fase 0
- Workflow en GitHub Actions que corre en runner con GPU, headless, en menos de 30 min por PR.
- Evaluación de al menos 50 episodios con semillas y variaciones de escena distintas.
- Veredicto estadístico: tasa de éxito con intervalo de confianza vs. baseline guardado.
- Comentario automático en el PR con la tasa, el veredicto y videos de episodios fallidos.
- Una prueba en el brazo real (20 intentos) documentada junto a la cifra de simulación.
- Un PR que empeora la política a propósito queda bloqueado; uno que no, pasa.
- README que permite reproducirlo en 30 minutos.

## Cómo quiero trabajar contigo
- Háblame en español; código, nombres y comentarios en inglés.
- Python con tipos, pytest, ruff; dependencias fijadas (uv o pip-tools).
- Pasos pequeños y verificables: propón el plan antes de cambios grandes y pregúntame antes de instalar algo pesado (Isaac Sim, CUDA, Docker de varios GB).
- Trata la evaluación como un problema de testing: flakiness, semillas, reproducibilidad y reportes son ciudadanos de primera clase.
- Verifica comandos contra la documentación actual de LeRobot 0.6+ e Isaac Lab-Arena; los tutoriales viejos usan comandos que ya cambiaron (por ejemplo control_robot.py).
- Es un repo personal, público, en mi cuenta personal de GitHub. No uses credenciales ni recursos de ningún empleador.

## Cursos que estoy siguiendo
- Hugging Face Robotics Course (https://huggingface.co/learn/robotics-course/en/unit0/1): voy por la unidad 0 (inicio, 2026-10-26).
  - Publicadas: 0 Bienvenida, 1 Introducción (robot learning, ecosistema LeRobot), 2 Robótica clásica.
  - Próximamente: 5 Aprendizaje por refuerzo, 6 Aprendizaje por imitación (la base de ACT), 7 Modelos fundacionales.
  - Unidades de 30–45 min, con código LeRobot y quizzes. Notas en `docs/learning/`.

## Notas técnicas del repo
- Gestor de dependencias: uv. `uv sync` instala solo lo ligero (ruff, pytest); `uv sync --extra lerobot` añade LeRobot, que trae torch (varios GB): pedir permiso antes.
- LeRobot fijado a 0.6.1 (requiere Python ≥ 3.12). `LeRobotDatasetMetadata` se importa desde `lerobot.datasets` y solo descarga `meta/` (no videos).
- Los tests que tocan el Hub llevan el marcador `hub` y no corren por defecto: `uv run pytest -m hub`.
- Este PC tiene poca RAM: nada de builds ni suites pesadas en local.
- GitHub: repo público `Andresdurango85/PipeRobot` (Apache-2.0); la carpeta local sigue llamándose `so101-policy-ci`.
- En el portátil, `gh` tiene dos cuentas y la activa es la del trabajo: NUNCA usarla aquí ni hacer `gh auth switch` (otras sesiones dependen de ella). Para `gh` en este repo: `GH_TOKEN=$(gh auth token --user Andresdurango85) gh ...`. `git push` ya usa la cuenta personal gracias a un `credential.helper` local del repo; identidad de commits configurada en local (`git config --local`).
