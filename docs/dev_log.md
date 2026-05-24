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

真机验证：

- 用户已确认左手/右手自动旋转方向正确。

## 2026-05-24 阶段 3C-2：评分页双摇 good

完成内容：

- 只在评分页启用双摇动作，不影响单词页、释义页、例句页或 done 页。
- 使用加速度模长检测摇晃峰值，两次峰值在短窗口内出现时触发。
- 触发后将当前评分设为 `good`，立即调用现有提交流程进入下一个单词。
- 保留下一词单词页 Button B 回到上一词评分页重新评分的机制。
- 加入冷却时间，避免一次剧烈摇晃连续提交多张卡片。
- 串口打印 `Shake good word=... magnitude=...`，方便真机验证阈值是否合适。

测试结果：

- 仓库级 Python 全量测试通过 55 个测试：
  `$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONPATH='src'; python -m unittest discover -s tests -v`
- 固件编译通过：
  `cd C:\Users\ASUS\Documents\M5Stick\firmware`
  `pio run`

下一步：

- 上传到真实 M5Stick C Plus，在评分页测试双摇是否稳定触发 `good`。
- 如果太灵敏或太迟钝，调节 `kShakeThreshold`、`kShakeReleaseThreshold`、`kShakeWindowMs` 和 `kShakeCooldownMs`。

真机验证：

- 用户已确认评分页双摇 `good` 在真实 M5Stick C Plus 上测试成功。

## 2026-05-24 阶段 4：PC 与 M5Stick 最小同步

完成内容：

- 增加固件配置模板 `firmware/include/secrets.example.h`。
- 保持私有配置 `firmware/include/secrets.h` 不进入 Git。
- 增加 PC 端设备同步接口：
  - `GET /api/device/tasks?limit=20`
  - `POST /api/device/reviews`
- 增加固件 Wi-Fi 与 HTTP 同步流程：
  - 使用 `secrets.h` 中的 2.4 GHz Wi-Fi 配置联网。
  - 启动时从 PC 后端拉取待复习卡片。
  - Wi-Fi 或同步失败时回退到内置示例卡片。
  - 在 RAM 中排队评分结果。
  - 提交评分后向 PC 后端上传待提交结果。
  - 上传失败或服务端响应不符合预期时保留待提交结果。
- 将固件启动日志更新为 `StickWords Stage 4 boot`。
- 更新交接文档，补充 Stage 4 的配置、编译、上传、验证流程和已知限制。

验证结果：

- `$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONPATH='src'; python -m unittest discover -s tests -v`
- 通过 66 个测试。
- `cd C:\Users\ASUS\Documents\M5Stick\firmware`
- `pio run`
- PlatformIO 固件编译通过。

遇到的问题与决策：

- M5Stick 不能用 `localhost` 访问 PC 后端；`STICKWORDS_SERVER_URL` 必须填写 PC 的局域网 IPv4 地址。
- 本阶段不做自动发现 PC，需要手动编辑 `secrets.h`。
- 待上传评分仍然只保存在 RAM 中；如果断电发生在上传成功之前，这部分评分会丢失。
- 固件 JSON 解析器只面向当前后端响应格式，刻意保持小而有界，不作为通用 JSON 解析器使用。
- 成功上传后的重新评分在本阶段会作为新的 review event 发送。

下一步：

- 在 PC 端运行 `python app.py --host 0.0.0.0 --port 8000 --data-dir data`。
- 在 `firmware\include\secrets.h` 中填写真实 2.4 GHz Wi-Fi 和 PC 局域网地址。
- 上传到真实 M5Stick C Plus，确认串口日志出现 Wi-Fi 连接、任务拉取和评分上传。
- 在 PC 管理页或 `data\vocab.csv` 中确认 M5Stick 提交的评分已经生效。

## 2026-05-24 Stage 4 polish: 管理页显示 M5Stick LAN URL

完成内容：

- 调整 PC Web 后端的 `server_url` 生成逻辑。
- 当用户从 `localhost` 或 `127.0.0.1` 打开 `/admin` 时，管理页会优先显示自动探测到的局域网 IPv4 URL，例如 `http://192.168.x.x:8000`。
- 如果局域网地址探测失败，则回退显示当前访问地址。
- 如果用户已经通过局域网 IP 打开管理页，则保持该地址不变。

测试结果：

- 先写入失败测试，确认旧实现不支持 `lan_host_lookup` 注入点。
- Web 测试通过 20 个测试：
  `$env:PYTHONPATH='src'; python -m unittest tests.test_web -v`
- 仓库级 Python 全量测试通过 69 个测试：
  `$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONPATH='src'; python -m unittest discover -s tests -v`

下一步：

- 启动 PC 后端后，在管理页查看 `M5Stick server URL`。
- 将这个 URL 写入 `firmware\include\secrets.h` 的 `STICKWORDS_SERVER_URL`，再上传固件做真机同步验证。

