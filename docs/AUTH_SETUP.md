# 豆瓣 Cookie / 微信读书凭证安全配置

这份文档说明如何为 `douban-weread` 准备本地凭证。

> 重要：凭证只应该保存在你自己的电脑上。不要把真实 Cookie、API Key、App Secret 粘贴到 GitHub Issue、PR、聊天记录、截图或公开文档中。

## 先看结论

当前 V1 使用两种不同的凭证：

- **豆瓣**：使用你自己浏览器登录后的完整 `Cookie` 请求头，写入 `DOUBAN_COOKIE`。
- **微信读书**：当前实现使用腾讯官方 WeChatReading Agent API 的 **`WEREAD_API_KEY`**，不是浏览器 Cookie。

因此 `.env` 中推荐使用：

```env
DOUBAN_COOKIE='bid=...; dbcl2="..."; ck=...; ...'
WEREAD_API_KEY='...'
```

不要把示例中的 `...` 替换后提交到 Git。

---

## 1. 安全获取豆瓣 Cookie

### 前提

1. 在浏览器中正常登录你自己的豆瓣账号。
2. 打开豆瓣读书页面，例如 `https://book.douban.com/`。
3. 确认页面显示的是你的已登录状态。

### Chrome / Edge 获取方式

1. 打开豆瓣读书页面。
2. 打开开发者工具：
   - macOS：`Option + Command + I`
   - Windows / Linux：`F12` 或 `Ctrl + Shift + I`
3. 进入 **Network / 网络** 标签页。
4. 刷新豆瓣读书页面。
5. 在请求列表中点击一个发往 `book.douban.com` 的请求。
6. 打开 **Headers / 标头**。
7. 在 **Request Headers / 请求标头** 中找到 `Cookie`。
8. 只复制 `Cookie` 后面的完整单行值。

你要的是类似下面这种内容：

```text
bid=...; dbcl2="..."; ck=...; ...
```

或者浏览器复制出来带有前缀：

```text
Cookie: bid=...; dbcl2="..."; ck=...; ...
```

项目两种格式都能识别。

### 不要复制这些东西

不要把下面任一种内容当成 `DOUBAN_COOKIE`：

- 完整的 `Copy as cURL` 命令
- 整页 Request Headers
- 多行请求头文本
- JSON 格式的浏览器 Cookie 导出
- 浏览器扩展导出的整套会话文件

当前实现至少需要 Cookie 中存在：

```text
dbcl2
ck
```

其它 Cookie 字段建议保留，不要手工删减。

### 写入 `.env`

项目根目录中：

```bash
cp .env.example .env
```

然后编辑 `.env`：

```env
DOUBAN_COOKIE='bid=...; dbcl2="..."; ck=...; ...'
```

推荐用单引号包住完整值，避免 Cookie 中的特殊字符被 shell 解释。

### 更安全的临时测试方式

如果只是临时验证，不想让 Cookie 出现在 shell history 中：

```bash
read -s "DOUBAN_COOKIE?Paste Douban Cookie locally: "
export DOUBAN_COOKIE
echo
```

粘贴时终端不会显示 Cookie 内容。

然后先做本地结构检查：

```bash
douban-weread auth diagnose
```

这个命令不会发网络请求，也不会打印 Cookie 原文。健康结果应该至少包含：

```text
Has dbcl2: True
Has ck: True
Ready for auth check: True
```

只有结构检查通过后，再做只读登录验证：

```bash
douban-weread auth check
```

如果 Cookie 过期，重新登录豆瓣并重新获取即可。

---

## 2. 获取微信读书官方 API Key

当前项目的微信读书搜索、书籍元数据和只读能力使用腾讯官方 WeChatReading Agent API。

**不需要从浏览器复制微信读书 Cookie。**

API Key 获取入口：

```text
https://weread.qq.com/r/weread-skills
```

按照页面提示使用你自己的微信读书账号申请 / 获取个人 API Key。

获取后，把它放到本机 `.env`：

```env
WEREAD_API_KEY='你的 API Key'
```

不要：

- 把 API Key 提交到 GitHub
- 把 API Key 发给项目维护者
- 把 API Key 放进截图
- 在 Issue / PR 中粘贴报错时连同 Key 一起粘贴

### 测试微信读书凭证

安装项目并加载环境变量后，可以先做只读搜索：

```bash
set -a
source .env
set +a

douban-weread weread search "白夜行" --limit 5
```

如果能够返回微信读书候选，说明 API Key 已经能够正常工作。

也可以查询一个已知 `bookId`：

```bash
douban-weread weread book --id 230107
```

这些操作都是只读查询。

---

## 3. `.env` 推荐模板

完整示例：

```env
# Feishu
FEISHU_APP_ID='cli_xxx'
FEISHU_APP_SECRET='xxx'

# Douban
DOUBAN_COOKIE='bid=...; dbcl2="..."; ck=...; ...'

# WeRead official Agent API
WEREAD_API_KEY='xxx'

# Local storage
DATABASE_URL='sqlite:///data/douban-weread.db'
```

`.env` 只保存在本机。

检查它是否被 Git 忽略：

```bash
git status --short
```

正常情况下不应该看到 `.env`。

也可以确认：

```bash
git check-ignore .env
```

如果输出：

```text
.env
```

说明 Git 正在忽略它。

---

## 4. 凭证泄露了怎么办

如果你不小心把真实凭证发到了公开位置：

### 豆瓣 Cookie

1. 删除公开内容中的 Cookie。
2. 退出豆瓣登录并重新登录，以使旧会话失效或更换会话。
3. 重新获取新的 Cookie。
4. 更新本机 `.env`。

### 微信读书 API Key

1. 立即在微信读书官方 API Key 管理页面撤销 / 轮换旧 Key（以页面实际提供的功能为准）。
2. 生成或获取新的 Key。
3. 更新本机 `.env`。

### 飞书 App Secret

如果同时泄露了 `FEISHU_APP_SECRET`，请在飞书开放平台重置 Secret，并同步更新 `.env`。

---

## 5. 常见问题

### `douban-weread auth diagnose` 显示 `Parsed cookie count: 0`

通常说明复制的不是单行 Cookie 请求头。重新从浏览器 Network → Request Headers → Cookie 获取。

### 有 `dbcl2`，但没有 `ck`

不要手工拼一个 `ck`。重新复制完整 Cookie 请求头。

### `auth check` 提示 Cookie expired / forbidden

重新登录豆瓣后重新获取 Cookie。

### 微信读书搜索提示缺少凭证

确认 `.env` 中使用的是：

```env
WEREAD_API_KEY='...'
```

而不是 `WEREAD_COOKIE`。

### LaunchAgent 启动后读不到凭证

后台启动脚本会从项目根目录加载 `.env`。确认文件存在：

```bash
ls -l .env
```

然后重新安装 / 启动 LaunchAgent：

```bash
zsh scripts/install_launchagent.sh
```

---

## 安全原则

这个项目是 self-hosted：

```text
你的账号
→ 你的浏览器 / 官方 API Key
→ 你的本机 .env
→ 你的本地 bot
```

凭证不需要交给其他人，也不应该进入 Git 仓库。
