# StickWords 开发日志

## 2026-05-23

完成内容：

- 确认第一版采用“PC 负责算法，M5Stick 负责显示和反馈”的架构。
- 确认 PC 网页管理页负责词库添加、编辑、停用和 CSV 批量导入。
- 确认 Wi-Fi HTTP 作为日常同步方式，USB 串口作为首次配置和故障恢复方式。
- 确认 CSV 字段、重复导入规则和软删除规则。
- 确认轻量 SM-2 复习算法。
- 确认 M5Stick 横屏、左右手自动旋转、Button A/Button B、双摇“记住”、上一题重新评分和异常断电恢复设计。
- 创建 `docs/roadmap.md` 和 `docs/design.md`。

测试结果：

- 当前阶段为设计文档阶段，尚未实现代码。

遇到的问题：

- M5Stick 按键数量有限，不能照搬手机应用交互。
- M5Stick 横握时有左右手两种方向，需要自动旋转或固定方向设置。
- 评分后撤销不能用 3 秒等待窗口，否则影响手感。
- PC 后端关闭后需要保证重新启动仍可继续同步。

解决方式：

- 使用单线复习流程降低交互分叉。
- Button A 统一为继续/确认，Button B 统一为返回/重新评分。
- 双摇提交“记住”后立即进入下一词，在下一词单词页按 Button B 回上一词评分页重新评分。
- PC 后端做成无状态服务，长期数据保存到 CSV，M5Stick 本地保存待上传结果。

下一步：

- 用户 review `docs/roadmap.md` 和 `docs/design.md`。
- 如果确认无误，再进入实现计划阶段。

## 2026-05-23 命名决策

完成内容：

- 项目正式命名为 StickWords。
- 为降低商标混淆风险，公开项目名和仓库名不使用 `Anki`。

测试结果：

- 仅更新文档，未涉及代码。

下一步：

- 后续 GitHub 仓库名优先使用 `stickwords`。

## 2026-05-23 阶段 1：PC 后端核心

完成内容：

- 实现 StickWords PC 后端核心 Python 包。
- 实现 CSV 词库读写。
- 实现 CSV 批量导入和重复单词更新规则。
- 实现轻量 SM-2 复习算法。
- 实现今日任务生成。
- 实现 `review_event_id` 幂等处理。
- 增加阶段 1 集成测试。
- 增加仓库内测试临时目录，避免 Windows 沙箱下 `%TEMP%` 权限不稳定。

测试结果：

- `$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONPATH='src'; python -m unittest discover -s tests -v`
- 通过 24 个测试。

遇到的问题：

- 子代理额度在 Task 4 代码质量审查时耗尽，后续改为主线 inline 执行。
- Windows 沙箱下，Python `TemporaryDirectory()` 创建的目录可能无法被同一 Python 进程写入。

解决方式：

- 保留每个任务的规格检查和质量检查，但由主线执行后续审查。
- 新增 `tests/temp_utils.py`，将测试临时目录放到仓库内 `.test-tmp/`，并在 `.gitignore` 中忽略。

下一步：

- 进入阶段 2：PC 网页管理页和 `start_stickwords.bat`。

## 2026-05-23 阶段 2：PC 网页管理页

完成内容：

- 完成 StickWords 服务层，统一封装词库加载、保存、添加、编辑、停用、导入和状态统计。
- 完成 `/admin` 网页管理页。
- 支持添加、编辑、停用单词。
- 支持通过 textarea 粘贴 CSV 批量导入。
- 完成 `/api/status` JSON 状态接口。
- 完成 `app.py` 和 `start_stickwords.bat` 启动入口。
- 增加阶段 2 Web 管理页集成测试，覆盖添加单词、textarea CSV 导入、状态接口和最终词库顺序。

测试结果：

- `$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONPATH='src'; python -m unittest discover -s tests -v`
- 通过 48 个测试。

遇到的问题：

- 先不引入 Flask/FastAPI，避免在早期阶段增加依赖和部署复杂度。
- multipart 文件上传会增加表单解析和测试复杂度。
- 表单路由和 HTML 表单契约需要保持一致，否则页面提交和后端处理容易错位。
- 空表单必须在 route 层拦截，避免写入坏数据。

解决方式：

- 使用标准库 WSGI 实现本阶段 HTTP 管理入口。
- CSV 批量导入先采用 textarea 粘贴文本，降低上传解析复杂度。
- 增加 route 层必填字段校验。
- 增加 Web 路由测试和阶段 2 集成测试，覆盖核心管理流程。

下一步：

- 阶段 3 M5Stick UI 原型。

## 2026-05-23 阶段 3A：M5Stick 硬件连通验证

完成内容：

- 补充 `docs/stage3a_platformio_quickstart.md`，说明 PlatformIO 编译、上传、串口监视器和真机屏幕检查流程。
- 更新交接文档，记录 Stage 3A 已通过 PlatformIO 真机验证。
- 明确 Stage 3A 的范围只验证屏幕、串口、Button A、Button B 和 IMU 加速度读数。
- 明确本阶段不包含 Wi-Fi、vocabulary sync、review flow。

测试结果：

- 仓库级 Python 测试已通过 51 个测试：
  `$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONPATH='src'; python -m unittest discover -s tests -v`
- 用户在 VSCode PlatformIO Terminal 中完成真机验证：
  `cd C:\Users\ASUS\Documents\M5Stick\firmware`
  `pio run`
  `pio run --target upload --upload-port COM5`
  `pio device monitor --port COM5`
