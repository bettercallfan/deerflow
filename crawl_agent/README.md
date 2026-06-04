# crawler_agent_application

一个前后端分离的智能爬虫项目，可以让不熟悉爬虫工具的人通过前端界面完成爬虫任务，包含：

- `crawler_agent_backend`：基于 FastAPI 的后端服务，负责任务创建、调度、模型配置、存储配置与抓取执行
- `crawler_agent_fronted`：基于 Vue 3 + Vite 的前端界面，负责任务管理、调度管理、模型配置和存储配置

## 目录结构

```text
crawler_agent_application/
├── crawler_agent_backend/    # FastAPI 后端
├── crawler_agent_fronted/    # Vue 3 前端
└── README.md
```

## 环境要求

建议使用下面的运行环境：

- Python `>=3.10`
- Node.js `>=18`
- npm `>=9`

说明：

- 后端代码使用了 `str | None` 这类 Python 3.10+ 语法
- 前端依赖中的 `vite@6.3.5` 和 `@vitejs/plugin-vue@5.2.3` 要求 Node.js `^18.0.0 || >=20.0.0`
- 后端默认使用 SQLite 保存元数据，不需要额外安装数据库即可本地启动
- 如果你要测试浏览器抓取链路，建议本机具备可用的 Chrome/Chromium 环境

## 后端依赖版本

后端依赖文件：[`crawler_agent_backend/requirements.txt`](/Users/a123/PycharmProjects/crawler_agent_application/crawler_agent_backend/requirements.txt)

### API 服务相关

- `fastapi==0.115.12`
- `uvicorn[standard]==0.34.2`
- `sqlalchemy==2.0.41`
- `pydantic==2.12.5`
- `pydantic-settings==2.10.1`
- `apscheduler==3.11.0`

### 抓取与内容处理相关

- `requests==2.32.3`
- `beautifulsoup4==4.14.3`
- `openai==2.30.0`
- `agentscope==1.0.7`
- `selenium==4.41.0`
- `fake-useragent==2.2.0`
- `crawl4ai`
- `transformers==5.3.0`

### 外部存储相关

- `pymysql==1.1.1`
- `pymilvus==2.6.9`

说明：

- 目前 `crawl4ai` 在 `requirements.txt` 中未固定版本，安装时会拉取兼容的最新版本
- 如果后续要做部署或多人协作，建议把 `crawl4ai` 也固定版本

## 前端依赖版本

前端依赖文件：[`crawler_agent_fronted/package.json`](/Users/a123/PycharmProjects/crawler_agent_application/crawler_agent_fronted/package.json)

### 运行时依赖

- `axios@^1.9.0`
- `element-plus@^2.10.0`
- `pinia@^3.0.2`
- `vue@^3.5.13`
- `vue-router@^4.5.1`

### 开发依赖

- `@vitejs/plugin-vue@^5.2.3`
- `vite@^6.3.5`

说明：

- 安装时会优先按 [`crawler_agent_fronted/package-lock.json`](/Users/a123/PycharmProjects/crawler_agent_application/crawler_agent_fronted/package-lock.json) 锁定版本解析

## 后端启动

### 1. 进入后端目录

```bash
cd crawler_agent_backend
```

### 2. 创建并激活虚拟环境

macOS / Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### 3. 安装依赖

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 4. 准备环境变量

```bash
cp .env.example .env
```

当前示例环境变量文件：[`crawler_agent_backend/.env.example`](/Users/a123/PycharmProjects/crawler_agent_application/crawler_agent_backend/.env.example)

默认配置如下：

```env
APP_NAME=Crawler Agent Service
APP_VERSION=0.1.0
DEBUG=false
API_PREFIX=/api/v1
TIMEZONE=Asia/Shanghai
METADATA_DATABASE_URL=sqlite:///./crawler_agent_meta.db
SCHEDULER_ENABLED=true
MAX_CONCURRENT_RUNS=2
```

补充说明：

- 默认元数据库为当前目录下的 SQLite 文件 `crawler_agent_meta.db`
- 如果你需要对接自己的模型服务，运行后可在前端“模型配置”页面填写 `api_key`、`base_url`、`model_name`

### 5. 启动后端

```bash
python run.py
```

启动后默认监听：

- 服务地址：`http://127.0.0.1:8000`
- 健康检查：`http://127.0.0.1:8000/health`
- Swagger 文档：`http://127.0.0.1:8000/docs`
- OpenAPI JSON：`http://127.0.0.1:8000/openapi.json`

## 前端启动

### 1. 进入前端目录

```bash
cd crawler_agent_fronted
```

### 2. 安装依赖

```bash
npm install
```

### 3. 启动开发服务器

```bash
npm run dev
```

启动后默认访问：

- 前端地址：`http://127.0.0.1:5173`

## 前后端联调说明

前端默认请求的后端 API 地址写死在：

- [`crawler_agent_fronted/src/api/client.js`](/Users/a123/PycharmProjects/crawler_agent_application/crawler_agent_fronted/src/api/client.js)

默认配置为：

```js
baseURL: 'http://127.0.0.1:8000/api/v1'
```

因此本地联调时请保持：

- 后端运行在 `127.0.0.1:8000`
- 前端运行在 `127.0.0.1:5173`

## 推荐启动顺序

```bash
# 终端 1
cd crawler_agent_backend
source .venv/bin/activate
python run.py
```

```bash
# 终端 2
cd crawler_agent_fronted
npm install
npm run dev
```

然后打开：

- 前端页面：`http://127.0.0.1:5173`
- 后端文档：`http://127.0.0.1:8000/docs`

## 首次使用建议

1. 先启动后端，确认 `http://127.0.0.1:8000/health` 返回正常
2. 再启动前端，进入页面确认可以正常加载
3. 先到“模型配置”页面填写模型服务信息
4. 如果需要外部落库，再到“存储配置”页面添加 MySQL 或 Milvus 连接
5. 最后到“任务”或“调度”页面创建抓取任务

## 主要接口分组

后端 API 前缀默认为 `/api/v1`，主要包括：

- `/model-configs`：模型配置
- `/crawl/tasks`：手动抓取任务
- `/schedules`：定时调度任务
- `/storage`：外部存储配置与连通性测试

## 常见问题

### 1. 前端打不开数据

优先检查：

- 后端是否已经启动
- 后端是否运行在 `127.0.0.1:8000`
- 前端请求地址是否仍是 `http://127.0.0.1:8000/api/v1`

### 2. 后端启动后没有模型能力

这是正常的。模型配置不是默认写在 `.env` 里的，需要在前端页面或接口里补充：

- `api_key`
- `base_url`
- `model_name`

### 3. 本地是否必须安装 MySQL / Milvus

不是必须。

- 项目元数据默认使用 SQLite
- MySQL / Milvus 只在你需要把抓取结果写入外部存储时才需要配置
