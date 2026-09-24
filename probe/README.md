# Vanilla Bench Probe

This is a Fabric Loader client mod for Minecraft **1.20.1**. It uses Yarn mappings and
Mixin, with no Fabric API dependency. The build uses JDK 21 and produces Java 17
bytecode so it can run with a normal Minecraft 1.20.1 Java 17 installation.

Build with `./gradlew build` (`gradlew.bat build` on Windows). Install the remapped
`build/libs/vanilla-bench-probe-0.1.0.jar` in the benchmark instance's `mods`
directory. Use Fabric Loader 0.16 or newer. Do not install the `-dev` or `-sources`
jar. The mod does nothing unless `VANILLA_BENCH_OUTPUT` is set.

The launcher/runner must set all of these environment variables in the game process:

| Variable | Value |
| --- | --- |
| `VANILLA_BENCH_OUTPUT` | Absolute path for the run's JSONL result. The probe truncates it on startup and flushes every line. |
| `VANILLA_BENCH_RUN_ID` | UUID for correlating the run. |
| `VANILLA_BENCH_WORLD` | Existing save folder name inside the instance's `saves` directory. The probe requires `level.dat`. |
| `VANILLA_BENCH_WARMUP` | Seconds after the player enters the world, zero or more. |
| `VANILLA_BENCH_DURATION` | Measurement seconds, greater than zero. |
| `VANILLA_BENCH_SCENARIO` | `static` or `rotate`. |

The probe emits `hello` on client initialization, `menu` when the title screen has
actually completed its first render, then opens the existing singleplayer world
through Minecraft's integrated server loader. It emits `world_ready` when the
world and player are present and no screen is open. After warmup it emits
`measurement_start`, batches up to 120 samples in each `frames` event, and emits
`measurement_end` before asking Minecraft to stop. All events contain `run_id`;
`hello` also contains the game process PID, and lifecycle events carry JVM uptime.
The `world_ready` event records effective graphics settings, framebuffer and window
dimensions, OpenGL vendor/renderer/version, coordinates, and heap/GC counters.

Each `frame_ms` sample is the monotonic time from one entry into
`MinecraftClient.render(boolean)` to the next entry. Thus it measures the whole
client frame cadence, including rendering, ticks and any FPS cap/vsync wait between
those calls. It is not GPU execution time. The first sample begins at
`measurement_start` and is recorded on the next render entry; the last sample may
cross the duration boundary by at most one frame. The duration uses
`System.nanoTime()` and is independent of game ticks. `static` holds the saved
view yaw; `rotate` turns it at 30 degrees/second from that yaw, repeating every
12 seconds. The saved pitch and position remain unchanged. Use a spectator player
in a peaceful, pre-generated world at the same position and direction for every
run. The probe requires spectator mode and fails if the player moves over 0.1
block. The runner should copy that immutable world to each instance before launch.

If the world fails to load, an unexpected GUI appears, or the window loses focus,
the probe emits `error` and stops. A renderer mod may replace parts of the render
pipeline, but this client-level render hook remains outside the renderer. It can
measure stutter from loading or Java GC during the measurement window; enough
warmup and repeat runs are needed for comparable results.
