# 验证记录（v0.1.0）

- Windows / Python 3.12：16 项 unittest 通过，包含采集、超时后 PID 消失、源文件保护、HiDPI 尺寸判据、统计定义、无效数据和报表转义。
- `python -m compileall -q src`、`python -m pip check` 通过。
- `vanilla-bench demo` 成功输出带合成数据水印的 HTML / Markdown / CSV / JSON。
- Fabric 1.20.1 探针通过实际 Gradle 编译和 remap，输出 Java 17 字节码；构建使用 JDK 21。
- Modrinth API 确认并锁定了三个整合包的 1.20.1 稳定版本和文件哈希。
- 独立代码审查发现的遥测帧计数、测量时长、采样间隔、HiDPI 比较及超时清理测试问题已修复。

尚未在三个真实整合包、固定世界和图形桌面上完成整套性能实测。因此不宣称已有真实性能排名，也不把协议模拟测试视为游戏运行验证。首次真实运行应先将重复数改为 1、时长改为 10 秒做冒烟测试，再按完整默认参数采集。原始游戏日志仅在本地保存；分享前检查是否含账号信息。
