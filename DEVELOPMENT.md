# 快速开发指南 / Quick Development Guide

[中文](#中文版) | [English](#english-version)

---

## 中文版

### 5 分钟快速上手

#### 前置条件
- Python 3.10+
- Redis (通过 conda 安装或系统包管理器)

#### 一键启动（开发环境）

```bash
# 1. 克隆仓库
git clone https://github.com/JaytonKogeru/AbDesign.git
cd AbDesign

# 2. 创建环境并安装依赖
conda create -n abdesign python=3.10 -y
conda activate abdesign
conda install -c conda-forge redis-server -y
pip install -r requirements.txt

# 3. 启动所有服务（在不同终端窗口）
# 终端 1: 启动 Redis
redis-server --daemonize yes

# 终端 2: 启动 API
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

# 终端 3: 启动 Worker
python -m worker.worker

# 4. 快速测试（无需启动服务）
make selftest
# 或
python scripts/selftest.py

# 5. 完整冒烟测试（需要启动服务）
python scripts/smoke_test.py
```

### 依赖管理

- 目前仓库没有 `third_party/` 目录下的 vendored 代码，依赖全部通过 PyPI 安装（见 `requirements.txt`）。
- 如未来确需引入 vendored 第三方库，请新建子目录时同步更新打包/部署忽略规则（如容器构建上下文、发行包清单），避免无意分发体积较大的依赖。

### 常用开发命令

#### 快速自检
```bash
# 快速验证核心功能（无需启动 Redis/API/Worker）
make selftest

# 验证 AbNumber 集成
python scripts/verify_abnumber.py

# 运行单元测试
pytest
# 或
make test
```

#### 测试 API
```bash
# 健康检查
curl http://localhost:8000/health

# 提交任务
curl -X POST http://localhost:8000/submit \
  -F "mode=separate" \
  -F "vhh_file=@samples/vhh_sample.pdb" \
  -F "target_file=@samples/target_sample.pdb"

# 查询结果（替换 task_id）
curl http://localhost:8000/result/{task_id}
```

#### 调试技巧

**查看 API 日志**
```bash
# API 会在终端实时输出请求日志
uvicorn api.main:app --reload --log-level debug
```

**查看 Worker 日志**
```bash
# Worker 输出包含任务执行详情
python -m worker.worker
```

**检查 Redis 队列**
```bash
# 连接 Redis CLI
redis-cli

# 查看队列长度
> LLEN rq:queue:default

# 查看所有键
> KEYS rq:*

# 监控实时命令
> MONITOR
```

**检查任务状态文件**
```bash
# 查看持久化的任务状态
cat /tmp/task_state.json | python -m json.tool
```

### 开发工作流

#### 1. 修改 API 端点

编辑 `api/main.py`:
```python
@app.get("/custom-endpoint")
async def custom_handler():
    return {"message": "Hello from custom endpoint"}
```

重启 API 服务（如果使用 `--reload` 则自动重载）。

#### 2. 添加新的分析功能

在 `pipeline/` 创建新文件：
```python
# pipeline/my_analysis.py
def analyze(structure_path: str) -> dict:
    """你的分析逻辑"""
    result = {
        "status": "success",
        "data": {}
    }
    return result
```

在 `pipeline/runner.py` 中集成：
```python
from pipeline.my_analysis import analyze

def run_pipeline(mode, inputs):
    # ... 现有代码 ...
    
    # 添加你的分析
    my_result = analyze(inputs.get("vhh_file"))
    
    # 添加到结果中
    summary_payload["my_analysis"] = my_result
```

#### 3. 修改 CDR 标注逻辑

编辑 `pipeline/cdr.py`：
```python
def annotate_cdrs(structure_path, scheme='chothia'):
    # 你的修改
    pass
```

重启 Worker 使更改生效。

#### 4. 添加新的配置选项

在 `api/config.py` 添加：
```python
@dataclass(frozen=True)
class Settings:
    # ... 现有字段 ...
    my_new_setting: str
    
@lru_cache(maxsize=1)
def get_settings():
    return Settings(
        # ... 现有设置 ...
        my_new_setting=os.getenv("MY_NEW_SETTING", "default_value"),
    )
```

使用环境变量：
```bash
export MY_NEW_SETTING=custom_value
uvicorn api.main:app
```

### 代码风格

项目遵循以下规范：

```bash
# 安装开发工具（可选）
pip install black isort flake8 mypy

# 格式化代码
black .

# 排序导入
isort .

# 检查代码风格
flake8 api/ pipeline/ worker/

# 类型检查
mypy api/ pipeline/ worker/
```

### 单元测试（待添加）

建议的测试结构：
```
tests/
├── test_api/
│   ├── test_main.py
│   ├── test_storage.py
│   └── test_validators.py
├── test_pipeline/
│   ├── test_runner.py
│   └── test_cdr.py
└── test_worker/
    └── test_tasks.py
```

示例测试：
```python
# tests/test_pipeline/test_cdr.py
import pytest
from pipeline.cdr import annotate_cdrs

def test_annotate_cdrs():
    result = annotate_cdrs("samples/vhh_sample.pdb", scheme="chothia")
    assert result.scheme == "chothia"
    assert len(result.chains) > 0
```

运行测试：
```bash
pytest tests/ -v
```

### 环境变量参考

创建 `.env` 文件（不要提交到 Git）：
```bash
# .env
STORAGE_ROOT=/tmp/abdesign/submissions
REDIS_URL=redis://localhost:6379/0
QUEUE_NAME=default
MAX_FILE_SIZE=52428800
API_KEY=your-secret-key-here
CORS_ORIGINS=http://localhost:3000,http://localhost:8080
RATE_LIMIT_PER_MINUTE=60
```

使用 python-dotenv 加载：
```bash
pip install python-dotenv
```

```python
from dotenv import load_dotenv
load_dotenv()
```

### Docker 开发（可选）

创建 `Dockerfile`:
```dockerfile
FROM python:3.10-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    redis-server \
    && rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制代码
COPY . .

# 暴露端口
EXPOSE 8000

# 启动命令
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

创建 `docker-compose.yml`:
```yaml
version: '3.8'

services:
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
  
  api:
    build: .
    ports:
      - "8000:8000"
    environment:
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      - redis
    volumes:
      - ./:/app
      - /tmp/submissions:/tmp/submissions
  
  worker:
    build: .
    command: python -m worker.worker
    environment:
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      - redis
    volumes:
      - ./:/app
      - /tmp/submissions:/tmp/submissions
```

使用 Docker Compose：
```bash
docker-compose up -d
docker-compose logs -f
docker-compose down
```

### 常见开发问题

#### 问题 1: 模块导入错误
```
ModuleNotFoundError: No module named 'api'
```

**解决方案**:
```bash
# 确保在项目根目录
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
```

#### 问题 2: Redis 连接失败
```
redis.exceptions.ConnectionError: Error connecting to Redis
```

**解决方案**:
```bash
# 检查 Redis 是否运行
redis-cli ping

# 检查环境变量
echo $REDIS_URL

# 启动 Redis
redis-server --daemonize yes
```

#### 问题 3: Worker 不处理任务

**检查清单**:
1. Redis 是否运行？
2. API 和 Worker 使用相同的 Redis URL？
3. 队列名称是否一致？
4. Worker 是否正在运行？

```bash
# 查看队列内容
redis-cli LLEN rq:queue:default

# 查看 Worker 进程
ps aux | grep worker
```

#### 问题 4: 文件权限错误

```bash
# 确保临时目录可写
sudo chmod -R 777 /tmp/submissions
# 或使用用户目录
export STORAGE_ROOT=$HOME/abdesign/submissions
mkdir -p $HOME/abdesign/submissions
```

### 性能分析

使用 Python profiler：
```python
import cProfile
import pstats

def profile_pipeline():
    profiler = cProfile.Profile()
    profiler.enable()
    
    # 运行你的代码
    result = run_pipeline("separate", inputs)
    
    profiler.disable()
    stats = pstats.Stats(profiler)
    stats.sort_stats('cumulative')
    stats.print_stats(20)

profile_pipeline()
```

使用 `time` 命令：
```bash
time python scripts/smoke_test.py
```

### Git 工作流

```bash
# 创建功能分支
git checkout -b feature/my-new-feature

# 提交更改
git add .
git commit -m "Add my new feature"

# 推送到远程
git push origin feature/my-new-feature

# 创建 Pull Request（在 GitHub 网页上）
```

### 有用的资源

- [FastAPI 文档](https://fastapi.tiangolo.com/)
- [Redis Queue (RQ) 文档](https://python-rq.org/)
- [AbNumber 文档](https://github.com/prihoda/abnumber)
- [Gemmi 文档](https://gemmi.readthedocs.io/)
- [Pydantic 文档](https://docs.pydantic.dev/)

---

## English Version

### 5-Minute Quick Start

#### Prerequisites
- Python 3.10+
- Redis (installed via conda or system package manager)

#### One-Command Startup (Development Environment)

```bash
# 1. Clone repository
git clone https://github.com/JaytonKogeru/AbDesign.git
cd AbDesign

# 2. Create environment and install dependencies
conda create -n abdesign python=3.10 -y
conda activate abdesign
conda install -c conda-forge redis-server -y
pip install -r requirements.txt

# 3. Start all services (in different terminal windows)
# Terminal 1: Start Redis
redis-server --daemonize yes

# Terminal 2: Start API
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

# Terminal 3: Start Worker
python -m worker.worker

# 4. Quick test (no services needed)
make selftest
# or
python scripts/selftest.py

# 5. Full smoke test (requires services running)
python scripts/smoke_test.py
```

### Dependency Management

- There is no vendored code under `third_party/`; all dependencies come from PyPI (see `requirements.txt`).
- If you ever need to vendor a third-party library, add it under a new subdirectory and update packaging/deployment ignore rules (e.g., container build context, release manifests) so large dependencies are not shipped unintentionally.

### Common Development Commands

#### Quick Self-Check
```bash
# Quick validation of core functionality (no Redis/API/Worker needed)
make selftest

# Verify AbNumber integration
python scripts/verify_abnumber.py

# Run unit tests
pytest
# or
make test
```

#### Test API
```bash
# Health check
curl http://localhost:8000/health

# Submit task
curl -X POST http://localhost:8000/submit \
  -F "mode=separate" \
  -F "vhh_file=@samples/vhh_sample.pdb" \
  -F "target_file=@samples/target_sample.pdb"

# Query results (replace task_id)
curl http://localhost:8000/result/{task_id}
```

#### Debugging Tips

**View API Logs**
```bash
# API outputs request logs in real-time
uvicorn api.main:app --reload --log-level debug
```

**View Worker Logs**
```bash
# Worker output includes task execution details
python -m worker.worker
```

**Check Redis Queue**
```bash
# Connect to Redis CLI
redis-cli

# Check queue length
> LLEN rq:queue:default

# View all keys
> KEYS rq:*

# Monitor real-time commands
> MONITOR
```

**Check Task State File**
```bash
# View persisted task state
cat /tmp/task_state.json | python -m json.tool
```

### Development Workflow

#### 1. Modify API Endpoint

Edit `api/main.py`:
```python
@app.get("/custom-endpoint")
async def custom_handler():
    return {"message": "Hello from custom endpoint"}
```

Restart API service (auto-reload if using `--reload`).

#### 2. Add New Analysis Function

Create new file in `pipeline/`:
```python
# pipeline/my_analysis.py
def analyze(structure_path: str) -> dict:
    """Your analysis logic"""
    result = {
        "status": "success",
        "data": {}
    }
    return result
```

Integrate in `pipeline/runner.py`:
```python
from pipeline.my_analysis import analyze

def run_pipeline(mode, inputs):
    # ... existing code ...
    
    # Add your analysis
    my_result = analyze(inputs.get("vhh_file"))
    
    # Add to results
    summary_payload["my_analysis"] = my_result
```

#### 3. Modify CDR Annotation Logic

Edit `pipeline/cdr.py`:
```python
def annotate_cdrs(structure_path, scheme='chothia'):
    # Your modifications
    pass
```

Restart Worker for changes to take effect.

#### 4. Add New Configuration Option

Add to `api/config.py`:
```python
@dataclass(frozen=True)
class Settings:
    # ... existing fields ...
    my_new_setting: str
    
@lru_cache(maxsize=1)
def get_settings():
    return Settings(
        # ... existing settings ...
        my_new_setting=os.getenv("MY_NEW_SETTING", "default_value"),
    )
```

Use environment variable:
```bash
export MY_NEW_SETTING=custom_value
uvicorn api.main:app
```

### Code Style

Project follows these conventions:

```bash
# Install development tools (optional)
pip install black isort flake8 mypy

# Format code
black .

# Sort imports
isort .

# Check code style
flake8 api/ pipeline/ worker/

# Type checking
mypy api/ pipeline/ worker/
```

### Unit Tests (To Be Added)

Recommended test structure:
```
tests/
├── test_api/
│   ├── test_main.py
│   ├── test_storage.py
│   └── test_validators.py
├── test_pipeline/
│   ├── test_runner.py
│   └── test_cdr.py
└── test_worker/
    └── test_tasks.py
```

Example test:
```python
# tests/test_pipeline/test_cdr.py
import pytest
from pipeline.cdr import annotate_cdrs

def test_annotate_cdrs():
    result = annotate_cdrs("samples/vhh_sample.pdb", scheme="chothia")
    assert result.scheme == "chothia"
    assert len(result.chains) > 0
```

Run tests:
```bash
pytest tests/ -v
```

### Environment Variables Reference

Create `.env` file (don't commit to Git):
```bash
# .env
STORAGE_ROOT=/tmp/abdesign/submissions
REDIS_URL=redis://localhost:6379/0
QUEUE_NAME=default
MAX_FILE_SIZE=52428800
API_KEY=your-secret-key-here
CORS_ORIGINS=http://localhost:3000,http://localhost:8080
RATE_LIMIT_PER_MINUTE=60
```

Use python-dotenv to load:
```bash
pip install python-dotenv
```

```python
from dotenv import load_dotenv
load_dotenv()
```

### Docker Development (Optional)

Create `Dockerfile`:
```dockerfile
FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    redis-server \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy code
COPY . .

# Expose port
EXPOSE 8000

# Start command
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Create `docker-compose.yml`:
```yaml
version: '3.8'

services:
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
  
  api:
    build: .
    ports:
      - "8000:8000"
    environment:
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      - redis
    volumes:
      - ./:/app
      - /tmp/submissions:/tmp/submissions
  
  worker:
    build: .
    command: python -m worker.worker
    environment:
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      - redis
    volumes:
      - ./:/app
      - /tmp/submissions:/tmp/submissions
```

Use Docker Compose:
```bash
docker-compose up -d
docker-compose logs -f
docker-compose down
```

### Common Development Issues

#### Issue 1: Module Import Error
```
ModuleNotFoundError: No module named 'api'
```

**Solution**:
```bash
# Make sure you're in project root
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
```

#### Issue 2: Redis Connection Failed
```
redis.exceptions.ConnectionError: Error connecting to Redis
```

**Solution**:
```bash
# Check if Redis is running
redis-cli ping

# Check environment variable
echo $REDIS_URL

# Start Redis
redis-server --daemonize yes
```

#### Issue 3: Worker Not Processing Tasks

**Checklist**:
1. Is Redis running?
2. Are API and Worker using the same Redis URL?
3. Is the queue name consistent?
4. Is Worker running?

```bash
# View queue contents
redis-cli LLEN rq:queue:default

# View Worker process
ps aux | grep worker
```

#### Issue 4: File Permission Error

```bash
# Ensure temp directory is writable
sudo chmod -R 777 /tmp/submissions
# Or use user directory
export STORAGE_ROOT=$HOME/abdesign/submissions
mkdir -p $HOME/abdesign/submissions
```

### Performance Profiling

Using Python profiler:
```python
import cProfile
import pstats

def profile_pipeline():
    profiler = cProfile.Profile()
    profiler.enable()
    
    # Run your code
    result = run_pipeline("separate", inputs)
    
    profiler.disable()
    stats = pstats.Stats(profiler)
    stats.sort_stats('cumulative')
    stats.print_stats(20)

profile_pipeline()
```

Using `time` command:
```bash
time python scripts/smoke_test.py
```

### Git Workflow

```bash
# Create feature branch
git checkout -b feature/my-new-feature

# Commit changes
git add .
git commit -m "Add my new feature"

# Push to remote
git push origin feature/my-new-feature

# Create Pull Request (on GitHub web interface)
```

### Useful Resources

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Redis Queue (RQ) Documentation](https://python-rq.org/)
- [AbNumber Documentation](https://github.com/prihoda/abnumber)
- [Gemmi Documentation](https://gemmi.readthedocs.io/)
- [Pydantic Documentation](https://docs.pydantic.dev/)
