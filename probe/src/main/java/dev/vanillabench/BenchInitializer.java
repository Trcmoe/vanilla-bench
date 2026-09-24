package dev.vanillabench;

import net.fabricmc.api.ClientModInitializer;

public final class BenchInitializer implements ClientModInitializer {
    @Override
    public void onInitializeClient() {
        BenchProbe.initialize();
    }
}