## 2026-05-24 Stage 4 polish: CSV 文件导入与管理页样式

完成内容：

- 管理页 Import CSV 表单增加 `.csv` 文件选择框。
- 保留 CSV 文本粘贴作为备用入口。
- 后端支持 `multipart/form-data` CSV 文件上传，文件内容优先，未选择文件时使用文本框内容。
- 管理页字体改为 `Segoe UI`，并整理为浅色工具台风格：分区面板、清晰统计卡片、表格横向滚动、按钮和输入框样式统一。
- M5Stick 中文乱码暂不改动，后续作为固件字体专项处理。

测试结果：

- 先写入失败测试，确认旧页面没有文件选择控件、旧后端不能处理 multipart CSV 文件上传。
- 页面渲染测试通过 3 个测试：
  `$env:PYTHONPATH='src'; python -m unittest tests.test_admin_views -v`
- Web 路由测试通过 21 个测试：
  `$env:PYTHONPATH='src'; python -m unittest tests.test_web -v`

下一步：

- 在浏览器刷新 `/admin`，用文件选择框导入真实 CSV。
- 继续观察 M5Stick 同步和评分上传链路。

## 2026-05-24 Stage 4 polish: M5Stick 内容页屏幕利用率

完成内容：

- 将固件内容页每页容量从 58 字符提高到 112 字符。
- 内容页显式从屏幕左上方 `(6, 6)` 开始绘制，减少下半屏空白造成的不必要翻页。
- 保留释义页和例句页的多页机制，长内容仍然可以继续翻页。
- 中文乱码暂不处理，仍作为后续字体/字库专项。

测试结果：

- 先写入失败测试，确认旧固件内容页容量低于 100 字符。
- 固件测试通过 15 个测试：
  `$env:PYTHONPATH='src'; python -m unittest tests.test_firmware_project -v`
- 仓库级 Python 全量测试通过 71 个测试：
  `$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONPATH='src'; python -m unittest discover -s tests -v`
- 固件编译通过：
  `cd C:\Users\ASUS\Documents\M5Stick\firmware`
  `pio run`

下一步：

- 上传到真实 M5Stick C Plus，观察 meaning/example 页面是否更充分利用屏幕高度。
- 如果仍然偏保守，可以继续微调 `kContentPageChars`；如果出现页面文字压到底部太满，则回调到 96 左右。

## 2026-05-24 Stage 4 polish: CSV 重复行提示

完成内容：

- 导入 CSV 时记录同一个文件内部重复出现的 `word` 行数。
- 重复行不算失败，仍然保持“最后一行覆盖前面内容”的现有规则。
- 网页导入成功后的提示增加 `duplicate_rows=N`，仅在存在重复行时显示。

测试结果：

- 先写入失败测试，确认旧导入结果没有 `duplicate_rows` 字段，旧网页提示不显示重复行数量。
- Importer 测试通过 5 个测试：
  `$env:PYTHONPATH='src'; python -m unittest tests.test_importer -v`
- Web 路由测试通过 22 个测试：
  `$env:PYTHONPATH='src'; python -m unittest tests.test_web -v`
- Service 测试通过 7 个测试：
  `$env:PYTHONPATH='src'; python -m unittest tests.test_service -v`

下一步：

- 后续可以把导入结果展示做成更清晰的结果面板，而不是只依赖 URL message。

## 2026-05-24 Stage 4 polish: Words table 搜索与简化

完成内容：

- 移除管理页 Words table 中的 `Edit` 列和每行内联编辑表单。
- 保留 `Suspend` 列，继续支持安全地停用不想复习的单词。
- 增加表格搜索框，浏览器端实时过滤单词行。
- 搜索范围包括 `word`、`meaning`、`example` 和 `status`。
- 后端编辑接口暂时保留，只是不再出现在常用网页界面中。

测试结果：

- 先写入失败测试，确认旧页面没有搜索框且仍显示编辑列。
- 页面渲染测试通过 4 个测试：
  `$env:PYTHONPATH='src'; python -m unittest tests.test_admin_views -v`
- Web 路由测试通过 22 个测试：
  `$env:PYTHONPATH='src'; python -m unittest tests.test_web -v`

下一步：

- 真实使用中观察搜索框是否足够；如果词库很大，再考虑服务端分页或后端搜索。

## 2026-05-24 Stage 4 polish: Quick Add 快速加词工具

完成内容：

