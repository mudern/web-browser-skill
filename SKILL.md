---
name: web-browser
description: "用于浏览网页和进行自动化操作。通过本地 HTTP 服务，让 Claude 可以启动浏览器、访问 URL、查看页面内容、填写表单、点击按钮、滚动页面、提取数据等。"
triggers:
  - "浏览网页"
  - "访问网站"
  - "打开浏览器"
  - "访问 URL"
  - "网页自动化"
  - "操作网页"
  - "填表单"
  - "点击按钮"
  - "爬取网页"
  - "网页内容提取"
compatibility:
  - "需要 uv 虚拟环境"
  - "需要 playwright"
  - "通过本地 HTTP 服务调用"
---

# Web Browser Skill

用于浏览网页和自动化操作，通过本地 HTTP 服务控制浏览器。

---

## 环境准备

进入 skill 目录：

```bash
cd ~/.claude/skills/web-browser/scripts
source .venv/bin/activate
python browser.py
````

如果上述的启动失败请重新创建环境

```bash
cd ~/.claude/skills/web-browser/scripts
uv venv
uv sync
playwright install chromium
```

---

## 启动服务

默认监听：

```text
http://127.0.0.1:8765
```

指定端口：

```bash
python scripts/browser.py --port 9001
```

指定 host + port：

```bash
python scripts/browser.py --host 127.0.0.1 --port 9001
```

---

## 接口说明

### 健康检查

```http
GET /health
```

返回：

```json
{"ok": true, "message": "ok"}
```

---

### 获取页面快照

```http
GET /snapshot
```

---

### 执行操作

```http
POST /action
Content-Type: application/json
```

---

## 可用操作 (actions)

| action       | 参数                                      | 说明     |
| ------------ | --------------------------------------- | ------ |
| `start`      | `headless`, `storage_state`, `viewport` | 启动浏览器  |
| `goto`       | `url`, `wait_until`, `timeout`          | 访问 URL |
| `snapshot`   | -                                       | 获取页面信息 |
| `click`      | `selector`, `timeout`                   | 点击元素   |
| `fill`       | `selector`, `value`, `timeout`          | 输入内容   |
| `press`      | `selector`, `key`, `timeout`            | 按键     |
| `wait`       | `ms`                                    | 等待     |
| `save_state` | `path`                                  | 保存登录状态 |
| `load_state` | `path`, `headless`                      | 加载登录状态 |
| `screenshot` | `path`, `full_page`                     | 截图     |
| `eval`       | `script`                                | 执行 JS  |
| `close`      | -                                       | 关闭浏览器  |

---

## 使用示例

假设服务运行在：

```text
http://127.0.0.1:9001
```

---

### 启动浏览器

```bash
curl -X POST http://127.0.0.1:9001/action \
  -H 'Content-Type: application/json' \
  -d '{"action":"start","headless":false}'
```

---

### 打开网页

```bash
curl -X POST http://127.0.0.1:9001/action \
  -H 'Content-Type: application/json' \
  -d '{"action":"goto","url":"https://example.com"}'
```

---

### 获取页面信息

```bash
curl http://127.0.0.1:9001/snapshot
```

---

### 点击按钮

```bash
curl -X POST http://127.0.0.1:9001/action \
  -H 'Content-Type: application/json' \
  -d '{"action":"click","selector":"#submit-button"}'
```

---

### 输入内容

```bash
curl -X POST http://127.0.0.1:9001/action \
  -H 'Content-Type: application/json' \
  -d '{"action":"fill","selector":"input[name=email]","value":"test@example.com"}'
```

---

### 截图

```bash
curl -X POST http://127.0.0.1:9001/action \
  -H 'Content-Type: application/json' \
  -d '{"action":"screenshot","path":"page.png","full_page":true}'
```

---

### 保存登录状态

```bash
curl -X POST http://127.0.0.1:9001/action \
  -H 'Content-Type: application/json' \
  -d '{"action":"save_state","path":"state.json"}'
```

---

### 加载登录状态

```bash
curl -X POST http://127.0.0.1:9001/action \
  -H 'Content-Type: application/json' \
  -d '{"action":"load_state","path":"state.json","headless":false}'
```

---

### 关闭浏览器

```bash
curl -X POST http://127.0.0.1:9001/action \
  -H 'Content-Type: application/json' \
  -d '{"action":"close"}'
```

---

## 返回格式

成功：

```json
{
  "ok": true,
  "title": "...",
  "url": "...",
  "text": "...",
  "elements": [...]
}
```

或：

```json
{
  "ok": true,
  "message": "started"
}
```

失败：

```json
{
  "ok": false,
  "error": "错误信息",
  "detail": "详细信息",
  "status": 400
}
```

---

## 页面元素结构（elements）

每个元素包含：

* `index`: 索引
* `tag`: 标签
* `text`: 文本
* `placeholder`
* `type`
* `name`
* `id`
* `class`
* `href`
* `visible`
* `selector_hint`

---

## 推荐流程

1. 启动服务
2. 调用 `start`
3. 调用 `goto`
4. 使用 `click / fill / press` 进行操作
5. 使用 `snapshot` 获取页面状态
6. 必要时 `save_state`
7. 完成后 `close`

---

## 注意事项

* 服务是常驻进程，应保持运行
* 所有操作通过 HTTP 调用完成
* 浏览器状态在同一个服务实例中持续存在
* 如需多实例，请使用不同端口
* 登录后建议保存状态以便复用
* 注意超时参数设置
* 优先使用 `selector_hint` 作为选择器
