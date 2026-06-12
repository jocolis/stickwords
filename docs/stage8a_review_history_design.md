# Stage 8A Review History Design

日期：2026-06-12

## 目标

Stage 8A 将现有 `data/review_events.csv` 从简单的事件去重清单扩展为可长期查询、可恢复、可支持评分修正的复习历史。

本阶段只建设数据模型、处理语义和只读 API，不实现统计图表或管理页历史界面。Stage 8B 将在此数据契约稳定后建设网页展示。

## 已确认的产品规则

- 每一次评分都永久保留，不覆盖或删除旧记录。
- 重新评分通过 `supersedes_event_id` 指向被修正的评分。
- 历史查询显示全部评分；统计只计算修正链末端的有效评分。
- 重新评分不算第二次复习，而是撤销旧评分的调度效果。
- 修正后的调度从原评分之前的状态重新计算。
- 历史保存当时的 `word` 文本快照，不复制 `meaning` 和 `example`。
- 扩展现有 `review_events.csv`，不新增第二份历史文件。
- 旧四列记录继续可读；未知字段保持为空，不使用当前词库伪造旧状态。
- 每条新历史记录保存 `scheduler_type` 和 `scheduler_version`。
- 当前调度器标识为 `simple_sm2` / `1`。
- 未来 FSRS 只作为可回退的 PC 端实验调度器；M5Stick 继续接收 PC 算好的 `due_at`。

## 数据职责

`data/vocab.csv` 保存每个单词当前的调度状态。

`data/review_events.csv` 保存状态变化的原因和结果：

- 对上传事件进行幂等去重。
- 提供完整复习历史。
- 表达评分修正关系。
- 为统计和未来 FSRS 实验提供可靠输入。
- 在历史已写入、词库尚未保存时帮助恢复状态。

历史记录是 append-only。父记录不会因为被修正而重写；其有效性由修正关系动态计算。

## CSV 格式

新表头顺序固定为：

```text
review_event_id
supersedes_event_id
word_id
word
rating
reviewed_at
received_at
scheduler_type
scheduler_version
before_status
before_last_reviewed_at
before_due_at
before_review_count
before_ease
before_interval_days
before_lapses
before_updated_at
after_status
after_last_reviewed_at
after_due_at
after_review_count
after_ease
after_interval_days
after_lapses
after_updated_at
```

字段含义：

- `review_event_id`：事件的全局唯一 ID，也是幂等键。
- `supersedes_event_id`：被本事件修正的直接父事件；普通评分为空。
- `word_id`：关联 `vocab.csv` 中的词条。
- `word`：评分发生时的单词文本快照。
- `rating`：`forgot`、`hard` 或 `good`。
- `reviewed_at`：用户在设备上评分的 UTC 时间。
- `received_at`：PC 后端首次接受该事件的 UTC 时间。
- `scheduler_type`：生成 `after_*` 状态的调度器，例如 `simple_sm2`。
- `scheduler_version`：调度规则版本，例如 `1`。
- `before_*`：本次有效评分之前的调度状态。
- `after_*`：应用本次评分后的调度状态。

`ease` 使用两位小数。日期使用 UTC ISO 8601 秒精度和 `Z` 后缀。空值写为空字符串。

`added_at`、`meaning` 和 `example` 不进入历史快照。调度恢复时保留 `vocab.csv` 中的内容字段，只使用历史覆盖调度字段。

## 旧文件兼容与迁移

旧文件只有：

```text
review_event_id,word_id,rating,reviewed_at
```

旧记录仍可用于：

- 判断 `review_event_id` 是否已经处理。
- 显示已知的 word ID、评分和评分时间。

旧记录不能用于：

- 重建评分前后的调度状态。
- 作为评分修正的目标。
- 需要状态变化数据的精细统计。
- FSRS 参数优化。

不能直接在旧四列表头下追加新格式行。`ReviewEventStore` 在首次需要写入新记录时：

1. 检测当前表头。
2. 读取全部旧记录。
3. 将旧记录映射到新表头，未知字段留空。
4. 写入同目录临时文件。
5. flush 并关闭文件。
6. 使用原子替换更新 `review_events.csv`。
7. 再追加本次新记录。

迁移不根据当前 `vocab.csv` 回填旧状态。

## 普通评分处理

普通评分的 `supersedes_event_id` 为空。

处理顺序：

1. 校验事件 ID、word ID、rating 和 reviewed time。
2. 如果事件 ID 已存在，执行幂等恢复检查，不再次计算评分。
3. 确认 word ID 存在。
4. 确认该评分时间不早于这个单词已接受的最新有效普通评分或修正评分。
5. 从当前词条复制 `before_*` 调度状态。
6. 使用当前调度器计算 `after_*`。
7. 先持久化完整历史记录。
8. 再把 `after_*` 保存到 `vocab.csv`。

第 7 步失败时不得修改 `vocab.csv`。

## 评分修正

