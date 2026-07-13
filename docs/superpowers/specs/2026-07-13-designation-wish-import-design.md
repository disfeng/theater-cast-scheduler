# 指定与许愿导入确认设计

## 目标

让管理员可以在一个持久化工作流中手工录入或导入群统计板中的指定与许愿，修正自动匹配结果，分条或批量确认有效数据，并将正式记录纳入指定剧场的自然周排班批次。

## 范围

本阶段包含：

- 以“剧场 + 周一日期”唯一标识的周排班批次。
- 群统计板原文的持久化导入草稿。
- 指定、许愿和无法解析行的草稿条目。
- 演员、角色和目标场次的自动匹配与人工修正。
- 有效条目的部分确认、批量确认和幂等正式入库。
- 与导入共用校验和确认逻辑的手工录入。
- 按周批次读取已确认、已纳入的指定与许愿，供后续周排班使用。

本阶段不包含周排班表格、冲突操作台、发布、导出或玩家登录。

## 核心业务规则

### 周批次

周批次由 `theater_id` 与自然周周一 `week_start` 唯一确定，覆盖周一至周日。状态依次为 `draft`、`ready`、`scheduled`。本阶段允许创建、查看和进入 `ready`；`scheduled` 由后续周排班工作流使用。

导入和手工录入都必须先选择一个周批次。具体场次只能从该剧场、该自然周的场次中选择。

### 指定作用范围

- 未绑定具体场次的万能指定、榜三指定和对位指定，可在批次内所有场次中寻找可满足位置。
- 绑定具体场次的指定只作用于该场。
- 指定优先级继续使用 `universal > top_three > paired`。

### 许愿作用范围

许愿属于整个周批次，不绑定具体场次，只参与指定处理后的补排，不压过任何指定。

### 部分确认

成功匹配并通过校验的条目可以单独确认或批量确认。无法解析、无法匹配或校验失败的条目保留在草稿中并显示原因，不阻塞其他有效条目。

每个草稿条目最多生成一条正式记录。重复确认返回原正式记录，不重复写入。

## 数据模型

### WeeklyBatch

- `id`
- `theater_id`
- `week_start`
- `status`: `draft | ready | scheduled`
- `created_at`
- 唯一约束：`theater_id, week_start`

### ImportDraft

- `id`
- `weekly_batch_id`
- `raw_text`
- `status`: `draft | partially_confirmed | confirmed`
- `created_at`
- `updated_at`

### ImportDraftItem

- `id`
- `import_draft_id`
- `item_kind`: `designation | wish | unresolved`
- `raw_line`
- `designation_type`: 指定条目可选
- `player_name`
- `actor_name_raw`
- `role_name_raw`
- `actor_id`
- `role_id`
- `target_performance_id`: 仅指定可选
- `note`
- `validation_status`: `valid | invalid`
- `failure_reason`
- `confirmed_at`
- `designation_id`: 确认指定后填写
- `wish_id`: 确认许愿后填写

正式 `Designation` 和 `Wish` 增加 `weekly_batch_id`。正式指定沿用现有 `included_in_batch` 字段；确认时设为 `true`。正式许愿通过批次关联表达纳入状态。

## 解析与匹配

导入服务复用现有 `parse_group_board`，将解析出的许愿、榜三建议和未解析行转换为持久化条目。手工录入直接创建同样的草稿条目，不走文本解析。

自动匹配规则：

1. 演员显示名完全匹配，忽略首尾空白。
2. 角色名完全匹配，忽略首尾空白。
3. 如果演员或角色不存在，条目标记为无效并说明原因。
4. 如果演员没有该角色能力，条目标记为无效。
5. 如果指定绑定的场次不属于所选剧场和自然周，条目标记为无效。
6. 管理员修改演员、角色、指定类型或目标场次后立即重新校验。

现有解析器无法确定的信息保持为空，等待管理员补充；不根据模糊名称猜测。

## 确认与幂等性

