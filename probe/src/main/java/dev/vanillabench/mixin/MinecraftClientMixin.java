package dev.vanillabench.mixin;

import dev.vanillabench.BenchProbe;
import net.minecraft.client.MinecraftClient;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

@Mixin(MinecraftClient.class)
public abstract class MinecraftClientMixin {
    @Inject(method = "render", at = @At("HEAD"))
    private void vanillaBenchFrameHead(boolean tick, CallbackInfo ci) {
        BenchProbe.onFrameHead((MinecraftClient) (Object) this);
    }

    @Inject(method = "render", at = @At("TAIL"))
    private void vanillaBenchFrameTail(boolean tick, CallbackInfo ci) {
        BenchProbe.onFrameTail((MinecraftClient) (Object) this);
    }
}