- 检查 `C:\Users\ASUS\Documents\quick-add-test` 原型，确认其目标是从 Obsidian/Chrome 复制例句后快速添加单词。
- 将原型思路整合进主项目的 `scripts\quick_add.py`，而不是直接复制其独立 CSV 写入逻辑。
- 新增 `StickWordsService.add_or_update_word()`，让快速加词和网页/同步共用同一套词库规则。
- 重复单词按大小写不敏感匹配并更新释义、例句和更新时间，同时保留已有复习进度。
- Quick Add 支持从剪贴板或 `--example` 读取例句，支持双击例句中的词，也支持手动输入目标词。
- 如果设置了 `DEEPSEEK_API_KEY`，可调用 DeepSeek 生成 Collins COBUILD 风格英文释义；未设置时仍可手动填写释义。
- 新增 `scripts\quick_add.bat` 作为 Windows 启动入口。
- 新增 `scripts\setup_quick_add_hotkey.ps1`，用于创建桌面快捷方式并绑定 `Ctrl+Alt+W`。

测试结果：

- 先写入失败测试，确认主服务层没有 `add_or_update_word()` 且 quick add 脚本不存在。
- Quick Add 测试通过 2 个测试：
  `$env:PYTHONPATH='src'; python -m unittest tests.test_quick_add -v`
- Service 测试通过 9 个测试：
  `$env:PYTHONPATH='src'; python -m unittest tests.test_service -v`

遇到的问题与决策：

- 原型自带 CSV/ID 逻辑可以工作，但如果直接复制，会和主项目的导入、重复词、复习进度规则形成两套真相。
- 因此本次只迁移交互和 DeepSeek 调用思路，持久化统一走 `StickWordsService`。
- 测试不调用真实 DeepSeek API，避免依赖网络和 API key。

下一步：

- 真实运行 `scripts\setup_quick_add_hotkey.ps1` 创建快捷方式。
- 从 Obsidian 或 Chrome 复制一句英文例句后，用 `Ctrl+Alt+W` 验证日常加词手感。

## 2026-05-24 Stage 4 polish: M5Stick 英文词边界排版

完成内容：

- 将 M5Stick 内容页从固定字符数分页改为按英文 token 排版。
- 使用 `M5.Lcd.textWidth()` 估算下一个词能否放入当前行，放不下时整词换行。
- 分页状态从页码改为当前页起始字符位置，Button A 翻到下一页和 Button B 返回上一页都通过同一套排版模拟计算。
- 保留释义页和例句页的单线流程，不改变评分页、双摇 `good` 或重新评分机制。
- 对极长单词保留兜底的字符级切分，避免单个超长 token 完全无法显示。

测试结果：

- 先写入失败测试，确认旧固件仍使用 `kContentPageChars` 固定字符数分页，缺少词边界排版函数。
- 固件测试通过 16 个测试：
  `$env:PYTHONPATH='src'; python -m unittest tests.test_firmware_project -v`
- 仓库级 Python 全量测试通过 79 个测试：
  `$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONPATH='src'; python -m unittest discover -s tests -v`
- PlatformIO 固件编译通过：
  `C:\Users\ASUS\.platformio\penv\Scripts\pio.exe run`

遇到的问题与决策：

- Codex shell 一开始找不到 `pio`，后来确认实际路径是 `C:\Users\ASUS\.platformio\penv\Scripts\pio.exe`。
- 首次直接运行时因沙箱不能写入 `.platformio\platforms.lock` 失败，授权后编译通过。
- 本次只处理英文排版；中文乱码仍属于字体/字库问题，暂不合并处理。

下一步：

- 上传固件到真实 M5Stick C Plus，重点观察 meaning/example 页是否还会把普通英文单词拆成两行。
- 如果页面显得过密或 `...` 位置影响阅读，再微调 `kContentLineHeight` 或内容区域边界。

## 2026-05-24 Stage 4 bugfix: 移除正式固件测试词 fallback

完成内容：

- 修复 M5Stick 同步失败或无 due cards 时显示早期 3 个测试词的问题。
- 移除正式固件中的 `abandon / benefit / curious` 内置样例卡片。
- 将 `syncedCardCount == 0` 明确解释为“没有可复习卡片”，不再作为样例模式开关。
- 新增状态页：Wi-Fi 失败显示 `WiFi failed / check network`，同步失败显示 `Sync failed / check server`，无到期卡片显示 `No due cards`。
- 保留现有同步成功后的复习流程、评分流程、双摇 `good` 和重新评分机制。

测试结果：

- 先写入失败测试，确认旧固件仍含 `kCards[]` 和 `using samples`，且 `activeCardCount()` 会回退到样例卡片数量。
- 固件测试通过 17 个测试：
  `$env:PYTHONPATH='src'; python -m unittest tests.test_firmware_project -v`
- PlatformIO 固件编译通过：
  `C:\Users\ASUS\.platformio\penv\Scripts\pio.exe run`

遇到的问题与决策：

- 根因是 `syncedCardCount == 0` 同时代表“同步失败/无数据”和“使用样例数据”，状态语义混在一起。
- 本次只修复误显示测试词；离线状态下根据本地缓存和 due date 继续复习，需要后续单独设计本地缓存与时间机制。

下一步：

- 上传固件到真实 M5Stick C Plus，验证在 PC 后端关闭、Wi-Fi 错误、无 due cards 三种情况下都不会显示测试词。
