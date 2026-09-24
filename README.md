# Vanilla Bench

面向 Minecraft **Vanilla optimization 整合包**的可复现性能测试工具。Python 负责隔离实例、随机化运行、多轮采样和出具报告；Fabric 探针负责自动进入测试存档和采集逐帧时间。

首版支持 **Minecraft 1.20.1 / Fabric / Java 17+ / Python 3.11+**。默认比较 [Fabulously Optimized](https://modrinth.com/modpack/fabulously-optimized)、[Sodium Plus](https://modrinth.com/modpack/sodiumplus) 和 [Remarkably Optimized](https://modrinth.com/modpack/remarkably)。准确拼写为 Remarkably Optimized。

这是测试工具，仓库中的演示报告使用明确标识的合成数据，不代表三个整合包的真实排名。真实结果需要在你的图形桌面、已登录的 Minecraft 实例和固定测试世界上运行。

## 测量内容

| 维度 | 指标 |
|---|---|
| 启动 | JVM 启动到主菜单事件的毫秒数 |
| 世界加载 | 主菜单事件到世界和玩家可用的毫秒数 |
| 流畅度 | 平均 FPS、1% / 0.1% low、P50 / P95 / P99 帧时间、>50 ms 卡顿次数/分钟 |
| 资源 | Java 进程 RSS 平均/峰值、CPU 平均/峰值；原始记录保留 I/O 计数与系统内存使用率 |
| 可靠性 | 每轮原始数据、失败原因、多轮中位数、FPS 变异系数、运行级 bootstrap 95% CI |

帧率来自游戏循环的帧间隔，不等同于显示器实际呈现的帧率。CPU 的 100% 表示一个逻辑核心。GPU 利用率、显存、能耗、启动阶段峰值资源、区块生成速度尚未采集，不能当成零。[完整测量定义](docs/METHODOLOGY.md)。

## 先看报告

```sh
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
python -m pip install -e .
vanilla-bench demo --output runs/demo
```

打开 `runs/demo/report.html`。同时生成 `report.md`、`summary.csv` 和含逐帧数据的 `results.json`。HTML 完全离线，无 CDN 依赖。再次运行请选择新的输出目录。

## 准备一次，自动执行多轮

1. **锁定版本。** [示例锁文件](examples/modrinth-lock.json)记录同为 1.20.1 的三个稳定版本：FO 5.2.8、Sodium Plus 2.2.11、Remarkably Optimized 1.15.11。用已登录的启动器分别安装对应 `.mrpack`，运行一次确保下载、账号和首次提示都处理完毕。不要混用 Minecraft 版本。可用 `vanilla-bench catalog --output local-lock.json` 重新查询；没有共同版本时命令明确失败。
2. **构建探针。** 在 `probe` 目录运行 `gradlew.bat build`（Windows）或 `./gradlew build`。构建需要 JDK 21，生成 Java 17 字节码。将配置中的 `probe_jar` 指向 `probe/build/libs/` 下不含 `-sources` 的 JAR。runner 每轮自动复制探针，不要将它放入原实例。[探针细节](probe/README.md)。
3. **准备只读基准存档。** 新建 1.20.1 世界，预生成观察点附近区块，切为旁观者，固定坐标/朝向，关闭天气和昼夜变化、随机刻等，保存退出。复制到独立目录作为 `world_template`。以不同存档单独测试森林、村庄、实体密集场景；本版每次 suite 使用一个世界。所有实例必须在同一世界、同一观察点测量。
4. **准备 Java 启动命令。** 建议使用支持 *Wrapper command* 的启动器，例如 Prism Launcher。按下面方法捕获每个实例的实际 Java 参数。runner 直接启动 Java，不依赖启动器窗口识别或鼠标坐标。
5. **创建配置。** 复制 `examples/benchmark.json` 为 `local-benchmark.json`；填写存档、探针、每个实例路径、版本和命令。图形功能、资源包、Java 可执行文件与 JVM 堆参数也需要统一。`options` 覆盖标准选项；各优化模组自己的设置请在源实例中事先调整。
6. **运行。**

```sh
vanilla-bench validate local-benchmark.json
vanilla-bench run local-benchmark.json --output runs/comparison-01
# 原始数据可以重新生成报告
vanilla-bench report runs/comparison-01/results.json --output runs/comparison-01
```

默认 5 轮、每轮每包每场景启动一个新 JVM，预热 30 秒、采集 120 秒、冷却 10 秒；`static` 固定视角、`rotate` 固定位置旋转观察。三个包两个场景共 30 次启动，预计至少 80 分钟，另加实例复制和加载时间。不要在采集中切换窗口、操作角色或打开菜单。

每轮创建独立实例和世界副本，源存档不会被覆盖。输出占用可能较大，运行前预留磁盘空间。Ctrl+C 会清理本次启动的进程并保留已完成的数据；失败轮次会记录并继续，最终命令返回非零状态码。不会终止其他已有 Java 进程。

### 捕获启动命令

在各实例的启动器设置中临时配置 Wrapper command（替换为你的绝对路径）：

```text
C:/path/to/vanilla-bench/.venv/Scripts/python.exe -m vanilla_bench capture --output C:/path/to/vanilla-bench/local-fo-command.json --
```

点击启动。该次操作仅捕获参数，**不会启动游戏**。把生成文件的整个对象填入配置的 `packs` 数组，并填写 `name` / `version`；然后移除启动器的 Wrapper command。重复另外两个实例。命令须包含独立的 `--gameDir` 参数，helper 自动替换为 `{game_dir}`；不接受未展开的 `@argfile`。禁用启动器快速加入服务器/世界功能。

捕获文件包含本地路径，可能包含登录 token：只保存在 `local*.json`，不要上传；本项目忽略这些文件，报告也不保存启动命令。账号令牌过期时重新捕获。实例的库、assets、native 路径必须保持有效；不能删掉源实例后再跑。不要使用会连接现有后台启动器的命令，否则探针环境变量及 PID 归属无法保证。

Linux/macOS 可使用对应 Python 绝对路径和启动命令；Python 单元测试在 CI 覆盖 Windows/Linux，实际图形驱动和整合包组合仍需在目标机器上验证。

## 公平性与边界

- `maxFps:260` 是 1.20.1 原版选项的无限制值；关闭 VSync，统一实际分辨率、渲染/模拟距离、云、粒子、实体距离、mipmap、资源包和着色器。显卡控制面板也可能限帧。
- 固定 Minecraft / Java / Fabric（建议统一 Loader 0.16.14）、JVM 参数、世界和探针；pack 自带的优化配置应明确属于“同画质”还是“开箱即用”配置。不要将两种测试混在一个排名中。
- 每轮重启 JVM 不会清空 OS 文件缓存。这里不宣称测到了冷启动；首次运行与后续运行仍有区别，结果保留运行顺序。
- 增加 `Fabric + probe` 基线可衡量收益，但它不是完全未修改的 vanilla。探针有采集开销，应在所有被测组中保持相同版本。
- 不生成任意加权的“总分”。更高平均 FPS 可能伴随更高内存或更差长尾，分别读各项数据。

[协议与扩展](docs/PROTOCOL.md) · [方法学](docs/METHODOLOGY.md) · [验证与限制](docs/VALIDATION.md)

## 开发与验证

```sh
python -m unittest discover -s tests -v
cd probe
./gradlew build
```

测试覆盖帧时间统计、失败排除、报告转义、协议乱序、超时清理、真实子进程数据采集与源实例保护。子进程测试是协议 fixture，不会冒充真实 Minecraft 性能测试。`.github/workflows/ci.yml` 同时构建探针。

## License

[MIT](LICENSE)。允许复用和商业使用，保留版权和许可声明。该许可仅涵盖本项目原创代码和文档；Minecraft、整合包、模组、世界与 Gradle wrapper 等第三方材料遵循各自许可。本仓库不分发游戏或整合包文件。

Not an official Minecraft product. Not approved by or associated with Mojang or Microsoft.
