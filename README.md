# Rhino Qwen Precision Agent

基于阿里云百炼 Qwen 的独立 Rhino 8 精确建模智能体 PoC。运行时只有本地 Python 服务、Qwen API、McNeel 官方 Rhino MCP Platform 和 Rhino；不调用 Codex、ChatGPT、OpenAI 模型或其他模型回退。

## 启动

### 一键启动（推荐）

双击 `双击启动_Rhino_Qwen智能体.cmd`。启动器会自动：

1. 查找并打开 Rhino 8；
2. 在 Rhino 中执行 `MCPStart`，等待 10500 端口就绪；
3. 启动本地 Qwen 建模服务并检查 Qwen、MCP、Rhino 三项连接；
4. 打开 `http://127.0.0.1:8765` 对话页面。

随后直接在网页输入中文建模要求，Rhino 会同步生成并验证模型。启动日志位于 `logs/launcher.log`，所有项目运行文件仍保存在 D 盘。

### 手动启动

1. 在 Rhino 8 运行 `MCPStart`，端口使用 `10500`。
2. 复制 `.env.example` 为 `.env`，填写有效的北京地域百炼 `QWEN_API_KEY`。不要提交 `.env`。
3. 双击或在 PowerShell 运行：

   ```powershell
   D:\codex\RhinoQwenPrecisionAgent\start.ps1
   ```

4. 浏览器访问 `http://127.0.0.1:8765`。

`start.ps1` 的虚拟环境、pip 缓存、日志和临时目录都位于 D 盘。服务只监听 `127.0.0.1`。

## 闭环

```text
中文要求 → Qwen ModelingSpec → Pydantic/JSON Schema
→ Qwen Function Calling 批准执行/修复
→ 确定性脚本经官方 Rhino MCP run_python 执行
→ 尺寸/实体/装配验证 → 最多两轮修复 → JSON/JSONL 审计记录
```

程序启动时动态读取官方 MCP `tools/list` 并生成 Qwen-compatible 工具 Schema。第一版采用一个受控的高层 Function Call 来批准已验证规格，随后由本地确定性执行器生成受限 Rhino Python；这避免把 Qwen 任意脚本直接交给 Rhino。

## 支持范围

- Box、Cylinder、Sphere；图层、名称、对象颜色。
- 圆桌等基础组合体；尺寸、中心共轴、Z 接触约束。
- 精密法兰模板：外径、厚度、中心通孔、螺栓分度圆、孔径与等分孔数；通过确定性布尔差生成一个闭合实体。
- 产品外壳模板：顶部开口矩形外壳，宽/深/高及等厚底板和四壁。
- 阶梯轴：任意多段直径/长度，沿 Z 轴生成单一旋转闭合实体。
- 任意闭合多边形草图拉伸；可对全部、竖向或横向边执行圆角或倒角。
- 椭圆截面自由曲面放样：支持截面高度、宽深、XY 偏置与旋转角。
- 多零件装配：中心对齐、Z 接触、最小间隙和实体干涉检查。
- Bounding Box、对象存在/数量、类型语义、图层、`IsValid`、`IsSolid` 验证。
- 法兰中心孔、圆周孔阵列、材料保留和理论体积验证；外壳空腔、底板、侧壁和理论体积验证。
- 问答只读模式；停止后续轮次；Rhino Undo。
- 真实 MCP 返回成功但验收失败时，结构化报告返回 Qwen，再撤销并最小重建。

当前“精密零件/产品建模”仍是受控参数化能力，不等于任意机械 CAD。已支持上述阶梯轴、闭合多边形拉伸、边圆角/倒角、多零件约束验收和椭圆截面放样；尚未保证任意特征树、装配运动副、NURBS 控制点编辑、SubD、Class-A 曲面、照片到生产模型或工程图/GD&T。项目使用 Qwen API，不代表训练了 Qwen。

示例：

```text
创建一个精密法兰：外径160 mm，厚度20 mm，中心通孔直径40 mm，
螺栓分度圆直径110 mm，均布6个直径12 mm的通孔。
```

```text
创建一个顶部开口的产品外壳：外形宽180 mm、深120 mm、高60 mm，
底部和四壁厚度均为3 mm。
```

```text
创建三段阶梯轴：Ø60×30、Ø40×50、Ø25×35 mm；轴线沿 Z 轴。
```

```text
用闭合草图点(-50,-30)、(50,-30)、(50,30)、(-50,30)拉伸20 mm，
四条竖边做5 mm圆角。
```

## 安全边界

- R0 读取自动执行；R1 创建可撤销；R2 修改显示计划；R3 删除/保存/关闭默认拒绝；R4 生成脚本禁止 Shell、网络、进程和凭据访问。
- 每次创建使用 Rhino Undo 记录；候选结果验证失败时先撤销，再修复。
- Key 只从环境变量或 `.env` 读取，日志不记录 Key。
- Qwen 不可用时显示真实错误并停止，不切换其他模型。

## 目录

- `app/`：服务、Qwen、MCP、规格、执行、验证、修复、UI。
- `schemas/`：ModelingSpec JSON Schema。
- `tests/`：单元测试与真实 Rhino MCP 集成脚本。
- `evaluation/`：固定案例、运行记录和小样本对比。
- `screenshots/`：演示截图（不含敏感信息）。

当前验证状态见 `TEST_REPORT.md`。上游版本与工具 Schema 见 `UPSTREAM_LOCK.md`。
