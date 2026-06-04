# StickWords 设计

## 设计原则

- 不编造硬件能力，具体按键、库函数和传感器行为要在开发时验证。
- 公开项目名使用 StickWords，避免在仓库名和应用名中使用 `Anki`。
- PC 是“大脑”和主数据源，M5Stick 是轻量复习终端。
- CSV 是第一版的长期数据源。
- 设备端交互要适合小屏幕、少按键和横握使用。
- 网络和电源都可能中断，必须保存会话进度和待上传结果。

## 系统架构

系统分为三块：

```text
M5Stick C Plus
  - 菜单
  - 单词复习界面
  - 评分交互
  - 当天任务缓存
  - 待上传结果队列
  - 会话恢复状态

PC 后端
  - CSV 词库
  - 轻量 SM-2 复习算法
  - 今日任务生成
  - 复习结果保存
  - HTTP API
  - USB 配置/救援通道

PC 网页管理页
  - 添加单词
  - 编辑释义和例句
  - 停用单词
  - CSV 批量导入
  - 查看复习状态
  - USB 配置向导
```

关键边界：

- M5Stick 不修改词库。
- M5Stick 不计算下一次复习日期。
- M5Stick 只下载任务、显示卡片、收集评分、上传结果。
- PC 后端关闭后重新启动，仍从磁盘 CSV 恢复状态。

## 数据流

日常使用：

```text
1. 用户在 PC 网页端维护词库。
2. PC 后端根据 due_at 和新词额度生成今日任务。
3. M5Stick 通过 Wi-Fi 请求今日任务。
4. M5Stick 本地缓存当天任务。
5. 用户在 M5Stick 上复习。
6. M5Stick 上传评分结果。
7. PC 后端更新 CSV 里的复习状态。
```

断网时：

```text
1. 如果 M5Stick 已缓存当天任务，可以继续复习。
2. 复习结果先存入本地待上传队列。
3. 网络恢复后自动或手动同步。
4. PC 后端按提交结果更新 CSV。
```

PC 后端关闭时：

```text
1. M5Stick 无法同步新任务。
2. M5Stick 可以继续复习已缓存任务。
3. 新评分进入本地待上传队列。
4. PC 后端重新启动后，M5Stick 再上传待处理结果。
```

## CSV 数据结构

主数据文件：

```text
data/vocab.csv
```

字段：

```csv
id,word,meaning,example,status,added_at,last_reviewed_at,due_at,review_count,ease,interval_days,lapses,updated_at
```

字段含义：

```text
id                稳定唯一 ID，后端生成
word              英文单词
meaning           中文释义
example           例句
status            new / learning / review / suspended
added_at          加入时间
last_reviewed_at  上次复习时间
due_at            下次应复习时间
review_count      总复习次数
ease              熟悉度系数
interval_days     当前间隔天数
lapses            忘记次数
updated_at        内容或状态更新时间
```

导入 CSV 可以只包含：

```csv
word,meaning,example
```

新增单词时，后端自动补齐：

```text
id = 生成唯一 ID
status = new
added_at = 当前时间
due_at = 当前时间
review_count = 0
ease = 2.5
interval_days = 0
lapses = 0
updated_at = 当前时间
```

重复单词规则：

```text
如果 word 不存在：
  新增单词

如果 word 已存在：
  更新 meaning
  更新 example
  更新 updated_at
  保留原有复习状态
```

网页删除默认是停用：

```text
status = suspended
```

第一版不默认物理删除词条。

## 复习算法

M5Stick 只提交三档评分：

```text
忘记 = forgot
模糊 = hard
记住 = good
```

初始状态：

```text
status = new
ease = 2.5
interval_days = 0
review_count = 0
lapses = 0
due_at = added_at
```

评分更新规则：

```text
forgot:
  lapses += 1
  ease = max(1.3, ease - 0.2)
  interval_days = 0
  due_at = now + 10 minutes 或 next_session
  status = learning

hard:
  ease = max(1.3, ease - 0.05)
  interval_days = max(1, round(interval_days * 1.2))
  due_at = now + interval_days days
  status = review

good:
  ease = min(3.0, ease + 0.05)
  如果 interval_days == 0: interval_days = 1
  否则 interval_days = round(interval_days * ease)
  due_at = now + interval_days days
  status = review
```

今日任务生成：

```text
1. 选择 due_at <= now 且 status != suspended 的复习词。
2. 最多取 20 个到期词。
3. 再选择 status = new 的新词。
4. 最多取 5 个新词。
5. 合并后返回给 M5Stick。
```

排序：

```text
到期复习词优先。
更早 due_at 的词优先。
新词排在后面。
```

## M5Stick 交互设计

硬件命名：

```text
Button A = 主键
Button B = 主键上方的可编程侧键
Power 键 = 电源/复位相关按键，不作为应用操作键
```

设备姿态：

```text
默认横屏使用。
支持左手和右手横握自动旋转。
姿态稳定约 0.8-1 秒后才切换方向。
设置中保留：自动 / 固定左手 / 固定右手。
```

复习单线流程：

