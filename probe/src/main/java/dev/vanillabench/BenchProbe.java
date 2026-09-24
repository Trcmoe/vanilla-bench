package dev.vanillabench;

import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import net.minecraft.client.MinecraftClient;
import net.minecraft.client.gui.screen.TitleScreen;
import net.minecraft.client.option.GameOptions;
import org.lwjgl.opengl.GL11;

import java.io.BufferedWriter;
import java.io.IOException;
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.RuntimeMXBean;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.UUID;

/** The probe only activates when all benchmark environment variables are present. */
public final class BenchProbe {
    private static BenchProbe active;

    private final String runId;
    private final String worldName;
    private final String scenario;
    private final long warmupNanos;
    private final long durationNanos;
    private final BufferedWriter output;
    private final List<Double> frames = new ArrayList<>(120);
    private final long createdNanos = System.nanoTime();
    private Phase phase = Phase.MENU;
    private long worldReadyNanos;
    private long measurementNanos;
    private long lastFrameNanos;
    private float startYaw;
    private float startPitch;
    private double startX;
    private double startY;
    private double startZ;
    private int frameCount;

    private enum Phase { MENU, LOADING, WARMUP, MEASURING, DONE }

    public static void initialize() {
        String outputPath = System.getenv("VANILLA_BENCH_OUTPUT");
        if (outputPath == null || outputPath.isBlank()) return;
        try {
            String id = required("VANILLA_BENCH_RUN_ID");
            UUID.fromString(id);
            String world = required("VANILLA_BENCH_WORLD");
            if (world.equals(".") || world.equals("..") || world.contains("/") || world.contains("\\")) {
                throw new IllegalArgumentException("VANILLA_BENCH_WORLD must be a save folder name");
            }
            String mode = required("VANILLA_BENCH_SCENARIO").toLowerCase(Locale.ROOT);
            if (!mode.equals("static") && !mode.equals("rotate")) {
                throw new IllegalArgumentException("VANILLA_BENCH_SCENARIO must be static or rotate");
            }
            double warmup = parseSeconds("VANILLA_BENCH_WARMUP", true);
            double duration = parseSeconds("VANILLA_BENCH_DURATION", false);
            Path path = Path.of(outputPath);
            if (!path.isAbsolute()) throw new IllegalArgumentException("VANILLA_BENCH_OUTPUT must be absolute");
            Path parent = path.getParent();
            if (parent != null) Files.createDirectories(parent);
            BufferedWriter writer = Files.newBufferedWriter(path, StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE, StandardOpenOption.TRUNCATE_EXISTING, StandardOpenOption.WRITE);
            active = new BenchProbe(id, world, mode, warmup, duration, writer);
            active.hello();
        } catch (Exception ex) {
            System.err.println("Vanilla Bench Probe: " + ex);
            throw new IllegalStateException("Invalid Vanilla Bench Probe configuration", ex);
        }
    }

    private BenchProbe(String runId, String worldName, String scenario, double warmupSeconds,
                       double durationSeconds, BufferedWriter output) {
        this.runId = runId;
        this.worldName = worldName;
        this.scenario = scenario;
        this.warmupNanos = (long) (warmupSeconds * 1_000_000_000d);
        this.durationNanos = (long) (durationSeconds * 1_000_000_000d);
        this.output = output;
    }

