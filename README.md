# AbDesign - 抗体设计工具集成平台

[![English](https://img.shields.io/badge/docs-English-blue)](README_EN.md)
[![Architecture](https://img.shields.io/badge/docs-Architecture-green)](ARCHITECTURE.md)
[![Development](https://img.shields.io/badge/docs-Development-orange)](DEVELOPMENT.md)
[![Testing](https://img.shields.io/badge/docs-Testing-red)](TESTING.md)

## 项目简介

AbDesign 是一个**抗体设计工具的统一入口平台**，旨在将用户输入的结构信息转化为各种抗体设计工具能够理解的配置语言和运行命令。该平台整合了 RFantibody、BoltzGen 等主流抗体设计工具，并可轻松扩展集成更多工具。

## 📚 文档导航

- **[README (English)](README_EN.md)** - 英文版说明文档
- **[架构文档 (ARCHITECTURE.md)](ARCHITECTURE.md)** - 详细的技术架构和模块说明
- **[开发指南 (DEVELOPMENT.md)](DEVELOPMENT.md)** - API 详细信息、快速开发指南和常见问题
- **[测试指南 (TESTING.md)](TESTING.md)** - 环境准备和测试方法

## 核心定位

AbDesign 作为**统一网关**，解决以下问题：

1. **统一输入接口**：提供标准化的结构文件上传和参数配置方式
2. **自动格式转换**：将用户输入转化为各工具特定的配置文件（YAML、JSON、命令行参数等）
3. **工具编排**：协调多个抗体设计工具的执行流程
4. **结果整合**：收集和标准化各工具的输出结果
5. **可扩展性**：轻松添加新的抗体设计工具集成

## 已集成的工具

### 🧬 RFantibody
基于 RFdiffusion 的抗体设计工具，专注于热点驱动的抗体优化。

**AbDesign 提供的能力：**
- 自动将 PDB/mmCIF 结构转换为 RFantibody 输入格式
- 解析用户指定的热点残基并生成 HLT 文件
- 配置设计参数（设计区域、生成数量等）
- 通过 Docker 容器化执行或直接调用
- 收集和标准化设计结果

**使用示例：**
```bash
curl -X POST "http://localhost:8000/submit" \
  -F "mode=separate" \
  -F "vhh_file=@nanobody.pdb" \
  -F "target_file=@target.pdb" \
  -F "user_params={\"integrations\":{\"rfantibody\":{\"enabled\":true,\"num_designs\":20}}}"
```

### 🔬 BoltzGen
基于 Boltz-1 模型的结构预测工具，适用于纳米抗体-靶标复合物预测。

**AbDesign 提供的能力：**
- 自动生成 BoltzGen YAML 配置文件
- 处理纳米抗体和靶标的链映射关系
- 批量设计任务管理
- Docker 容器化执行支持
- 输出结果验证和收集

**使用示例：**
```bash
curl -X POST "http://localhost:8000/submit" \
  -F "mode=separate" \
  -F "vhh_file=@nanobody.pdb" \
  -F "target_file=@target.pdb" \
  -F "user_params={\"integrations\":{\"boltzgen\":{\"enabled\":true,\"protocol\":\"nanobody-anything\",\"num_designs\":50}}}"
```

## 辅助功能模块

为支持工具集成，AbDesign 提供以下辅助功能：

### 1. 结构标准化与残基映射
- 统一 PDB 和 mmCIF 格式处理
- 生成规范化的 mmCIF 结构
- 建立 auth/label 残基标识符映射
- 支持热点残基的格式转换

### 2. CDR 区域标注
- 自动识别和标注 CDR1、CDR2、CDR3 区域
- 支持多种编号方案（Chothia、IMGT、Kabat 等）
- 为工具提供精确的序列和结构信息

### 3. 异步任务管理
- 基于 Redis 和 RQ 的任务队列
- 支持长时间运行的设计任务
- 实时任务状态查询和结果下载

## 技术架构

AbDesign 采用微服务架构，核心是**配置生成和工具编排**：

```
┌─────────────────┐
│   用户输入       │
│ (结构文件+参数)  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  标准化处理层    │
│  - 格式转换     │
│  - 残基映射     │
│  - CDR 标注     │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  配置生成层      │
│  - YAML 配置    │
│  - HLT 文件     │
│  - 命令行参数   │
└────────┬────────┘
         │
         ├──────────┬──────────┬─────────┐
         ▼          ▼          ▼         ▼
    ┌────────┐ ┌────────┐ ┌────────┐  ...
    │RFantib-│ │BoltzGen│ │未来工具│
    │  ody   │ │        │ │        │
    └────┬───┘ └───┬────┘ └───┬────┘
         │         │          │
         └─────────┴──────────┘
                   │
                   ▼
         ┌─────────────────┐
         │  结果收集整合    │
         └─────────────────┘
```

### 核心模块

1. **API 层 (`api/`)**：提供 HTTP 接口，处理文件上传和任务提交
2. **流水线层 (`pipeline/`)**：结构标准化、CDR 标注、残基映射
3. **集成层 (`integrations/`)**：各工具的适配器和配置生成器
4. **工作进程 (`worker/`)**：异步任务执行和结果收集

详细架构说明请参见 [ARCHITECTURE.md](ARCHITECTURE.md)

## 快速开始

### 环境要求
- Python 3.10+
- Redis Server
- 依赖包（见 requirements.txt）

### 安装步骤

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

#### 2. 启动服务

需要启动三个组件（建议使用三个独立终端）：

**终端 1 - Redis:**
```bash
redis-server --daemonize yes
```

**终端 2 - API 服务:**
```bash
uvicorn api.main:app --host 0.0.0.0 --port 8000 --log-level info
```

**终端 3 - Worker:**
```bash
python -m worker.worker
```

#### 3. 提交设计任务

**基础用法（仅标准化和 CDR 标注）：**
```bash
curl -X POST "http://localhost:8000/submit" \
  -F "mode=separate" \
  -F "vhh_file=@samples/vhh_sample.pdb" \
  -F "target_file=@samples/target_sample.pdb"
```

**启用 RFantibody 设计：**
```bash
curl -X POST "http://localhost:8000/submit" \
  -F "mode=separate" \
  -F "vhh_file=@samples/vhh_sample.pdb" \
  -F "target_file=@samples/target_sample.pdb" \
  -F "user_params={\"target_hotspots\":[\"A:305\",\"A:456\"],\"integrations\":{\"rfantibody\":{\"enabled\":true,\"num_designs\":20,\"design_loops\":[\"H1\",\"H3\"]}}}"
```

**启用 BoltzGen 预测：**
```bash
curl -X POST "http://localhost:8000/submit" \
  -F "mode=separate" \
  -F "vhh_file=@samples/vhh_sample.pdb" \
  -F "target_file=@samples/target_sample.pdb" \
  -F "user_params={\"integrations\":{\"boltzgen\":{\"enabled\":true,\"protocol\":\"nanobody-anything\",\"num_designs\":50}}}"
```

#### 4. 查询结果

```bash
# 获取任务状态和结果
curl "http://localhost:8000/result/{task_id}"

# 下载生成的配置文件
curl "http://localhost:8000/download/{task_id}/rfantibody_config" -o config.yaml
```

## 添加新工具集成

AbDesign 设计为可扩展的架构，添加新工具仅需三步：

### 步骤 1: 创建工具适配器

在 `integrations/` 目录创建新文件，例如 `newtool.py`：

```python
from pathlib import Path
from typing import Dict, Any

def run_newtool(
    task_dir: Path,
    input_structure: Path,
    config: Dict[str, Any],
    **kwargs
) -> Dict[str, Any]:
    """
    新工具的适配器函数
    
    Args:
        task_dir: 任务工作目录
        input_structure: 输入结构文件
        config: 工具配置参数
    
    Returns:
        包含输出文件路径和元数据的字典
    """
    # 1. 生成工具特定的配置文件
    config_path = task_dir / "newtool_config.yaml"
    # ... 写入配置
    
    # 2. 执行工具（Docker 或直接调用）
    # ... 调用命令
    
    # 3. 收集和返回结果
    return {
        "status": "success",
        "output_files": [...],
        "metadata": {...}
    }
```

### 步骤 2: 集成到流水线

在 `pipeline/runner.py` 中添加集成点：

```python
from integrations.newtool import run_newtool

# 在 IntegrationConfig 中添加配置
@dataclass
class NewToolIntegrationConfig:
    enabled: bool = False
    param1: str = "default"
    # ... 其他参数

# 在 run_pipeline 函数中调用
if config.integrations.newtool.enabled:
    newtool_result = run_newtool(
        task_dir=config.output_dir,
        input_structure=inputs.get("structure"),
        config=config.integrations.newtool
    )
```

### 步骤 3: 更新 API Schema

在 `api/schemas.py` 中添加配置模型：

```python
class NewToolConfig(BaseModel):
    enabled: bool = False
    param1: Optional[str] = None
```

就这么简单！新工具现在可以通过 API 调用了。

## 配置选项

主要通过环境变量配置：

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| `STORAGE_ROOT` | `/tmp/submissions` | 文件存储根目录 |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis 连接地址 |
| `QUEUE_NAME` | `default` | 任务队列名称 |
| `MAX_FILE_SIZE` | `52428800` (50MB) | 最大文件大小 |
| `API_KEY` | 空字符串 | API 访问密钥（可选）|

详细 API 文档和配置选项请参见 [DEVELOPMENT.md](DEVELOPMENT.md)

## 项目结构

```
AbDesign/
├── integrations/          # 🔧 工具适配器（核心）
│   ├── rfantibody.py      # RFantibody 适配器
│   ├── boltzgen.py        # BoltzGen 适配器
│   └── normalize.py       # 标准化工具
├── pipeline/              # 📋 辅助处理模块
│   ├── runner.py          # 流水线编排器
│   ├── cdr.py             # CDR 标注
│   └── epitope/           # 结构标准化和映射
├── api/                   # 🌐 Web 接口
├── worker/                # ⚙️ 异步任务处理
├── scripts/               # 🛠️ 工具脚本
├── tests/                 # ✅ 测试套件
└── samples/               # 📁 示例文件
```

## 关键依赖

| 依赖包 | 用途 |
|--------|------|
| `fastapi` + `uvicorn` | Web 服务框架 |
| `redis` + `rq` | 异步任务队列 |
| `gemmi` | 结构文件解析 |
| `abnumber[anarci]` | CDR 识别和编号 |
| `biopython` | 生物信息学工具 |

## 测试和验证

```bash
# 快速自检（无需启动服务）
make selftest

# 完整测试（需要启动服务）
python scripts/smoke_test.py --base-url http://localhost:8000

# 单元测试
pytest
```

详细测试指南请参见 [TESTING.md](TESTING.md)

## 常见问题

### 工具集成相关

**Q: 如何确认 RFantibody/BoltzGen 是否可用？**

检查 Docker 镜像或直接调用：
```bash
docker images | grep rfantibody
docker images | grep boltzgen
```

**Q: 如何查看生成的配置文件？**

配置文件保存在任务目录中，可通过下载端点获取：
```bash
curl "http://localhost:8000/download/{task_id}/rfantibody_config" -o config.yaml
```

**Q: 是否支持同时运行多个工具？**

是的，可以在 `user_params` 中同时启用多个集成：
```json
{
  "integrations": {
    "rfantibody": {"enabled": true, "num_designs": 20},
    "boltzgen": {"enabled": true, "num_designs": 50}
  }
}
```

### 服务运行相关

**Q: Redis 连接失败？**

检查 Redis 是否运行并确认连接地址：
```bash
ps aux | grep redis-server
redis-cli ping  # 应返回 PONG
```

**Q: 如何查看任务日志？**

Worker 日志包含详细的执行信息：
```bash
# 在 worker 终端查看实时日志
# 或查看日志文件（如果配置了）
tail -f worker.log
```

更多技术细节和 API 文档请参见 [DEVELOPMENT.md](DEVELOPMENT.md)

## 许可证

本项目的许可证信息请查看仓库。

## 贡献

欢迎提交 Issue 和 Pull Request！

## 联系方式

如有问题，请在 GitHub 仓库中创建 Issue。

---

**版本**: 0.1.0  
**最后更新**: 2025-12
