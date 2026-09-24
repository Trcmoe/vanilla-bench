Vanilla Bench v0.1.2 presents a general benchmarking workflow for user-selected compatible Minecraft instances. The catalog command now requires one or more explicit `--project` arguments; configuration examples use neutral Pack A / Pack B placeholders and no bundled real-pack version lock. The supported probe remains Minecraft 1.20.1 / Fabric and the existing probe 0.1.0 binary is unchanged.

- Isolated instance and world copies, randomized repeated trials, warmup and timeouts.
- JVM-to-menu startup, world load, frame-time/FPS tails, process CPU and RSS.
- Offline HTML, Markdown, CSV and raw JSON reports with failure records and synthetic demo labels.
- Python runner and Fabric probe workflows, with Chinese setup and methodology documentation.

Validation: 18 Python tests and the recorded dependency checks and Gradle build/remap passed locally. The probe binary is compiled for Java 17 and requires Fabric Loader 0.16+. Actual graphical benchmark runs against user-selected instances have not been performed; no performance ranking is claimed.
