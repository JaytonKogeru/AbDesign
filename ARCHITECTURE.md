# AbDesign 架构文档 / Architecture Documentation

[中文](#中文版) | [English](#english-version)

---

## 中文版

### 系统架构概览

AbDesign 采用微服务架构，将系统分为三个主要组件：

1. **API 服务层**：接收 HTTP 请求，处理文件上传
2. **消息队列层**：使用 Redis 作为任务队列的消息中间件
3. **工作进程层**：后台执行计算密集型任务

### 数据流图

```
用户请求 → API (FastAPI)
              │
              ├─→ 验证输入
              ├─→ 保存文件到临时存储
              ├─→ 创建任务记录
              ├─→ 入队到 Redis
              └─→ 返回 task_id
                     │
                     ↓
              Redis Queue
                     │
                     ↓
              Worker (RQ) ← 监听队列
                     │
                     ├─→ 读取文件
                     ├─→ 执行 Pipeline
                     │     ├─→ CDR 标注
                     │     ├─→ 结构对齐（预留）
                     │     ├─→ 结合位点预测（预留）
                     │     └─→ 打分模型（模拟）
                     ├─→ 保存结果
                     └─→ 更新任务状态
                            │
                            ↓
              用户轮询 /result/{task_id}
                            │
                            ↓
              返回结果 + 下载链接
```

### 模块详解

#### 1. API 模块 (`api/`)

**main.py** - 应用入口点
- 定义 FastAPI 应用实例
- 配置 CORS 中间件
- 实现请求日志中间件
- 定义路由处理器

**关键路由**:
```python
POST /submit          # 提交新任务
GET  /result/{task_id}  # 查询任务状态和结果
GET  /download/{task_id}/{artifact}  # 下载生成的文件
GET  /health          # 健康检查
```

**config.py** - 配置管理
```python
@dataclass(frozen=True)
class Settings:
    storage_root: str         # 文件存储路径
    redis_url: str            # Redis 连接 URL
    queue_name: str           # 队列名称
    max_file_size: int        # 最大文件大小限制
    api_key: str              # API 密钥（可选）
    cors_origins: List[str]   # CORS 允许的源
    rate_limit_per_minute: int # 速率限制
```

**storage.py** - 文件管理
- `generate_task_id()`: 生成唯一任务 ID（UUID）
- `create_temp_directory()`: 为任务创建临时目录
- 文件保存到 `{STORAGE_ROOT}/{task_id}/` 目录

**task_store.py** - 任务状态持久化
- 使用 JSON 文件存储任务状态（生产环境建议使用数据库）
- 任务状态：`queued` → `started` → `succeeded`/`failed`

**schemas.py** - 数据模型
```python
class UploadRequest(BaseModel):
    file_name: str
    file_size: int
    content: bytes
    
    @validator("file_name")
    def validate_extension(cls, value: str):
        # 验证文件扩展名（.pdb, .cif）
        ...

    @validator("file_size")
    def validate_file_size(cls, value: int):
        # 验证文件大小
        ...
```

**validators.py** - 输入验证
- 文件格式验证
- 大小限制检查
- 参数合法性验证

**results.py** - 结果处理
- 格式化任务结果
- 生成下载链接
- 聚合元数据

#### 2. Pipeline 模块 (`pipeline/`)

**runner.py** - 流水线编排器

核心数据结构：
```python
@dataclass
class PipelineConfig:
    mode: str                        # 运行模式
    output_dir: Path                 # 输出目录
    cdr_numbering_scheme: str        # CDR 编号方案
    alignment: AlignmentConfig       # 对齐配置
    binding_site: BindingSiteConfig  # 结合位点配置
    scoring: ScoringConfig           # 打分配置
    keep_intermediates: bool         # 是否保留中间文件

@dataclass
class PipelineResult:
    artifacts: PipelineArtifacts     # 生成的文件
    summary_score: float             # 总体评分
    numbering_scheme: str            # 使用的编号方案
    alignment: Dict[str, Any]        # 对齐结果
    binding_site_prediction: Dict    # 结合位点预测
    scoring: Dict[str, Any]          # 打分详情
    cdr_annotation: Dict[str, Any]   # CDR 标注结果
    config: Dict[str, Any]           # 使用的配置
```

执行流程：
1. 解析输入参数
2. 构建 PipelineConfig
3. 创建输出目录
4. 执行各个分析步骤：
   - 结构对齐（目前为模拟实现）
   - 结合位点预测（目前为模拟实现）
   - 打分模型（目前为模拟实现）
   - **CDR 标注**（完整实现）
5. 写入结果文件
6. 返回 PipelineResult

**cdr.py** - CDR 标注核心

关键函数：
```python
def annotate_cdrs(structure_path, scheme='chothia') -> CDRAnnotationResult:
    """
    标注结构中的 CDR 区域
    
    流程：
    1. 使用 gemmi 解析结构文件
    2. 提取每条链的氨基酸序列
    3. 使用 abnumber 进行 CDR 识别
    4. 返回标注结果
    """
```

数据结构：
```python
@dataclass
class ChainAnnotation:
    chain_id: str                    # 链标识符
    sequence: str                    # 氨基酸序列
    cdrs: List[Dict[str, object]]    # CDR 区域列表
    numbering: List[Dict]            # 编号信息

@dataclass
class CDRAnnotationResult:
    scheme: str                      # 编号方案
    chains: List[ChainAnnotation]    # 所有链的标注
```

#### 3. Worker 模块 (`worker/`)

**worker.py** - 工作进程主程序
```python
def main():
    settings = get_settings()
    connection = get_redis_connection()
    queue = get_queue(name=settings.queue_name)
    with Connection(connection):
        worker = Worker([queue])
        worker.work()  # 阻塞式监听队列
```

**tasks.py** - 任务定义
```python
def run_pipeline(task_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    后台任务执行函数
    
    步骤：
    1. 更新任务状态为 'started'
    2. 准备输入参数
    3. 调用 pipeline.runner.run_pipeline()
    4. 处理结果，生成摘要
    5. 更新任务状态为 'succeeded' 或 'failed'
    6. 返回结果元数据
    """
```

**queue.py** - 队列管理
```python
def get_redis_connection() -> Redis:
    """创建 Redis 连接"""
    
def get_queue(name: str, connection: Redis = None) -> Queue:
    """获取或创建队列实例"""
```

### 技术选型理由

| 技术 | 选择理由 |
|------|---------|
| **FastAPI** | 现代化 Python Web 框架，高性能，自动生成 API 文档 |
| **Redis + RQ** | 轻量级任务队列，易于部署，支持任务重试和监控 |
| **gemmi** | 高性能结构文件解析库，支持 PDB 和 mmCIF |
| **abnumber** | 专业的抗体编号库，支持多种编号方案 |
| **Pydantic** | 数据验证和序列化，类型安全 |

### 扩展性设计

#### 预留接口

系统设计时预留了多个扩展点：

1. **结构对齐模块**
```python
def _run_structure_alignment(config: AlignmentConfig, inputs):
    if not config.enabled:
        return {"status": "skipped"}
    # TODO: 实现真实的结构对齐算法
    # 可以集成 TM-align, PyMOL, BioPython 等
```

2. **结合位点预测**
```python
def _predict_binding_sites(config: BindingSiteConfig, inputs):
    if not config.enabled:
        return {"status": "skipped"}
    # TODO: 集成 P2Rank 或其他预测工具
```

3. **打分模型**
```python
def _score_models(config: ScoringConfig, binding_site_result, inputs):
    if not config.enabled:
        return {"status": "skipped", "summary_score": 0.0}
    # TODO: 集成深度学习打分模型
    # 可以使用 PyTorch/TensorFlow 模型
```

#### 添加新模块的步骤

1. 在 `pipeline/` 创建新模块文件
2. 定义配置类（继承自 dataclass）
3. 实现分析函数
4. 在 `runner.py` 中集成
5. 更新 `PipelineConfig` 和 `PipelineResult`
6. 添加测试用例

### 性能优化建议

1. **并发处理**
   - 增加 Worker 进程数量
   - 使用多线程/多进程处理独立任务

2. **缓存优化**
   - Redis 缓存常用结果
   - 本地缓存小文件

3. **数据库升级**
   - 生产环境替换 JSON 文件存储为 PostgreSQL/MongoDB
   - 使用连接池

4. **文件存储**
   - 大文件使用对象存储（S3, MinIO）
   - 实现文件过期清理机制

### 监控和日志

当前实现：
- 请求日志（时间、路径、状态码、耗时）
- Worker 任务日志
- 异常堆栈跟踪

生产环境建议：
- 集成 Prometheus + Grafana 监控
- 使用 ELK Stack 收集日志
- 添加性能指标追踪
- 实现告警机制

---

## English Version

### System Architecture Overview

AbDesign adopts a microservices architecture, dividing the system into three main components:

1. **API Service Layer**: Receives HTTP requests, handles file uploads
2. **Message Queue Layer**: Uses Redis as message middleware for task queues
3. **Worker Process Layer**: Executes compute-intensive tasks in the background

### Data Flow Diagram

```
User Request → API (FastAPI)
               │
               ├─→ Validate Input
               ├─→ Save Files to Temporary Storage
               ├─→ Create Task Record
               ├─→ Enqueue to Redis
               └─→ Return task_id
                      │
                      ↓
               Redis Queue
                      │
                      ↓
               Worker (RQ) ← Listen to Queue
                      │
                      ├─→ Read Files
                      ├─→ Execute Pipeline
                      │     ├─→ CDR Annotation
                      │     ├─→ Structure Alignment (reserved)
                      │     ├─→ Binding Site Prediction (reserved)
                      │     └─→ Scoring Model (mock)
                      ├─→ Save Results
                      └─→ Update Task Status
                             │
                             ↓
               User Polls /result/{task_id}
                             │
                             ↓
               Return Results + Download Links
```

### Module Details

#### 1. API Module (`api/`)

**main.py** - Application Entry Point
- Defines FastAPI application instance
- Configures CORS middleware
- Implements request logging middleware
- Defines route handlers

**Key Routes**:
```python
POST /submit                          # Submit new task
GET  /result/{task_id}                # Query task status and results
GET  /download/{task_id}/{artifact}   # Download generated files
GET  /health                          # Health check
```

**config.py** - Configuration Management
```python
@dataclass(frozen=True)
class Settings:
    storage_root: str                 # File storage path
    redis_url: str                    # Redis connection URL
    queue_name: str                   # Queue name
    max_file_size: int                # Max file size limit
    api_key: str                      # API key (optional)
    cors_origins: List[str]           # CORS allowed origins
    rate_limit_per_minute: int        # Rate limit
```

**storage.py** - File Management
- `generate_task_id()`: Generate unique task ID (UUID)
- `create_temp_directory()`: Create temporary directory for task
- Files saved to `{STORAGE_ROOT}/{task_id}/` directory

**task_store.py** - Task State Persistence
- Uses JSON file for task state storage (database recommended for production)
- Task states: `queued` → `started` → `succeeded`/`failed`

**schemas.py** - Data Models
```python
class UploadRequest(BaseModel):
    file_name: str
    file_size: int
    content: bytes
    
    @validator("file_name")
    def validate_extension(cls, value: str):
        # Validate file extension (.pdb, .cif)
        ...

    @validator("file_size")
    def validate_file_size(cls, value: int):
        # Validate file size
        ...
```

**validators.py** - Input Validation
- File format validation
- Size limit checks
- Parameter validity verification

**results.py** - Result Processing
- Format task results
- Generate download links
- Aggregate metadata

#### 2. Pipeline Module (`pipeline/`)

**runner.py** - Pipeline Orchestrator

Core Data Structures:
```python
@dataclass
class PipelineConfig:
    mode: str                        # Execution mode
    output_dir: Path                 # Output directory
    cdr_numbering_scheme: str        # CDR numbering scheme
    alignment: AlignmentConfig       # Alignment config
    binding_site: BindingSiteConfig  # Binding site config
    scoring: ScoringConfig           # Scoring config
    keep_intermediates: bool         # Keep intermediate files

@dataclass
class PipelineResult:
    artifacts: PipelineArtifacts     # Generated files
    summary_score: float             # Overall score
    numbering_scheme: str            # Numbering scheme used
    alignment: Dict[str, Any]        # Alignment results
    binding_site_prediction: Dict    # Binding site predictions
    scoring: Dict[str, Any]          # Scoring details
    cdr_annotation: Dict[str, Any]   # CDR annotation results
    config: Dict[str, Any]           # Configuration used
```

Execution Flow:
1. Parse input parameters
2. Build PipelineConfig
3. Create output directory
4. Execute analysis steps:
   - Structure alignment (currently mock)
   - Binding site prediction (currently mock)
   - Scoring model (currently mock)
   - **CDR annotation** (full implementation)
5. Write result files
6. Return PipelineResult

**cdr.py** - CDR Annotation Core

Key Functions:
```python
def annotate_cdrs(structure_path, scheme='chothia') -> CDRAnnotationResult:
    """
    Annotate CDR regions in structure
    
    Process:
    1. Parse structure file using gemmi
    2. Extract amino acid sequence for each chain
    3. Identify CDRs using abnumber
    4. Return annotation results
    """
```

Data Structures:
```python
@dataclass
class ChainAnnotation:
    chain_id: str                    # Chain identifier
    sequence: str                    # Amino acid sequence
    cdrs: List[Dict[str, object]]    # CDR region list
    numbering: List[Dict]            # Numbering information

@dataclass
class CDRAnnotationResult:
    scheme: str                      # Numbering scheme
    chains: List[ChainAnnotation]    # Annotations for all chains
```

#### 3. Worker Module (`worker/`)

**worker.py** - Worker Process Main Program
```python
def main():
    settings = get_settings()
    connection = get_redis_connection()
    queue = get_queue(name=settings.queue_name)
    with Connection(connection):
        worker = Worker([queue])
        worker.work()  # Blocking listen to queue
```

**tasks.py** - Task Definitions
```python
def run_pipeline(task_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Background task execution function
    
    Steps:
    1. Update task status to 'started'
    2. Prepare input parameters
    3. Call pipeline.runner.run_pipeline()
    4. Process results, generate summary
    5. Update task status to 'succeeded' or 'failed'
    6. Return result metadata
    """
```

**queue.py** - Queue Management
```python
def get_redis_connection() -> Redis:
    """Create Redis connection"""
    
def get_queue(name: str, connection: Redis = None) -> Queue:
    """Get or create queue instance"""
```

### Technology Choices

| Technology | Rationale |
|------------|-----------|
| **FastAPI** | Modern Python web framework, high performance, automatic API docs |
| **Redis + RQ** | Lightweight task queue, easy to deploy, supports retry and monitoring |
| **gemmi** | High-performance structure file parsing, supports PDB and mmCIF |
| **abnumber** | Professional antibody numbering library, multiple schemes supported |
| **Pydantic** | Data validation and serialization, type safety |

### Scalability Design

#### Reserved Interfaces

The system has multiple extension points:

1. **Structure Alignment Module**
```python
def _run_structure_alignment(config: AlignmentConfig, inputs):
    if not config.enabled:
        return {"status": "skipped"}
    # TODO: Implement real structure alignment
    # Can integrate TM-align, PyMOL, BioPython, etc.
```

2. **Binding Site Prediction**
```python
def _predict_binding_sites(config: BindingSiteConfig, inputs):
    if not config.enabled:
        return {"status": "skipped"}
    # TODO: Integrate P2Rank or other prediction tools
```

3. **Scoring Model**
```python
def _score_models(config: ScoringConfig, binding_site_result, inputs):
    if not config.enabled:
        return {"status": "skipped", "summary_score": 0.0}
    # TODO: Integrate deep learning scoring model
    # Can use PyTorch/TensorFlow models
```

#### Steps to Add New Module

1. Create new module file in `pipeline/`
2. Define config class (inherit from dataclass)
3. Implement analysis function
4. Integrate in `runner.py`
5. Update `PipelineConfig` and `PipelineResult`
6. Add test cases

### Performance Optimization Suggestions

1. **Concurrent Processing**
   - Increase number of Worker processes
   - Use multi-threading/multi-processing for independent tasks

2. **Caching Optimization**
   - Redis cache for frequently used results
   - Local cache for small files

3. **Database Upgrade**
   - Replace JSON file storage with PostgreSQL/MongoDB in production
   - Use connection pooling

4. **File Storage**
   - Use object storage (S3, MinIO) for large files
   - Implement file expiration cleanup mechanism

### Monitoring and Logging

Current Implementation:
- Request logs (time, path, status code, duration)
- Worker task logs
- Exception stack traces

Production Recommendations:
- Integrate Prometheus + Grafana monitoring
- Use ELK Stack for log collection
- Add performance metric tracking
- Implement alerting mechanism
