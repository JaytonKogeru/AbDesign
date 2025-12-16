# Quick status check and smoke test guide

## 当前仓库状态
- 默认分支：`work`
- 当前没有未解决的冲突；使用 `git status -sb` 可快速确认工作区是否干净。

## 依赖安装（Conda / uv）
你可以使用 conda 或 [astral-sh/uv](https://docs.astral.sh/uv/) 来管理依赖，避免 venv。
仓库曾包含精简的 vendored `abnumber/` 目录，该子集已删除；现在默认从 PyPI 安装上游 `abnumber[anarci]` 包（见 `requirements.txt`），可提供标准的 ANARCI 编号。

### 选项 1：Conda
```bash
conda create -n vhh-api python=3.11 -y
conda activate vhh-api
python -m pip install -r requirements.txt
```

### 选项 2：uv
```bash
# 确保已安装 uv：pip install uv
uv venv .uvenv --python 3.11
source .uvenv/bin/activate
uv pip install -r requirements.txt

安装完成后可运行一次快速校验，确保使用的是上游 AbNumber，并且编号能处理插入位点：
```bash
# 验收脚本（检查 abnumber 源路径、版本、编号输出）
python scripts/verify_abnumber.py

# 或使用现有单元测试
python -m unittest tests/test_abnumber_integration.py
```
```

## 启动服务与 Worker
在两个终端分别执行：
```bash
# 终端 1：启动 API（默认监听 8000）
uvicorn api.main:app --host 0.0.0.0 --port 8000 --log-level info

# 终端 2：启动队列 Worker
python -m worker.worker
```

如启用了 API Key，设置环境变量 `API_KEY` 并在后续请求中通过 `X-API-Key` 传递。

## 运行功能冒烟测试
仓库已提供示例结构文件：`samples/vhh_sample.pdb` 与 `samples/target_sample.pdb`。
在第三个终端执行：
```bash
python scripts/smoke_test.py --base-url http://localhost:8000
```
脚本会：
1. 以 `separate` 模式提交示例 VHH/target 文件；
2. 轮询 `/result/{task_id}` 直至任务完成；
3. 打印任务状态和生成的工件路径（预测结构、打分表以及 CDR 注释文件）。

若需要 API Key，添加参数：
```bash
python scripts/smoke_test.py --base-url http://localhost:8000 --api-key <YOUR_KEY>
```

## 验收命令清单（从干净环境开始）
1. 安装依赖：`python -m pip install -r requirements.txt`
2. 运行 AbNumber 验收脚本：`python scripts/verify_abnumber.py`
3. 启动服务并运行冒烟测试：`python scripts/smoke_test.py --base-url http://localhost:8000`

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
