# 测试报告

日期：2026-10-30

更新：2026-10-31（精密零件与产品外壳模板）

## 已在真实 Rhino 8 + 官方 MCP 验证

- Rhino 8.33 启动并加载官方 Rhino MCP Platform 0.3.0。
- `MCPStart` 在 `localhost:10500` 监听。
- Router `initialize`、`tools/list`、`list_slots` 成功；动态发现 32 个工具。
- 最小探针：创建 100×60×30 mm Box → 实测尺寸/有效/闭合 → `Undo` → 对象消失。
- 项目代码真实集成：盒子验证 6/6 后撤销。
- 圆桌：底座 600×40、桌腿 180×650、桌面 1200×60；主动把桌腿偏移 25 mm。
- MCP 返回执行成功，但验证 18/19，`center_aligned_xy` 误差 25.0 mm > 0.1 mm。
- 撤销并重建后 19/19 通过；尺寸误差、两处 Z 接触误差、XY 中心误差均为 0.0 mm。

## 自动测试

- `12 passed`：原有 ModelingSpec/MCP/安全测试，加上法兰、外壳、阶梯轴、草图拉伸、圆角/倒角、放样及装配约束覆盖。
- 运行：`.venv\Scripts\python.exe -m pytest -q`

## 已在真实 Qwen + Rhino 8 验证

- 在百炼北京地域创建独立 API Key，仅授权 `qwen3.8-flash`；Key 保存在被 `.gitignore` 排除的 `.env`/`secrets`，报告和运行日志不记录 Key。
- `qwen3.8-flash` 普通对话返回 `OK`，严格 ModelingSpec JSON 通过 Pydantic，Function Calling 成功返回 `execute_modeling_spec_via_rhino_mcp`。
- FastAPI 服务真实启动；`/api/status` 同时报告 Qwen、MCP、Rhino 在线，动态适配 32 个 MCP 工具。
- 通过独立网页输入盒子提示：Qwen 生成规格和工具计划，Rhino 创建真实 Box，验证 7/7 通过；页面展示 ModelingSpec、计划和验证表。
- 问答模式真实调用 `qwen3.8-flash`，读取当前 Rhino context 后返回 4,278 字符的 Boolean Difference 分析；该模式未执行写工具。
- 圆桌完整闭环：Qwen 推导桌腿高度 650 mm；主动偏移桌腿 25 mm 后，MCP 返回成功而首次验收失败 1 项；错误报告返回 Qwen，Qwen 返回 `repair`，撤销重建后 19/19 通过。
- 修复前与修复后报告、Qwen 工具消息、Token、规格和执行结果均写入 `evaluation/runs`。
- 三案例真实对比：直接脚本基线最终 0/3（3 次脚本 payload 失败）；实验首次 2/3、最终 3/3、39/39 检查通过、自动修复 1 次。详见 `evaluation/comparison.md`；这不是普遍准确率结论。
- Rhino 真实视口截图：`screenshots/rhino-real-viewport.jpg`。

## 尚未验证

- “Codex 桌面端完全关闭”的现场观察无法由正在执行本次开发会话的 Codex 自己完成，因此这一条保持未验证；代码与进程链路检查确认运行时只有项目 Python、Qwen HTTPS、官方 Router、Rhino，且代码未引用 Codex/ChatGPT/OpenAI 服务或模型回退。
- 第一版范围中的 Move/Rotate/Copy/Mirror、Boolean/Join/Fillet 和修改当前选择对象没有纳入本次核心验收，README 未宣称已保证这些能力。

除必须由用户在关闭 Codex 后复核的独立运行观察外，核心 PoC 闭环、UI、审计记录与三案例评测均已真实完成。

## 2026-10-31 精密模式真实验证

- 固定规格经官方 Rhino MCP：法兰 10/10、顶部开口产品外壳 10/10 通过。
- 真实 `qwen3.8-flash` 中文端到端法兰：正确生成 `flange` 规格，外径 160、厚 20、中心孔 40、分度圆 110、6×Ø12；11/11 通过，耗时 24.149 s。
- 真实 `qwen3.8-flash` 中文端到端产品外壳：正确生成 `enclosure` 规格，180×120×60、壁厚 3；11/11 通过，耗时 28.016 s。
- 法兰检查包括：BBox、有效/闭合、中心孔、6 孔圆周阵列、材料保留、理论体积、图层与对象数量。
- 外壳检查包括：BBox、有效/闭合、内部空腔、底板、侧壁、理论体积、图层与对象数量。
- 视口截图：`screenshots/precision-flange-validated.jpg`、`screenshots/product-enclosure-validated.jpg`。
- 当前未实现任意特征树、装配运动副、Class-A 曲面和生产工程图，不能把受控参数化能力描述为任意精密零件建模。

## 2026-10-31 高级扩展真实验证

- 固定规格经官方 Rhino MCP：阶梯轴 8/8、草图圆角 8/8、草图倒角 8/8、自由曲面放样 8/8、三零件装配 20/20，全部通过。
- 真实 `qwen3.8-flash` 中文端到端：阶梯轴 8/8（42.354 s）、草图拉伸+竖边圆角 8/8（45.745 s）、三零件装配 20/20（47.440 s），全部通过并生成 Rhino 视口截图。
- 真实 `qwen3.8-flash` 已把自由曲面中文要求解析为合法 `loft_surface`、3 个截面；其 Rhino 固定规格执行与验收另行 8/8 通过。
- 装配检查包括三对象尺寸/有效性/闭合性/图层、XY 同心、两处 Z 接触及 Boolean Intersection 干涉体积。
- 圆角/倒角使用受控边选择器；自由曲面当前为椭圆截面放样，不宣称 Class-A 或任意 NURBS 编辑。

## 2026-11-02 一键启动器验证

- 新增 `launcher.ps1`、`双击启动_Rhino_Qwen智能体.cmd` 和 D 盘根目录快捷方式。
- 冷启动参数验证通过：启动器自动打开 Rhino 8，执行 `MCPStart`，10501 测试端口就绪后完成清理。
- 默认端口验证通过：检测 10500 已就绪后启动本地服务，Qwen、官方 MCP、Rhino 三项均在线。
- 真实网页闭环验证通过：Qwen 生成盒子规格，Rhino 建模并验收 7/7，通过后执行 Undo；耗时 32.690 s。
- 启动器日志：`logs/launcher.log`；验证记录：`evaluation/launcher_validation_2026-11-02.json`。