修正事件必须包含非空 `supersedes_event_id`。

允许修正的条件：

- 父事件存在。
- 父事件属于同一个 `word_id`。
- 父事件是当前修正链的末端，即尚未被其他事件修正。
- 父事件具有完整的 `before_*` 和 `after_*` 快照。
- 父事件是该单词最新的有效评分；其后不存在另一轮复习。

不满足任一条件时，整个修正事件失败并返回明确错误，不写历史、不修改词库。

修正计算：

1. 读取父事件。
2. 沿 `supersedes_event_id` 向上找到修正链根事件。
3. 使用根事件的 `before_*` 作为基线。
4. 在该基线上应用新的 rating。
5. 新历史的 `before_*` 仍保存这份原始基线。
6. 新历史的 `after_*` 保存重新计算的结果。
7. 新事件通过 `supersedes_event_id` 指向直接父事件。

示例：

```text
event-001 forgot
  before: review_count=0, lapses=0
  after:  review_count=1, lapses=1

event-002 hard, supersedes event-001
  before: review_count=0, lapses=0
  after:  review_count=1, lapses=0

event-003 good, supersedes event-002
  before: review_count=0, lapses=0
  after:  review_count=1, lapses=0
```

最终 `vocab.csv` 使用 `event-003` 的 `after_*`。三条历史全部保留，但只有 `event-003` 有效。

## 有效性计算

CSV 不存储可变的 `is_effective` 或 `superseded_by_event_id` 字段。

加载历史时构建：

- `by_event_id`：事件 ID 到记录的映射。
- `superseded_ids`：所有非空 `supersedes_event_id` 的集合。
- `superseded_by`：父事件 ID 到直接修正事件 ID 的映射。

一条记录满足以下条件时有效：

```text
review_event_id 不在 superseded_ids 中
```

第一版只允许一条父记录拥有一个直接修正子记录，因此不会形成分叉修正链。

## 事件顺序

单次上传中的事件继续按以下顺序处理：

```text
(reviewed_at, payload_order)
```

同一批次中的修正事件必须出现在父事件之后。父事件可以来自：

- 已持久化历史。
- 当前批次中先前已成功接受的记录。

如果修正事件先于尚未存在的父事件，返回 `unknown supersedes_event_id`，不猜测依赖顺序。

对于同一单词，晚到且时间早于已接受最新有效评分的普通事件，第一版拒绝处理。当前单设备持久化队列会按顺序上传；拒绝异常乱序比静默破坏调度状态更安全。

## M5Stick 上传协议

普通评分：

```json
{
  "word_id": "w-000001",
  "rating": "forgot",
  "reviewed_at": "2026-06-12T08:00:00Z",
  "event_id": "m5stick-c-plus-abcd-1-w-000001",
  "supersedes_event_id": ""
}
```

修正评分：

```json
{
  "word_id": "w-000001",
  "rating": "good",
  "reviewed_at": "2026-06-12T08:01:00Z",
  "event_id": "m5stick-c-plus-abcd-2-w-000001",
  "supersedes_event_id": "m5stick-c-plus-abcd-1-w-000001"
}
```

为生成修正关系，固件待上传记录需要保存稳定的 `event_id`，而不是只在构建 HTTP JSON 时临时拼接。复习结果还需记住该卡片最近一次提交的事件 ID，重新评分时将其写入 `supersedes_event_id`。

已有不含该字段的客户端请求按普通评分处理。

## 幂等与断电恢复

### 重复上传

如果 `review_event_id` 已存在：

- 不追加第二行。
- 不增加复习次数。
- 不改变修正关系。
- 检查对应 word 的当前调度状态是否至少与历史 `after_*` 一致。

### 历史已写、词库未保存

处理新事件时先写历史，再保存词库。如果进程在两步之间退出，下次收到同一事件时：

1. 找到已有历史。
2. 将该事件的 `after_*` 覆盖到当前词条调度字段。
3. 保存 `vocab.csv`。
4. 返回 duplicate，而不是再次应用评分。

恢复只针对具有完整 `after_*` 的新格式记录。旧记录缺少快照时维持原有幂等行为，不伪造恢复状态。

### 词库已出现更新但历史缺失

正常流程不会先写词库再写历史。若人工修改文件造成这种状态，系统不根据词库反向创建历史。

## 只读查询 API

新增：

```text
GET /api/reviews/recent?limit=50
```

规则：

- 默认 `limit=50`。
- 最小值为 0，最大值为 500。
- 按 `(reviewed_at, file_order)` 倒序返回。
- 默认返回所有记录，包括已被修正的评分。
- 旧格式记录的未知字段返回 `null`。
- malformed 历史行不进入结果，并在服务日志中报告；不得阻断其他有效行查询。

返回示例：

