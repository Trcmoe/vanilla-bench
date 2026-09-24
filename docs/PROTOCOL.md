# 运行与遥测协议

本文描述当前 Python 运行器与客户端探针之间的文件协议。探针针对 Minecraft **1.20.1** 构建，通过 Fabric 客户端入口与 `MinecraftClient.render` 注入采样；原始字段以本仓库的 [`runner.py`](../src/vanilla_bench/runner.py) 和 [`BenchProbe.java`](../probe/src/main/java/dev/vanillabench/BenchProbe.java) 为准。[Yarn 1.20.1 的 MinecraftClient 文档](https://maven.fabricmc.net/docs/yarn-1.20.1%2Bbuild.10/net/minecraft/client/MinecraftClient.html)可用于核对游戏 API。

## 运行输入及隔离

`vanilla-bench validate CONFIG.json` 检查配置，`vanilla-bench run CONFIG.json --output NEW_DIR` 顺序执行。输出目录必须不存在，且不能位于源实例或世界模板之内。配置要求 `minecraft_version` 为 `1.20.1`、至少一个有唯一名称及固定版本的实例、已有的 `world_template`（含 `level.dat`）和 `probe_jar`。每个 `packs[]` 项需要 `name`、`version`、`game_dir` 和字符串数组 `command`，其中至少一个参数包含 `{game_dir}`。命令直接作为参数数组运行，不经 shell；应直接启动游戏 Java 进程，使探针报告的 PID 位于本次命令的进程树中。所有路径相对配置文件定位。`scenarios` 只允许 `static` 和 `rotate`。

默认值：`repetitions=5`、`warmup_seconds=30`、`duration_seconds=120`、`timeout_seconds=600`、`sample_interval_seconds=0.5`、`cooldown_seconds=10`、`seed=20260924`。默认覆盖的游戏选项为 `enableVsync:false`、`maxFps:260`、`pauseOnLostFocus:false`、`renderDistance:12`、`simulationDistance:8`、`fullscreen:false`、`overrideWidth:1920`、`overrideHeight:1080`。`maxFps:260` 在原版 1.20.1 的选项界面表示无限制，但仍应检查 `effective_settings` 与画面。输入世界须人工预制为旁观者、和平、白天、时间冻结，并预生成测试范围区块；配置加载器只核对 `level.dat`，不会代替人工复核这些条件。

每次运行将源实例复制到独立 `game` 目录，排除源 `saves`、截图、日志与崩溃报告，再把世界模板复制为 `saves/vanilla-bench-world`。运行器在副本中写入选项并安装探针；源实例不应预装另一份同 ID 探针。每轮先随机排列全部实例与场景，轮与轮之间不改变配置；每次启动一个新进程。运行结束后仅终止本次启动树中已记录的进程。操作系统缓存不清理，也不宣称冷启动。

## 传给探针的环境变量

| 名称 | 值与用途 |
| --- | --- |
| `VANILLA_BENCH_OUTPUT` | 本次运行的绝对路径 `telemetry.jsonl`；探针打开并逐行刷新。 |
| `VANILLA_BENCH_RUN_ID` | 本次运行的 UUID；每条事件必须与之相同。 |
| `VANILLA_BENCH_WORLD` | 世界存档文件夹名，目前固定为 `vanilla-bench-world`。 |
| `VANILLA_BENCH_WARMUP` | 世界就绪后的预热秒数，允许 0。 |
| `VANILLA_BENCH_DURATION` | 正数测量秒数。 |
| `VANILLA_BENCH_SCENARIO` | `static` 或 `rotate`。 |

若没有 `VANILLA_BENCH_OUTPUT`，探针保持不活动。其余变量缺失或格式错误时，探针拒绝运行。遥测为 UTF-8 JSON Lines：每行一个 JSON 对象，写入后刷新。`run_id` 是关联键；时间边界事件使用 JVM uptime 毫秒，帧样本使用单调时钟相邻 `render` 入口间隔的毫秒数，两者用途不同。

## 事件顺序和字段

允许的正常顺序是 `hello → menu → world_ready → measurement_start → frames（可多批）→ measurement_end`。`frames` 仅允许在测量阶段，数组须非空且每个值为有限正数；任何阶段可发 `error`。探针在主菜单出现时安排打开世界，在世界与玩家存在、没有打开界面且窗口有焦点时写 `world_ready`，随后预热、测量。`static` 保持保存的偏航角；`rotate` 每 12 秒转 360°。失焦、界面打开、世界或玩家消失等会报错；运行器还验证事件顺序、UUID、时间戳、游戏 PID 所属进程树、超时、帧覆盖和资源采样。

| 事件 | 主要字段 | 含义 |
| --- | --- | --- |
| `hello` | `pid`, `jvm_uptime_ms`, `java_version`, `jvm_name`, `max_heap_bytes`, `world`, `scenario`, `warmup_seconds`, `duration_seconds` | 探针启动与运行身份。 |
| `menu` | `jvm_uptime_ms` | 首次识别主菜单；用其 JVM uptime 作启动指标。 |
| `world_ready` | `jvm_uptime_ms`, `player_x/y/z`, `start_yaw / start_pitch`, `effective_settings`, `runtime` | 世界与玩家就绪时的条件快照。 |
| `measurement_start` | `jvm_uptime_ms` | 预热完毕，开始采样。 |
| `frames` | `frame_ms`（数字数组） | 最多约 120 个样本一批；本事件没有 JVM 时间戳。 |
| `measurement_end` | `jvm_uptime_ms`, `sample_count`, `runtime` | 达到测量时长后结束。 |
| `error` | `message`, `jvm_uptime_ms` | 探针发现运行条件失效或加载失败。 |

所有事件还有 `type`、`run_id`。`effective_settings` 记录图形模式、渲染/模拟距离、最大帧率、垂直同步、云、粒子、全屏、窗口与帧缓冲尺寸及 OpenGL vendor/renderer/version。`runtime` 记录 Java 堆使用/已提交/最大字节数和累计 GC 次数/耗时。这些是边界时刻快照，当前汇总报告不会把它们转换成独立性能评分。[Yarn 1.20.1 的集成服务器加载器文档](https://maven.fabricmc.net/docs/yarn-1.20.1%2Bbuild.10/net/minecraft/server/integrated/IntegratedServerLoader.html)给出游戏侧加载 API；`world_ready` 是本探针自定的判据，不是 Minecraft 官方性能事件。

例如，一次成功测量的遥测开头和结尾可呈现为（UUID 与数值仅示意）：

```jsonl
{"type":"hello","run_id":"aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa","pid":1234,"jvm_uptime_ms":800,"java_version":"17","jvm_name":"OpenJDK 64-Bit Server VM","max_heap_bytes":4294967296,"world":"vanilla-bench-world","scenario":"static","warmup_seconds":30,"duration_seconds":120}
{"type":"menu","run_id":"aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa","jvm_uptime_ms":4500}
{"type":"world_ready","run_id":"aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa","jvm_uptime_ms":8100,"player_x":0,"player_y":100,"player_z":0,"start_yaw":90,"effective_settings":{},"runtime":{}}
{"type":"measurement_start","run_id":"aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa","jvm_uptime_ms":38100}
{"type":"frames","run_id":"aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa","frame_ms":[16.5,17.2]}
{"type":"measurement_end","run_id":"aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa","jvm_uptime_ms":158100,"sample_count":2,"runtime":{}}
```

这只是结构例子，不满足默认 120 秒测量的帧覆盖门槛。真实 `world_ready.effective_settings` 和 `runtime` 含上文列出的字段。

## 输出、采样和失败

根目录 `results.json` 使用 `schema_version: 1`、`synthetic: false`、`metadata`、`runs`。元数据含创建时间、主机概况、世界/探针指纹、选项覆盖、预热与测量时长、随机种子、缓存策略及各实例 `mods`、`config`、`options.txt` 指纹。每次运行在 `run-NNN/` 保存 `telemetry.jsonl`、`process.log`、`run.json`；根目录随进度更新 `report.html`、`report.md`、`summary.csv`。`demo` 的 `synthetic: true` 和虚构实例名只用于报表演示，不代表实测或排名。

`runs[]` 的核心字段为 `pack`、`version`、`scenario`、`repetition`、`run_id`、`status`（`ok`/`failed`）、`error`、`startup_ms`、`world_load_ms`、`frames_ms`、`resources`、`events`；成功时还有 `launch_to_end_s`。启动时间等于 `menu.jvm_uptime_ms`，不含启动器时间；世界加载时间等于 `world_ready - menu`，含主菜单后的自动打开调度。`events` 是已接受的边界事件；帧批次被合并到 `frames_ms`。失败运行仍写出已采集的数据、错误和 `run.json`，汇总时排除其性能指标并列出原因。

`resources[]` 由运行器从游戏 Java 进程采样，每条包含 `elapsed_s`、`interval_s`、`cpu_percent`、`rss_bytes`、`read_bytes`、`write_bytes`、`system_memory_percent`。CPU 调用先在测量开始时预热，再按采样间隔读取；**100% 为一个逻辑核心**。RSS 是驻留内存，不能与私有字节或显存等同。I/O 不可取得时对应值为 JSON `null`，表示缺失而非零；此字段为累计计数，不是每秒速率。解释参见 [psutil 的进程 CPU、RSS 与 I/O 文档](https://psutil.readthedocs.io/stable/#process-class)。没有采集 GPU 功耗或显存。

详细统计公式及环境控制见 [`METHODOLOGY.md`](METHODOLOGY.md)。
