# ODMR 启动说明

- **仓库**：https://github.com/zhuziyang-ui/odmr  
- **全新空白电脑（有网）**：请先完整阅读 [ENV_SETUP.md](./ENV_SETUP.md)（从安装 Git / Python / Node 到首次启动）。  
- **无外网 / 实验室隔离网**：请看 [OFFLINE_SETUP.md](./OFFLINE_SETUP.md)（U 盘离线包）。

本文件面向 **已装好环境** 的日常启停与更新。

## 一键启停（推荐）

在资源管理器中双击项目根目录下的：

| 文件 | 作用 |
| --- | --- |
| `start.bat` | 先停止旧进程，再分别打开后端 / 前端窗口 |
| `stop.bat` | 结束占用 **8000**、**5173** 端口的进程 |

等价命令行：

```bat
cd /d 你的项目目录
start.bat
stop.bat
```

启动后访问：

- 前端：http://127.0.0.1:5173  
- 后端：http://127.0.0.1:8000  
- API 文档：http://127.0.0.1:8000/docs  

功能页包括：设备、锁相、微波、ODMR、电流测量（含 PID 闭环）、状态估计（EKF/UKF）等。

## 单独启停

```bat
scripts\start-backend.bat
scripts\start-frontend.bat
scripts\stop-services.bat
```

## 依赖安装（代码更新后）

```bat
cd /d 你的项目目录
git pull
python -m pip install -r requirements.txt
cd frontend
npm.cmd install
```

若前端启动报 esbuild 相关错误：

```bat
cd frontend
npm.cmd approve-scripts esbuild
npm.cmd rebuild esbuild
```

## 自检

```bat
cd /d 你的项目目录
python -c "from backend.app.main import app; print(app.title)"
python -m unittest discover -s backend/tests -v
```
