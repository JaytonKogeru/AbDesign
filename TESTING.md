# Quick status check and smoke test guide

## 当前仓库状态
- 默认分支：`work`
- 当前没有未解决的冲突；使用 `git status -sb` 可快速确认工作区是否干净。

## 环境准备与依赖安装

推荐使用 Conda 管理环境和非 Python 依赖（如 Redis）。

### 1. 安装 Conda (如果尚未安装)
如果系统中没有 Conda，请先安装 [Miniconda](https://docs.conda.io/en/latest/miniconda.html) 或 Anaconda。

### 2. 创建环境并安装依赖
```bash
# 创建 Python 3.10 环境 (推荐)
conda create -n abdesign python=3.10 -y

# 激活环境
conda activate abdesign

# 安装 Redis Server (必须，用于任务队列通信)
conda install -c conda-forge redis-server -y

# 安装 Python 依赖
pip install -r requirements.txt
```

## 启动服务

需要启动三个组件：Redis、API 服务和 Worker。建议在不同的终端窗口中运行，或使用后台运行命令。

### 1. 启动 Redis 服务
Worker 和 API 通过 Redis 进行通信。
```bash
# 后台启动 Redis
redis-server --daemonize yes

# 检查 Redis 是否运行
ps aux | grep redis-server
```

### 2. 启动 API 服务
```bash
# 确保已激活环境：conda activate abdesign
uvicorn api.main:app --host 0.0.0.0 --port 8000 --log-level info
```

### 3. 启动 Worker
```bash
# 确保已激活环境：conda activate abdesign
python -m worker.worker
```

## 运行功能冒烟测试
仓库已提供示例结构文件：`samples/vhh_sample.pdb` 与 `samples/target_sample.pdb`。
在新的终端执行：
```bash
# 确保已激活环境：conda activate abdesign
python scripts/smoke_test.py --base-url http://localhost:8000
```
脚本会：
1. 以 `separate` 模式提交示例 VHH/target 文件；
2. 轮询 `/result/{task_id}` 直至任务完成；
3. 打印任务状态和生成的工件路径（预测结构与打分表）。

若需要 API Key，添加参数：
```bash
python scripts/smoke_test.py --base-url http://localhost:8000 --api-key <YOUR_KEY>
```

## 常见问题
- **Worker 接收不到任务**：请确保 `redis-server` 已启动，且 API 和 Worker 连接的是同一个 Redis 实例（默认 `localhost:6379`）。
- **端口冲突**：如果 8000 端口被占用，可以在启动 uvicorn 时指定其他端口，并在 smoke_test.py 中更新 `--base-url`。

## 手动验证步骤（可选）
- 通过 `curl` 查看健康检查：
  ```bash
  curl -s http://localhost:8000/health
  ```
- 如需清理历史任务，删除状态文件与存储目录：
  ```bash
  rm -f /tmp/task_state.json
  rm -rf /tmp/submissions
  ```
