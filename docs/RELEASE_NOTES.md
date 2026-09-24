Vanilla Bench v0.1.0 adds a Python benchmark runner and a Fabric 1.20.1 probe for comparing vanilla-optimization modpacks.

- Isolated world/instance copies, randomized repeated trials, warmup and timeouts.
- JVM-to-menu startup, world load, frame-time/FPS tails, process CPU and RSS.
- Offline HTML, Markdown, CSV and raw JSON reports with failure records and synthetic demo labels.
- Pinned Modrinth metadata for Fabulously Optimized, Sodium Plus and Remarkably Optimized on 1.20.1.
- MIT license, Chinese setup/methodology documentation, Python and Java CI.

Validation: 16 Python tests, dependency checks, and a real Gradle build/remap passed locally. The attached probe is compiled for Java 17 and requires Fabric Loader 0.16+. Actual graphical runs of all three modpacks have not been performed; no performance ranking is claimed.
