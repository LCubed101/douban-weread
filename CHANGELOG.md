# Changelog

## v0.2.0 — Book Router UX · 2026-09-13

### 🎯 本次版本重点

- 修复明确书名搜索时的豆瓣候选污染
  - 搜索《变量》时，不再把《情绪》《变量2》《变量7》《变量8》误当成同一本书的版本候选
  - 新增严格标题过滤：Search 负责召回，Resolver 负责判断
  - 保持 fail closed：证据不足时不为了凑候选数量塞入弱匹配结果
- 新增 **Explicit Text Fast Path**
  - 纯文本书名 + 唯一候选 + exact title match + 无歧义时，跳过“你想加入的是这本吗？”确认卡
  - 直接检查 / 写入豆瓣状态并继续查询微信读书
  - 已有「想读 / 在读 / 读过」状态时保留原状态，不降级
- 目标体验进一步收束为：
  - `看到 → 识别 → 必要时选一次 → 完成`
  - 在确定输入下：`看到 → 发出去 → 完成`

### ✅ 今日验证

- PR #74：strict title filtering before showing Douban candidates
- PR #75：explicit-text fast path skips confirmation for exact single matches
- 飞书真实回归：《变量》直接返回豆瓣状态 + 微信读书结果

### 📝 开发日记

- `docs/DEV_LOG_2026-09-13.md`

---

## Previous / Latest

### ✨ 新功能

- 新增 **多图连续发送支持**
  - 连续发送多张截图时，可合并识别后统一处理
- 完善 **图书 Reading Router**
  - 支持书名 / ISBN / 截图 / 长文本中的图书识别
  - 支持豆瓣「想读」记录
  - 支持微信读书版本匹配与可读性检查

### ⚡ 功能优化

- 优化图书交互流程，减少重复确认
  - 能直接判断时直接执行
  - 有歧义时优先使用按钮选择
  - 目标体验：`看到 → 识别 → 必要时选一次 → 完成`
- 优化豆瓣与微信读书的匹配逻辑
  - 豆瓣负责「我想读什么」
  - 微信读书负责「我现在能不能读」
  - 同一作品不同版本时支持更合理的跨版本匹配
- 优化结果卡片
  - 成功状态更明确
  - 减少冗余提示和调试信息
  - 保留直接打开目标平台的入口
- 优化多图处理逻辑
  - 连续截图尽量不再被拆成多个独立任务
  - 尽量统一输出一次结果

### 🛠 问题修复

- 修复点击按钮后重复出现确认卡片的问题
- 修复连续发送多张图片时被拆成多个独立任务的问题
- 修复部分微信读书因版本差异被误判为「不可读」的问题

### 🌿 产品范围调整

- 主产品重新聚焦为 **Book-only Reading Router**
- Film / TV / Documentary 不再作为主产品能力继续扩展
- 已有 Movie / TV 能力保留在独立实验分支：`experiment/movie-router`
- Podcast Router 暂不进入主产品路线
- 飞书 Bot 保持为 Capture 入口，不承担知识库角色
- 观点 / 摘抄 / 灵感继续交给 flomo 等现有笔记工具

### 🧪 独立实验

`experiment/movie-router` 保留此前已验证的 Movie / TV 能力，包括：

- Film / TV / Documentary → 豆瓣「想看」
- 同名 Book / Movie 按钮选择
- 多季剧集识别与季数选择
- 安全场景下的 Mixed Book + Movie Router

该分支面向明确需要影视自动路由的用户，不代表 Book-only 主产品范围。