```text
1. 单词页
   Button A 短按 -> 释义 + 例句摘要页

2. 释义 + 例句摘要页
   Button A 短按 -> 完整例句页

3. 完整例句页
   Button A 短按 -> 下一屏
   到达例句末尾后 Button A 短按 -> 评分页

4. 评分页
   左右倾斜 -> 切换 忘记 / 模糊 / 记住
   Button A 短按 -> 提交当前评分，立即进入下一词
   连续摇晃两下 -> 直接提交“记住”，立即进入下一词
```

返回与重新评分：

```text
Button B 短按 = 返回。

在当前卡片中间页面：
  Button B 短按返回上一页。

评分完成后进入下一词的单词页：
  Button B 短按回到上一词评分页。
  重新评分后覆盖上一词的本地待上传结果。
```

长按：

```text
Button A 长按 = 回主菜单或结束本轮。
```

体感使用范围：

```text
1. 自动屏幕方向。
2. 评分页左右倾斜选择评分。
3. 评分页双摇直接提交“记住”。
```

其他页面不使用体感，降低误触发。

## 会话恢复与异常断电

M5Stick 本地需要持久化：

```text
task_date
cards
current_index
current_step
pending_reviews
last_reviewed_card_for_undo
server_url
wifi_config
```

保存时机：

```text
成功同步今日任务后。
每次页面切换后。
每次评分后。
待上传队列变化后。
正常退出复习时。
```

下次进入复习时，如果发现未完成会话：

```text
检测到未完成复习
Button A：继续
Button B：返回主菜单
```

异常断电恢复：

```text
如果上次停在单词/摘要/完整例句/评分页：
  回到同一张卡片对应页面。

如果上次刚评分并进入下一词：
  回到下一词单词页。
  Button B 仍可回上一词评分页重新评分。

如果有待上传结果：
  优先尝试上传。
  上传失败则继续保留。
```

缓存可靠性：

```text
使用两个状态槽，例如 session_a 和 session_b。
每次写入带 version、saved_at 和 checksum。
启动时读取最新且校验通过的一份。
```

第一版目标是显著降低断电导致的数据损坏风险，但不承诺断电瞬间正在写入时 100% 不丢最后一步。

## HTTP API

第一版接口：

```text
GET /api/health
  M5Stick 检查 PC 后端是否在线。

GET /api/tasks/today
  返回今日任务：到期复习词 + 今日新词。

POST /api/reviews
  M5Stick 上传复习结果队列。

GET /api/status
  返回词库数量、今日待复习数量、最近同步状态等。
```

复习结果格式包含唯一事件 ID：

```json
{
  "review_event_id": "device-id + timestamp + word-id",
  "word_id": "...",
  "rating": "good",
  "reviewed_at": "..."
}
```

PC 后端记录已处理事件，避免重复上传导致重复计数：

```text
data/review_events.csv
```

## PC 网页管理页

网页管理页是 PC 端控制台：

```text
/admin
```

功能：

```text
查看后端运行状态。
查看词库数量。
查看今日待复习数量。
添加单词。
编辑释义和例句。
停用单词。
CSV 批量导入。
导出和备份 vocab.csv。
查看最近复习记录。
查看 M5Stick 最近同步时间。
显示建议写入 M5Stick 的局域网地址。
USB 配置向导。
```

启动方式：

```text
start_stickwords.bat
```

双击后：

```text
1. 启动 python app.py。
2. 自动打开浏览器到 http://localhost:8000/admin。
```

注意：

```text
app.py 没启动时，网页管理页无法打开。
网页管理页可以集成业务操作，但不能在后端未启动时启动后端。
```

后续可以升级为 Windows 开机自启动、后台服务或托盘小图标。

## USB 配置与救援

USB 串口只做配置和救援，不做日常完整同步。

PC 工具向 M5Stick 发送 JSON 行：

```json
{"type":"set_wifi","ssid":"...","password":"..."}
{"type":"set_server","url":"http://192.168.x.x:8000"}
{"type":"get_status"}
{"type":"reset_config"}
```

M5Stick 返回 JSON 行：

```json
{"ok":true,"message":"wifi saved"}
{"ok":false,"error":"invalid server url"}
```

## 局域网地址策略

第一版：

```text
网页管理页显示当前 PC 的候选局域网地址。
用户通过 USB 配置向导把 server_url 写入 M5Stick。
```

长期推荐：

```text
在路由器里给 PC 做 DHCP 保留固定 IP。
例如长期固定为 http://192.168.x.x:8000。
```

后续可选：

```text
实现 UDP 自动发现。
M5Stick 在局域网广播寻找 StickWords 后端。
PC 后端回复自己的地址。
```

UDP 自动发现放到后续阶段，不作为第一版必做项。

## 测试策略

PC 端：

```text
测试 CSV 读写。
测试 CSV 导入。
测试重复 word 更新内容但保留复习状态。
测试 SM-2 三种评分。
测试 review_event_id 重复上传不重复计数。
手动测试网页管理页。
```

M5Stick 端：

```text
串口日志验证 Button A / Button B。
验证横屏和左右手自动旋转。
验证单线复习流程。
验证评分页左右倾斜。
验证双摇提交“记住”。
验证断网缓存。
验证异常断电恢复。
```

联调：

```text
PC 关闭时复习，重开后上传。
PC IP 改变后用 USB 重写 server_url。
同一批 review_event_id 重试上传。
CSV 导入后 M5Stick 同步今日任务。
```