- `pio run` 编译成功。
- `pio run --target upload --upload-port COM5` 上传成功，设备识别为 ESP32-PICO-D4。
- 串口监视器成功显示 IMU 数值变化，以及 `Button A pressed/released`、`Button B pressed/released`。

遇到的问题：

- 第一版固件使用 M5StickCPlus 专用库；如果后续出现编译或硬件兼容性问题，再考虑切换到 M5Unified。
- Codex 环境不一定能访问 PlatformIO、依赖下载或真实 USB 设备，不能把 Codex 内部验证等同于真机验证。
- PlatformIO 自动上传时误选 COM1，导致 `Failed to connect to ESP32: No serial data received`。

解决方式：

- 保持 Stage 3A 为最小硬件连通检查，先用 M5StickCPlus 专用库完成屏幕、串口、按键和 IMU 验证。
- 将真实硬件验证拆成人工检查项：编译、上传、串口 boot log、Button A/B 日志、IMU 数值变化、屏幕状态页。
- 使用 `--upload-port COM5` 和 `--port COM5` 明确指定 M5Stick 的 USB 串口。

下一步：

- 进入 Stage 3B：使用假数据实现最小复习 UI 状态机。

## 2026-05-24 阶段 3B：按键版最小复习 UI

完成内容：

- 将 Stage 3A 硬件检查固件升级为 Stage 3B 本地复习 UI 原型。
- 内置 3 张假数据卡片，不连接 PC 后端。
- 实现单线流程：单词页 -> 释义摘要页 -> 完整例句页 -> 评分页 -> 下一词。
- 评分页支持 Button A 短按循环 `forgot / hard / good`，Button A 长按提交。
- 实现下一词单词页 Button B 回上一词评分页重新评分。
- 重新评分覆盖 RAM 中上一条评分结果，并打印串口日志。
- 完成 3 张卡片后显示 done 页面。

测试结果：

- 仓库级 Python 全量测试：
  `$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONPATH='src'; python -m unittest discover -s tests -v`
- 固件编译：
  `cd C:\Users\ASUS\Documents\M5Stick\firmware`
  `pio run`

遇到的问题：

- Stage 3B 仍是假数据和 RAM 结果，重启后评分消失。
- 为保持手感，评分提交后不加声音、震动或停顿，只通过串口记录结果。

解决方式：

- 使用明确的 Page enum、Rating enum 和 RAM ReviewResult 数组组织状态机。
- 只在 UI 状态变化时重绘屏幕，降低闪烁。

下一步：

- 在真实 M5Stick C Plus 上验证 Stage 3B 交互。
- 通过后进入 Stage 3C。

## 2026-05-24 阶段 3B：M5Stick UI 空间优化

完成内容：

- 移除 M5Stick 复习界面顶部的 `StickWords` 标题、页码/单词头部信息和底部按键提示。
- 单词页改为只显示居中的大号单词。
- 释义+例句摘要页、完整例句页和评分页使用更大的正文显示，减少下方空白。
- 评分页保留当前单词，方便确认正在评分的卡片。
- 保持 Button A / Button B 的复习交互不变。

测试结果：

- 仓库级 Python 全量测试通过 52 个测试：
  `$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONPATH='src'; python -m unittest discover -s tests -v`
- 固件编译通过：
  `cd C:\Users\ASUS\Documents\M5Stick\firmware`
  `pio run`

下一步：

- 上传到真实 M5Stick C Plus，确认小屏幕 UI 观感和字号是否舒适。

## 2026-05-24 阶段 3B：释义与例句分页流程

完成内容：

- 将复习流程调整为：单词页 -> 释义页 1..N -> 例句页 1..N -> 评分页。
- 第二页不再重复显示单词，只显示释义内容。
- 例句页不再和释义页混排，例句过长时按需进入下一页。
- 释义和例句共用内容分页函数，为后续真实 CSV 长释义、中文释义或更长例句预留扩展口子。
- Button B 仍保持返回上一页；下一个单词的单词页仍可返回上一个单词评分页重新评分。

测试结果：

- 仓库级 Python 全量测试通过 53 个测试：
  `$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONPATH='src'; python -m unittest discover -s tests -v`
- 固件编译通过：
  `cd C:\Users\ASUS\Documents\M5Stick\firmware`
  `pio run`

下一步：

- 上传到真实 M5Stick C Plus，确认释义页和例句分页的阅读节奏是否合适。

## 2026-05-24 阶段 3C-1：左右手横屏自动旋转

完成内容：

- 启用 M5Stick C Plus 的 IMU，加回加速度读取。
- 固件启动日志升级为 `StickWords Stage 3C boot`。
- 根据 X 轴加速度稳定方向在横屏 `rotation 1` 和 `rotation 3` 之间切换。
- 加入 500 ms 稳定时间，降低手持轻微晃动导致的方向抖动。
- 方向变化时只重绘当前页面，不改变当前复习进度、分页位置或评分状态。
- 串口打印 `Orientation rotation=... ax=... ay=... az=...`，方便真机调试方向映射。

测试结果：

- 仓库级 Python 全量测试通过 54 个测试：
  `$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONPATH='src'; python -m unittest discover -s tests -v`
- 固件编译通过：
  `cd C:\Users\ASUS\Documents\M5Stick\firmware`
  `pio run`

遇到的问题：

- 如果设备完全平放，只在桌面平面内旋转 180 度，加速度计无法区分左右手方向；本阶段按真实手持时的稳定倾角判断。
- 方向映射可能需要真机确认。如果左手/右手切换后方向反了，只需要对调 `detectLandscapeRotation()` 中 `1` 和 `3` 的返回值。

下一步：

- 上传到真实 M5Stick C Plus，检查左手/右手持握时是否自动转正。
