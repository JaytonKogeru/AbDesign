# Quick status check and smoke test guide

## 当前仓库状态
- 默认分支：`work`
- 当前没有未解决的冲突；使用 `git status -sb` 可快速确认工作区是否干净。

## 依赖安装
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt requests
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
3. 打印任务状态和生成的工件路径（预测结构与打分表）。

若需要 API Key，添加参数：
```bash
python scripts/smoke_test.py --base-url http://localhost:8000 --api-key <YOUR_KEY>
```

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