    private static String required(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) throw new IllegalArgumentException(name + " is missing");
        return value;
    }

    private static double parseSeconds(String name, boolean zeroAllowed) {
        double value = Double.parseDouble(required(name));
        if (!Double.isFinite(value) || value < 0 || (!zeroAllowed && value == 0) || value > 3600) {
            throw new IllegalArgumentException(name + " must be finite and in (0, 3600] (warmup may be zero)");
        }
        return value;
    }

    public static void onFrameHead(MinecraftClient client) {
        if (active != null) active.frameHead(client);
    }

    public static void onFrameTail(MinecraftClient client) {
        if (active != null) active.frameTail(client);
    }

    private void hello() {
        RuntimeMXBean runtime = ManagementFactory.getRuntimeMXBean();
        JsonObject event = event("hello");
        event.addProperty("pid", ProcessHandle.current().pid());
        event.addProperty("jvm_uptime_ms", runtime.getUptime());
        event.addProperty("java_version", System.getProperty("java.version"));
        event.addProperty("jvm_name", runtime.getVmName());
        event.addProperty("max_heap_bytes", Runtime.getRuntime().maxMemory());
        event.addProperty("world", worldName);
        event.addProperty("scenario", scenario);
        event.addProperty("warmup_seconds", warmupNanos / 1_000_000_000d);
        event.addProperty("duration_seconds", durationNanos / 1_000_000_000d);
        write(event);
    }

    private void frameHead(MinecraftClient client) {
        if (phase == Phase.DONE || phase == Phase.MENU) return;
        long now = System.nanoTime();
        if (phase == Phase.LOADING) {
            if (now - createdNanos > 180_000_000_000L) fail(client, "world load timed out");
            else if (client.world != null && client.player != null && client.currentScreen == null
                    && client.getOverlay() == null) {
                if (!client.player.isSpectator()) {
                    fail(client, "benchmark world player must be in spectator mode");
                    return;
                }
                if (!client.isWindowFocused()) {
                    fail(client, "window is unfocused at world_ready");
                    return;
                }
                worldReadyNanos = now;
                startYaw = client.player.getYaw();
                startPitch = client.player.getPitch();
                startX = client.player.getX();
                startY = client.player.getY();
                startZ = client.player.getZ();
                phase = Phase.WARMUP;
                JsonObject event = event("world_ready");
                event.addProperty("jvm_uptime_ms", uptime());
                event.addProperty("player_x", client.player.getX());
                event.addProperty("player_y", client.player.getY());
                event.addProperty("player_z", client.player.getZ());
                event.addProperty("start_yaw", startYaw);
                event.addProperty("start_pitch", startPitch);
                event.addProperty("spectator", client.player.isSpectator());
                event.add("effective_settings", settings(client));
                event.add("runtime", runtime());
                write(event);
            }
            return;
        }
        if (client.world == null || client.player == null || client.currentScreen != null || !client.isWindowFocused()) {
            fail(client, "world, player, unpaused screen, or focus lost during benchmark");
            return;
        }
        if (Math.abs(client.player.getX() - startX) > 0.1 || Math.abs(client.player.getY() - startY) > 0.1
                || Math.abs(client.player.getZ() - startZ) > 0.1) {
            fail(client, "player moved during benchmark");
            return;
        }
        if (phase == Phase.WARMUP) {
            rotate(client, now - worldReadyNanos);
            if (now - worldReadyNanos >= warmupNanos) {
                phase = Phase.MEASURING;
                measurementNanos = now;
                lastFrameNanos = now;
                JsonObject event = event("measurement_start");
                event.addProperty("jvm_uptime_ms", uptime());
                write(event);
            }
            return;
        }
        rotate(client, now - worldReadyNanos);
        double frameMs = (now - lastFrameNanos) / 1_000_000d;
        lastFrameNanos = now;
        if (Double.isFinite(frameMs) && frameMs > 0) {
            frames.add(frameMs);
            frameCount++;
        }
        if (frames.size() >= 120) flushFrames();
        if (now - measurementNanos >= durationNanos) finish(client);
    }

    private void frameTail(MinecraftClient client) {
        if (phase == Phase.MENU && client.currentScreen instanceof TitleScreen && client.getOverlay() == null) {
            JsonObject event = event("menu");
            event.addProperty("jvm_uptime_ms", uptime());
            write(event);
            phase = Phase.LOADING;
            try {
                Path level = client.runDirectory.toPath().resolve("saves").resolve(worldName).resolve("level.dat");
                if (!Files.isRegularFile(level)) {
                    fail(client, "existing world level.dat is missing: " + level);
                    return;
                }
                client.createIntegratedServerLoader().start(client.currentScreen, worldName);
            } catch (Exception ex) {
                fail(client, "could not open world: " + ex);
            }
        } else if (phase == Phase.DONE) {
            client.stop();
        }
    }

    private void rotate(MinecraftClient client, long elapsedNanos) {
        if (scenario.equals("rotate")) {
            // One complete revolution every 12 seconds, starting at the world's saved yaw.
            double turns = elapsedNanos / 12_000_000_000d;
            client.player.setYaw(startYaw + (float) ((turns * 360d) % 360d));
        } else {
            client.player.setYaw(startYaw);
        }
        client.player.setPitch(startPitch);
    }

    private JsonObject settings(MinecraftClient client) {
        GameOptions options = client.options;
        JsonObject result = new JsonObject();
        result.addProperty("graphics_mode", String.valueOf(options.getGraphicsMode().getValue()));
        result.addProperty("render_distance", options.getViewDistance().getValue());
        result.addProperty("simulation_distance", options.getSimulationDistance().getValue());
        result.addProperty("max_fps", options.getMaxFps().getValue());
        result.addProperty("vsync", options.getEnableVsync().getValue());
        result.addProperty("clouds", String.valueOf(options.getCloudRenderMode().getValue()));
        result.addProperty("particles", String.valueOf(options.getParticles().getValue()));
        result.addProperty("fullscreen", client.getWindow().isFullscreen());
        result.addProperty("framebuffer_width", client.getWindow().getFramebufferWidth());
        result.addProperty("framebuffer_height", client.getWindow().getFramebufferHeight());
        result.addProperty("window_width", client.getWindow().getWidth());
        result.addProperty("window_height", client.getWindow().getHeight());
        result.addProperty("gl_vendor", GL11.glGetString(GL11.GL_VENDOR));
        result.addProperty("gl_renderer", GL11.glGetString(GL11.GL_RENDERER));
        result.addProperty("gl_version", GL11.glGetString(GL11.GL_VERSION));
        return result;
    }

    private JsonObject runtime() {
        Runtime runtime = Runtime.getRuntime();
        JsonObject result = new JsonObject();
        result.addProperty("heap_used_bytes", runtime.totalMemory() - runtime.freeMemory());
        result.addProperty("heap_committed_bytes", runtime.totalMemory());
        result.addProperty("max_heap_bytes", runtime.maxMemory());
        long collections = 0;
        long collectionMs = 0;
        for (GarbageCollectorMXBean gc : ManagementFactory.getGarbageCollectorMXBeans()) {
            if (gc.getCollectionCount() >= 0) collections += gc.getCollectionCount();
            if (gc.getCollectionTime() >= 0) collectionMs += gc.getCollectionTime();
        }
        result.addProperty("gc_collection_count", collections);
        result.addProperty("gc_collection_time_ms", collectionMs);
        return result;
    }

    private void finish(MinecraftClient client) {
        flushFrames();
        JsonObject event = event("measurement_end");
        event.addProperty("jvm_uptime_ms", uptime());
        event.addProperty("sample_count", frameCount);
        event.add("runtime", runtime());
        write(event);
        phase = Phase.DONE;
    }

    private void fail(MinecraftClient client, String message) {
        if (phase == Phase.DONE) return;
        if (!frames.isEmpty()) flushFrames();
        JsonObject event = event("error");
        event.addProperty("message", message);
        event.addProperty("jvm_uptime_ms", uptime());
        write(event);
        phase = Phase.DONE;
    }

    private void flushFrames() {
        if (frames.isEmpty()) return;
        JsonArray samples = new JsonArray();
        for (double sample : frames) samples.add(sample);
        JsonObject event = event("frames");
        event.add("frame_ms", samples);
        write(event);
        frames.clear();
    }

    private JsonObject event(String type) {
        JsonObject result = new JsonObject();
        result.addProperty("type", type);
        result.addProperty("run_id", runId);
        return result;
    }

    private static long uptime() {
        return ManagementFactory.getRuntimeMXBean().getUptime();
    }

    private void write(JsonObject event) {
        try {
            output.write(event.toString());
            output.newLine();
            output.flush();
        } catch (IOException ex) {
            phase = Phase.DONE;
            throw new IllegalStateException("Vanilla Bench Probe could not write JSONL", ex);
        }
    }
}