确认服务在同一事务中锁定或重新读取草稿条目，重新执行全部校验，再创建正式记录并回填正式记录 ID 与 `confirmed_at`。

- 已确认条目再次确认时直接返回已关联记录。
- 无效条目返回业务冲突，不修改草稿或正式表。
- 批量确认逐条返回成功或失败结果，有效条目提交，失败条目保留。
- 草稿全部条目确认后状态为 `confirmed`；部分确认后为 `partially_confirmed`；没有确认记录时保持 `draft`。

重复判定以草稿条目的正式记录关联为准。本阶段不对不同草稿中内容相同的业务记录自动去重，避免误把玩家重复购买或重复许愿合并。

## API

管理端新增：

- `GET /admin/weekly-batches`
- `POST /admin/weekly-batches`
- `GET /admin/weekly-batches/{batch_id}`
- `POST /admin/import-drafts/parse`
- `GET /admin/import-drafts/{draft_id}`
- `POST /admin/import-drafts/{draft_id}/items`
- `PATCH /admin/import-draft-items/{item_id}`
- `POST /admin/import-draft-items/{item_id}/confirm`
- `POST /admin/import-drafts/{draft_id}/confirm-valid`
- `GET /admin/weekly-batches/{batch_id}/scheduling-inputs`

`scheduling-inputs` 返回已经确认并纳入该批次的指定与许愿，字段形状与现有调度服务的 `DesignationInput`、`WishInput` 对齐。

## 管理界面

新增“指定与许愿”页面：

1. 选择剧场和周一日期，创建或打开周批次。
2. 粘贴群统计板文本并解析，或选择手工新增指定/许愿。
3. 展示草稿条目表格，包括类型、玩家、演员、角色、具体场次、状态和失败原因。
4. 使用下拉框修正指定类型、演员、角色与目标场次；许愿不展示具体场次。
5. 有效条目提供“确认”，页面顶部提供“确认全部有效条目”。
6. 已确认条目只读展示正式记录 ID，防止再次编辑。
7. 无法解析行保留原文，可转换为指定、许愿或留待后续处理。

页面刷新后从 API 恢复草稿，不依赖浏览器临时状态。

## 错误处理

业务错误使用稳定错误码和可读消息：

- `actor_not_found`
- `role_not_found`
- `actor_role_capability_missing`
- `performance_outside_batch`
- `draft_item_invalid`

前端在条目行内显示匹配错误，在页面级操作失败时显示警告。数据库失败必须回滚，不得留下没有正式记录关联的“已确认”条目。

## 测试策略

后端覆盖：

- 剧场与自然周批次唯一性和周一校验。
- 群统计板解析结果持久化。
- 演员、角色、能力和批次场次匹配。
- 有效条目部分确认且不受无效条目阻塞。
- 修正无效条目后重新校验并确认。
- 重复确认幂等，不产生重复正式记录。
- 批量确认的逐条成功/失败结果和草稿状态。
- 指定与许愿正确关联批次并转换为调度输入。

前端覆盖：

- 创建或打开周批次。
- 粘贴文本生成可恢复草稿。
- 修正条目并显示校验结果。
- 分条确认和确认全部有效条目。
- 手工新增指定与许愿。
- 刷新后重新加载草稿。
- 行级和页面级错误展示。

最终验证包括 Ruff、后端全量 pytest、前端全量 Vitest、TypeScript/Vite 构建、迁移烟雾测试和生成物跟踪检查。

## 验收标准

- 管理员可以为指定剧场和自然周建立唯一批次。
- 导入原文和草稿条目刷新后仍存在。
- 有效数据可以部分确认，无效数据有明确原因且不阻塞有效数据。
- 管理员可以修正或手工录入指定与许愿。
- 确认操作幂等，正式记录与周批次关联正确。
- 批次能够提供与排班服务兼容的已确认指定与许愿输入。
- 所有新增行为有自动化测试，且全量质量门通过。
