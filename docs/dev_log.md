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
