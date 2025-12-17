# AbDesign - 抗体设计服务

[![English](https://img.shields.io/badge/docs-English-blue)](README_EN.md)
[![Architecture](https://img.shields.io/badge/docs-Architecture-green)](ARCHITECTURE.md)
[![Development](https://img.shields.io/badge/docs-Development-orange)](DEVELOPMENT.md)
[![Testing](https://img.shields.io/badge/docs-Testing-red)](TESTING.md)

## 项目简介

AbDesign 是一个用于抗体结构分析和设计的 Web 服务平台。该系统专注于 VHH（重链可变域抗体，也称为纳米抗体）的 CDR（互补决定区）标注、结构预测和结合位点分析。

## 📚 文档导航

- **[README (English)](README_EN.md)** - 英文版说明文档
- **[架构文档 (ARCHITECTURE.md)](ARCHITECTURE.md)** - 详细的技术架构和模块说明
- **[开发指南 (DEVELOPMENT.md)](DEVELOPMENT.md)** - 快速开发指南和常见问题
- **[测试指南 (TESTING.md)](TESTING.md)** - 环境准备和测试方法

上述文档已覆盖项目的主要内容，无需额外的摘要或索引文件。

## 核心功能

### 1. CDR 区域标注
- 支持多种编号方案（Chothia、IMGT 等）
- 自动识别和标注 CDR1、CDR2、CDR3 区域
- 基于 [AbNumber](https://github.com/prihoda/abnumber) 库进行精确编号
- 输出 JSON 和 CSV 格式的标注结果

### 2. 结构分析
- 支持 PDB 和 mmCIF 格式的结构文件
- 两种提交模式：
  - **separate 模式**：分别上传 VHH 和靶标结构
  - **complex 模式**：上传复合物结构
- 自动提取序列和链信息

### 3. 异步任务处理
- 基于 Redis 和 RQ（Redis Queue）的任务队列系统
- 支持长时间运行的计算任务
- 实时任务状态查询

## 技术架构

### 系统架构图

```
┌─────────────┐      ┌──────────────┐      ┌─────────────┐
│   客户端     │ HTTP │   FastAPI    │      │   Worker    │
│  (用户请求)  │─────▶│   API 服务   │◀────▶│   进程      │
└─────────────┘      └──────────────┘      └─────────────┘
                            │                      │
                            │                      │
                            ▼                      ▼
                     ┌──────────────┐      ┌─────────────┐
                     │    Redis     │      │  Pipeline   │
                     │  消息队列    │      │  (CDR标注)  │
                     └──────────────┘      └─────────────┘
                            │
                            ▼
                     ┌──────────────┐
                     │  文件存储    │
                     │ (/tmp/...)   │
                     └──────────────┘
```

### 核心组件

#### 1. API 层 (`api/`)
- **main.py**: FastAPI 应用主入口
  - `/health`: 健康检查端点
  - `/submit`: 提交分析任务
  - `/result/{task_id}`: 查询任务结果
  - `/download/{task_id}/{artifact}`: 下载生成的文件
- **config.py**: 环境配置管理
- **schemas.py**: 数据模型定义
- **storage.py**: 文件存储管理
- **task_store.py**: 任务状态持久化
- **validators.py**: 输入验证

#### 2. 流水线层 (`pipeline/`)
- **runner.py**: 主要的流水线编排器
  - 结构对齐（预留接口）
  - 结合位点预测（预留接口）
  - 打分模型（模拟实现）
  - CDR 标注（完整实现）
- **cdr.py**: CDR 标注核心逻辑
  - 使用 gemmi 解析结构文件
  - 使用 abnumber 进行 CDR 识别

#### 3. 工作进程 (`worker/`)
- **worker.py**: RQ worker 主程序
- **tasks.py**: 后台任务定义
- **queue.py**: Redis 队列管理

#### 4. AbNumber 集成（上游 PyPI 包）
- 直接依赖 PyPI 上游 `abnumber[anarci]`，提供完整 ANARCI 编号

## 安装和部署

### 环境要求
- Python 3.10+
- Redis Server
- 依赖包（见 requirements.txt）

### 快速开始

#### 1. 安装依赖

使用 Conda（推荐）：
```bash
# 创建环境
conda create -n abdesign python=3.10 -y
conda activate abdesign

# 安装 Redis
conda install -c conda-forge redis-server -y

# 安装 Python 依赖
pip install -r requirements.txt
```

使用 uv（可选）：
```bash
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt
```

#### 2. 启动服务

需要启动三个组件（建议使用三个独立终端）：

**终端 1 - Redis:**
```bash
redis-server --daemonize yes
```

**终端 2 - API 服务:**
```bash
uvicorn api.main:app --host 0.0.0.0 --port 8000 --log-level info
# 或者使用启动脚本
./start_uvicorn.sh
```

**终端 3 - Worker:**
```bash
python -m worker.worker
```

#### 3. 运行测试

```bash
# 冒烟测试
python scripts/smoke_test.py --base-url http://localhost:8000

# 如果启用了 API Key
python scripts/smoke_test.py --base-url http://localhost:8000 --api-key YOUR_KEY
```

## API 使用示例

### 提交任务

**Separate 模式（分离上传）:**
```bash
curl -X POST "http://localhost:8000/submit" \
  -F "mode=separate" \
  -F "vhh_file=@samples/vhh_sample.pdb" \
  -F "target_file=@samples/target_sample.pdb" \
  -F "numbering_scheme=chothia"
```

响应示例：
```json
{
  "task_id": "abc123def456",
  "job_id": "rq:job:xyz789",
  "mode": "separate",
  "numbering_scheme": "chothia",
  "received_files": ["vhh_file", "target_file"],
  "status": "queued"
}
```

**Complex 模式（复合物上传）:**
```bash
curl -X POST "http://localhost:8000/submit" \
  -F "mode=complex" \
  -F "complex_file=@samples/complex.pdb" \
  -F "numbering_scheme=imgt"
```

**携带目标热点（pdb_auth）示例：**
```bash
curl -X POST "http://localhost:8000/submit" \
  -F "mode=separate" \
  -F "vhh_file=@samples/vhh_sample.pdb" \
  -F "target_file=@samples/target_sample.pdb" \
  -F "user_params={\"target_hotspots\":[\"A:305\",\"A:456\",\"B:52A\"]}"
```

### 查询结果

```bash
curl "http://localhost:8000/result/{task_id}"
```

响应示例：
```json
{
  "task_id": "abc123def456",
  "status": "succeeded",
  "result_metadata": {
    "structure_path": "/tmp/submissions/abc123def456/predicted.pdb",
    "scores_csv": "/tmp/submissions/abc123def456/scores.csv",
    "scores_tsv": "/tmp/submissions/abc123def456/scores.tsv",
    "cdr_json": "/tmp/submissions/abc123def456/cdr_annotations.json",
    "cdr_csv": "/tmp/submissions/abc123def456/cdr_annotations.csv",
    "summary_score": 0.8,
    "numbering_scheme": "chothia",
    "cdr_summary": {
      "scheme": "chothia",
      "chains": [
        {
          "chain_id": "H",
          "cdrs": [
            {
              "name": "CDR1",
              "start": "26",
              "end": "32",
              "sequence": "GFTFNTY"
            }
          ]
        }
      ]
    }
  }
}
```

### 下载文件

```bash
# 下载预测结构
curl "http://localhost:8000/download/{task_id}/structure" -o predicted.pdb

# 下载 CDR 标注（JSON）
curl "http://localhost:8000/download/{task_id}/cdr_annotations_json" -o cdr.json

# 下载 CDR 标注（CSV）
curl "http://localhost:8000/download/{task_id}/cdr_annotations_csv" -o cdr.csv

# 下载打分结果
curl "http://localhost:8000/download/{task_id}/scores_csv" -o scores.csv
```

## 配置选项

通过环境变量配置系统行为：

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| `STORAGE_ROOT` | `/tmp/submissions` | 文件存储根目录 |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis 连接地址 |
| `QUEUE_NAME` | `default` | 任务队列名称 |
| `MAX_FILE_SIZE` | `52428800` (50MB) | 最大文件大小 |
| `API_KEY` | 空字符串 | API 访问密钥（可选）|
| `CORS_ORIGINS` | `*` | CORS 允许的源 |
| `RATE_LIMIT_PER_MINUTE` | `30` | 每分钟请求限制 |

示例：
```bash
export STORAGE_ROOT=/var/abdesign/data
export API_KEY=my_secret_key
export RATE_LIMIT_PER_MINUTE=60
uvicorn api.main:app --host 0.0.0.0 --port 8000
```

## 项目结构

```
AbDesign/
├── api/                    # FastAPI Web 服务
│   ├── main.py            # 主应用和路由
│   ├── config.py          # 配置管理
│   ├── schemas.py         # 数据模型
│   ├── storage.py         # 文件存储
│   ├── task_store.py      # 任务状态管理
│   ├── validators.py      # 输入验证
│   └── results.py         # 结果处理
├── pipeline/              # 核心分析流水线
│   ├── runner.py          # 流水线编排器
│   └── cdr.py             # CDR 标注逻辑
├── worker/                # 后台任务处理
│   ├── worker.py          # Worker 主程序
│   ├── tasks.py           # 任务定义
│   └── queue.py           # 队列管理
├── scripts/               # 工具脚本
│   ├── smoke_test.py      # 冒烟测试
│   └── verify_abnumber.py # 验证使用上游 AbNumber
├── samples/               # 示例文件
│   ├── vhh_sample.pdb     # VHH 示例结构
│   └── target_sample.pdb  # 靶标示例结构
├── requirements.txt       # Python 依赖
├── start_uvicorn.sh       # 启动脚本
├── TESTING.md            # 测试指南
└── README.md             # 本文件
```

## 关键依赖

| 依赖包 | 版本 | 用途 |
|--------|------|------|
| `fastapi` | 0.115.5 | Web 框架 |
| `uvicorn` | 0.32.0 | ASGI 服务器 |
| `redis` | 5.2.1 | Redis 客户端 |
| `rq` | 1.16.2 | 任务队列 |
| `abnumber[anarci]` | 0.3.1 | 抗体编号和 CDR 识别（含 ANARCI） |
| `biopython` | 1.84 | 生物信息学工具 |
| `gemmi` | 0.6.8 | 结构文件解析 |

## 开发特性

### 中间件
- **CORS**: 支持跨域请求
- **日志**: 记录所有请求和响应时间
- **异常处理**: 统一的错误响应格式

### 安全特性
- **API Key 认证**: 可选的 API 密钥保护
- **速率限制**: 防止滥用的请求频率控制
- **文件验证**: 严格的文件类型和大小限制

### 可扩展性
- **模块化设计**: 各组件松耦合，易于扩展
- **预留接口**: 
  - 结构对齐模块（待实现）
  - 结合位点预测（待实现）
  - 打分模型（待实现）
- **配置驱动**: 通过环境变量灵活配置

## CDR 编号方案

支持的编号方案：
- **Chothia** (默认): Kabat 的改进版本，广泛用于抗体工程
- **IMGT**: 国际免疫遗传学信息系统标准
- **Kabat**: 经典的抗体编号系统
- **AHo**: 另一种常用方案
- **Martin**: 结构对齐编号

## 常见问题

### 1. Worker 无法接收任务
**原因**: Redis 未启动或连接配置不正确

**解决方案**:
```bash
# 检查 Redis 是否运行
ps aux | grep redis-server

# 检查连接
redis-cli ping
# 应该返回 PONG

# 确保环境变量一致
echo $REDIS_URL
```

### 2. 端口冲突
**解决方案**:
```bash
# 使用其他端口
uvicorn api.main:app --port 8080

# 更新测试脚本
python scripts/smoke_test.py --base-url http://localhost:8080
```

### 3. CDR 标注失败
**常见原因**:
- 结构文件格式错误
- 缺少 ATOM 记录
- 序列无法识别为抗体

**调试方法**:
```bash
# 查看任务日志
tail -f worker.log

# 检查结构文件
python -c "import gemmi; print(gemmi.read_structure('your_file.pdb'))"
```

### 4. 清理历史任务
```bash
# 删除任务状态
rm -f /tmp/task_state.json

# 清理存储目录
rm -rf /tmp/submissions/*
```

## 扩展开发

### 添加新的分析模块

1. 在 `pipeline/` 中创建新模块
2. 在 `runner.py` 中集成
3. 更新 `PipelineConfig` 和 `PipelineResult`

示例：
```python
# pipeline/new_module.py
def analyze_something(inputs):
    # 你的分析逻辑
    return result

# pipeline/runner.py
from pipeline.new_module import analyze_something

def run_pipeline(mode, inputs):
    # ...
    new_result = analyze_something(inputs)
    # ...
```

### 添加新的 API 端点

```python
# api/main.py
@app.get("/custom-endpoint/{task_id}")
async def custom_handler(task_id: str):
    # 你的处理逻辑
    return {"result": "data"}
```

## 测试

参见 [TESTING.md](TESTING.md) 获取详细的测试指南。

## 许可证

本项目的许可证信息请查看仓库。

## 贡献

欢迎提交 Issue 和 Pull Request！

## 联系方式

如有问题，请在 GitHub 仓库中创建 Issue。

---

**版本**: 0.1.0  
**最后更新**: 2025-12
