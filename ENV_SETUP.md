# 全新电脑环境配置指南（Windows）

本文面向 **空白 Windows 电脑**（未安装开发工具）。按顺序执行即可从零拉起本仓库的后端与前端。

- **仓库**：https://github.com/zhuziyang-ui/odmr  
- **推荐系统**：Windows 10 / 11（64 位）  
- **本机已验证参考版本**：Python 3.13、Node.js 24、npm 11、Git  

> 硬件仪器（Zurich Instruments 锁相、Keysight 微波源等）**不是**跑通软件的必要条件。无仪器时可用模拟/离线模式开发与自检；接真机时再安装厂商驱动与 VISA。

> **电脑完全不能上网？** 请改看 **[OFFLINE_SETUP.md](./OFFLINE_SETUP.md)**（U 盘打包 / 离线 pip·npm 安装）。  
> **想免安装、U 盘双击即用？** 请看 **[PORTABLE.md](./PORTABLE.md)**（打成 `ODMR_Console` 便携夹）。

---

## 0. 需要安装什么（总览）

| 软件 | 用途 | 推荐版本 |
| --- | --- | --- |
| Git | 克隆与更新代码 | 最新稳定版 |
| Python | 运行 FastAPI 后端 | **3.11～3.13**（64 位） |
| Node.js | 运行 Vite 前端 | **LTS**（18+，推荐 20/22/24） |
| 代码编辑器（可选） | 改代码 | VS Code / Cursor 等 |

完成后访问：

| 服务 | 地址 |
| --- | --- |
| 前端 | http://127.0.0.1:5173 |
| 后端 | http://127.0.0.1:8000 |
| API 文档 | http://127.0.0.1:8000/docs |

---

## 1. 安装 Git

1. 打开：https://git-scm.com/download/win  
2. 下载并安装，安装时保持默认即可。  
3. **新开**一个 PowerShell 或「命令提示符」，验证：

```bat
git --version
```

应显示类似 `git version 2.x.x`。

---

## 2. 安装 Python

1. 打开：https://www.python.org/downloads/windows/  
2. 下载 **Windows installer (64-bit)**，建议 3.11 / 3.12 / 3.13。  
3. 安装时务必勾选：
   - **Add python.exe to PATH**
   - 可选：Install pip  
4. **新开**终端，验证：

```bat
python --version
python -m pip --version
```

应分别显示 Python 版本和 pip 版本。

### 若 `python` 打不开

- 可能被 Windows 应用商店占位：关闭「应用执行别名」里的 `python.exe` / `python3.exe`，或重装并勾选 PATH。  
- 也可使用完整路径，例如：

```bat
"%LocalAppData%\Programs\Python\Python313\python.exe" --version
```

---

## 3. 安装 Node.js（含 npm）

1. 打开：https://nodejs.org/  
2. 下载 **LTS** 安装包并安装（勾选加入 PATH）。  
3. **新开**终端，验证：

```bat
node --version
npm.cmd --version
```

> **PowerShell 提示**：若直接运行 `npm` 报“禁止运行脚本”，请用 **`npm.cmd`**（本仓库启动脚本已使用 `npm.cmd`），或把执行策略改为：
>
> ```powershell
> Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
> ```

---

## 4. 克隆本仓库

任选一个工作目录（示例用桌面）：

```bat
cd /d %USERPROFILE%\Desktop
git clone https://github.com/zhuziyang-ui/odmr.git
cd odmr
```

若你已有本地拷贝、只需更新：

```bat
cd /d 你的项目目录
git pull origin master
```

---

## 5. 安装 Python 依赖（后端）

在**项目根目录**执行：