```json
{
  "reviews": [
    {
      "review_event_id": "event-002",
      "supersedes_event_id": "event-001",
      "superseded_by_event_id": null,
      "is_effective": true,
      "word_id": "w-000001",
      "word": "duped",
      "rating": "good",
      "reviewed_at": "2026-06-12T08:01:00Z",
      "received_at": "2026-06-12T08:05:00Z",
      "scheduler_type": "simple_sm2",
      "scheduler_version": "1",
      "before_status": "new",
      "before_interval_days": 0,
      "after_status": "review",
      "after_interval_days": 1,
      "after_due_at": "2026-06-13T08:01:00Z"
    }
  ]
}
```

`is_effective` 和 `superseded_by_event_id` 是查询时派生字段，不写回 CSV。

## 调度器边界与未来 FSRS

Stage 8A 不改变现有 `apply_review()` 算法。

新历史记录标记：

```text
scheduler_type = simple_sm2
scheduler_version = 1
```

未来实验性 FSRS：

- 只在 PC 后端启用。
- 使用配置在 `simple_sm2` 与 `fsrs` 之间切换。
- M5Stick 继续接收 `due_at` 和离线包，不运行 FSRS。
- `forgot` 映射为 FSRS `Again`。
- `hard` 映射为 FSRS `Hard`。
- `good` 映射为 FSRS `Good`。
- 第一版不提供 FSRS `Easy`。
- 只使用 Stage 8A 上线后的完整、有效历史进行参数优化。
- 旧记录和已被修正记录不参与训练。
- 切换调度器时必须保留回退路径，不覆盖历史。

FSRS 不属于 Stage 8A 的实现范围。

## 组件边界

建议保持以下职责：

- `ReviewEvent`：设备上传的输入事件。
- `ReviewHistoryRecord`：包含前后快照的持久化历史。
- `ReviewEventStore`：迁移、加载、索引、追加和最近历史查询。
- `process_review_events()`：排序、校验、普通评分、修正评分、幂等恢复。
- `StickWordsService`：提供 PC 时钟、词库保存和 API 数据转换。
- `web.py`：解析 `/api/reviews/recent` 查询参数并返回 JSON。

调度公式仍留在 `scheduler.py`，历史模块不复制公式。

## 错误处理

以下情况单条事件失败，其他独立事件可以继续：

- unknown word ID
- invalid rating
- missing event ID or reviewed time
- unknown `supersedes_event_id`
- correction target belongs to another word
- correction target already superseded
- correction target lacks complete snapshots
- correction target is not the latest effective review for the word
- normal event is older than the latest accepted effective review

响应继续使用：

```json
{
  "accepted": 1,
  "skipped_duplicate": 0,
  "failed": 1,
  "errors": ["reviews[1]: correction target already superseded"]
}
```

## 测试范围

### 存储测试

- 新文件写入固定表头。
- 旧四列表头原子迁移，未知字段为空。
- UTF-8 BOM 只出现在文件开头。
- 多条记录按文件顺序加载。
- malformed 行被报告并跳过。
- 最近历史按时间和文件顺序倒序返回。

### 处理测试

- 普通评分写入完整 before/after 快照。
- 相同事件 ID 只应用一次。
- 重复事件可从 `after_*` 恢复落后的 `vocab.csv`。
- 修正评分从根事件 `before_*` 重新计算。
- 多次修正形成线性链，只有末端有效。
- 修正后 `review_count` 只增加一次。
- `forgot` 改为 `good` 后不会保留错误的 lapse。
- 拒绝跨词修正、分叉修正、旧格式修正和过期修正。
- 同时间事件保持 payload 顺序。

### 服务与 API 测试

- 无 `supersedes_event_id` 的旧客户端仍可上传。
- 新客户端可以上传修正关系。
- `received_at` 使用 PC 后端时钟。
- recent API 校验 limit 并返回派生有效性字段。
- PC 重启后历史和修正关系仍可加载。

### 固件源码测试

- 待上传记录持久化稳定 `event_id`。
- 修正评分上传正确的 `supersedes_event_id`。
- 普通评分发送空修正字段。
- 旧待上传 NVS 结构可以迁移或被明确兼容。

## 本阶段不做

- 管理页历史列表和统计图表。
- 历史导出、导入和备份恢复 UI。
- 任意旧评分的全历史重放。
- 删除或修改历史记录。
- 多设备冲突合并。
- SQLite 迁移。
- FSRS 调度器或参数优化。
- 对旧四列记录进行状态推断。

## 验收标准

- `review_events.csv` 能兼容旧文件并保存新格式历史。
- 所有新评分拥有准确的前后调度快照和调度器版本。
- 同一事件重复上传不会重复计数，并可修复历史已写但词库未保存的状态。
- 最新有效评分可以被线性修正，最终调度等同于从原始基线直接应用新评分。
- 全部评分永久可查，API 能区分有效和已被修正记录。
- 现有无修正字段的 M5Stick/客户端上传仍然有效。
- Stage 8A 不改变现有简化 SM-2 的调度结果。