```bat
cd /d 你的项目目录
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

`requirements.txt` 主要包含：

- `fastapi` / `uvicorn`：Web API  
- `numpy` / `pydantic` / `openpyxl`：数值与数据  
- `pyvisa` / `pyvisa-py`：通用仪器通信  
- `zhinst-toolkit`：苏黎世仪器（无真机也可先装上）

### 自检后端能否导入

```bat
python -c "from backend.app.main import app; print(app.title)"
```

能打印应用标题即表示后端依赖基本正确。

### （可选）跑单元测试

```bat
python -m unittest discover -s backend/tests -v
```

---

## 6. 安装前端依赖

```bat
cd /d 你的项目目录\frontend
npm.cmd install
```

若启动时报 **esbuild** 相关错误：

```bat
cd /d 你的项目目录\frontend
npm.cmd approve-scripts esbuild
npm.cmd rebuild esbuild
```

---

## 7. 启动与停止

### 方式 A：一键脚本（推荐）

在资源管理器中进入项目根目录，双击：

| 文件 | 作用 |
| --- | --- |
| `start.bat` | 结束旧进程后，分别打开后端 / 前端窗口 |
| `stop.bat` | 结束占用 **8000**、**5173** 端口的进程 |

命令行等价：

```bat
cd /d 你的项目目录
start.bat
stop.bat
```

### 方式 B：分开启动

```bat
scripts\start-backend.bat
scripts\start-frontend.bat
scripts\stop-services.bat
```

### 方式 C：手动命令（便于看报错）

**终端 1 — 后端：**

```bat
cd /d 你的项目目录
python main.py
```

**终端 2 — 前端：**

```bat
cd /d 你的项目目录\frontend
npm.cmd run dev -- --host 127.0.0.1 --port 5173
```

浏览器打开：http://127.0.0.1:5173  

功能页包括：设备、锁相、微波、ODMR、电流测量（PID）、状态估计（EKF/UKF）等（以当前前端路由为准）。

---

## 8. 日常更新代码后的标准流程

每次从 GitHub 拉新代码后，建议执行：

```bat
cd /d 你的项目目录
git pull
python -m pip install -r requirements.txt
cd frontend
npm.cmd install
```

然后重新 `start.bat`。

---

## 9. 接真机时的额外准备（可选）

仅在连接 Zurich / Keysight 等设备时需要，**软件空跑可跳过**。

1. **仪器厂商驱动 / LabOne（Zurich）**  
   - 按 Zurich Instruments 官网安装 LabOne 与对应固件。  
   - 确认电脑与仪器网络/USB 连通。

2. **VISA 运行时（Keysight 等）**  
   - 可安装 Keysight IO Libraries 或 NI-VISA。  
   - `pyvisa` / `pyvisa-py` 用于发现与通信；具体资源字符串以设备页扫描结果为准。

3. **防火墙**  
   - 允许本机 `python` 与 `node` 访问本地回环与仪器网段。

4. **权限**  
   - USB 仪器：安装驱动后插拔一次，在设备管理器确认无感叹号。

---

## 10. 常见问题

### 端口被占用（8000 / 5173）

```bat
stop.bat
```

或手动在管理员 PowerShell 中查杀占用端口的进程，再重新 `start.bat`。

### `pip` 很慢或超时

使用国内镜像示例：

```bat
python -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### `npm install` 很慢

```bat
npm.cmd config set registry https://registry.npmmirror.com
npm.cmd install
```

### 前端能开、接口 404 / 连不上后端

1. 确认后端窗口无报错，且 http://127.0.0.1:8000/docs 能打开。  
2. 前端通过 Vite 代理把 `/api` 转到 `8000`（见 `frontend/vite.config.js`），请用 **5173** 访问页面，不要只开静态文件。  
3. 两个窗口都不要关。

### 克隆私有仓库需要登录

若仓库改为私有，需配置 GitHub 凭据（Personal Access Token 或 GitHub CLI 登录）后再 `git clone` / `git push`。

---

## 11. 推荐目录与检查清单（复制用）

把下面当作模板勾选：

```text
[ ] 1. 安装 Git，git --version 正常
[ ] 2. 安装 Python 3.11+，python / pip 正常
[ ] 3. 安装 Node.js LTS，node / npm.cmd 正常
[ ] 4. git clone https://github.com/zhuziyang-ui/odmr.git
[ ] 5. python -m pip install -r requirements.txt
[ ] 6. cd frontend && npm.cmd install
[ ] 7. 根目录双击 start.bat
[ ] 8. 浏览器打开 http://127.0.0.1:5173
[ ] 9. 打开 http://127.0.0.1:8000/docs 确认 API
[ ] 10.（可选）python -m unittest discover -s backend/tests -v
```

---

## 12. 相关文档

| 文档 | 内容 |
| --- | --- |
| [OFFLINE_SETUP.md](./OFFLINE_SETUP.md) | **无外网**时用 U 盘打包/安装 |
| [STARTUP.md](./STARTUP.md) | 已有环境时的启停与更新 |
| [README.md](./README.md) | 功能说明、PID / EKF·UKF 调参 |
| `scripts/` | 分服务启动与离线打包脚本 |

配置完成后，日常只需：**`git pull` → 更新依赖（有变化时）→ `start.bat`**。
