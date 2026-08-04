# 离线环境配置指南（Windows，无外网）

适用于 **实验电脑不能上网**、只能用 U 盘 / 内网拷贝的场景。  
在线安装仍请看 [ENV_SETUP.md](./ENV_SETUP.md)。

核心思路：

1. 在一台 **能上网的电脑** 上打好「离线包」  
2. 拷到离线机  
3. 离线安装运行时 + Python/前端依赖，再启动  

---

## 方案怎么选

| 方案 | 适用 | 优点 | 注意 |
| --- | --- | --- | --- |
| **A. 整机拷贝（最快）** | 两台机都是 Win10/11 64 位，配置接近 | 几乎不装依赖 | 路径/系统差太多可能要重装 venv |
| **B. 离线安装包（推荐）** | 正式给新电脑部署 | 可重复、体积可控 | 需在联网机先打包 |
| **C. 仅代码 U 盘同步** | 离线机已配好环境 | 只更新源码 | 不解决首次环境 |

---

## 方案 A：整机拷贝（最快上线）

在 **已能运行本项目** 的电脑上：

1. 确认后端/前端都能 `start.bat` 正常打开。  
2. 将整个项目目录拷到 U 盘（可排除大文件以省空间）：

| 建议带上 | 可不带 |
| --- | --- |
| 全部源码、`requirements.txt`、`frontend/package.json` | `data/current_tracking/` 实验数据 |
| `frontend/node_modules/`（前端依赖） | `__pycache__`、`.git`（可选） |
| 若用了虚拟环境：项目内 `.venv/` | `frontend/dist/` |

3. 另存安装包（若目标机还没有 Python/Node）：

- Python：https://www.python.org/downloads/windows/（Windows 64-bit installer）  
- Node.js LTS：https://nodejs.org/  

4. 离线机：先装 Python、Node（勾选加入 PATH），再把项目目录拷到例如：

```text
C:\Users\你的用户名\Desktop\odmr
```

5. 若拷了 **虚拟环境 `.venv`**：

```bat
cd /d C:\Users\你的用户名\Desktop\odmr
.venv\Scripts\python.exe main.py
```

前端若已有 `node_modules`：

```bat
cd frontend
npm.cmd run dev -- --host 127.0.0.1 --port 5173
```

或直接双击根目录 `start.bat`（脚本默认用系统 `python` / `npm.cmd`；若只用 `.venv`，需把启动脚本改成 `.venv\Scripts\python.exe`，或先 `activate`）。

> **坑**：虚拟环境路径写死了原机路径时，换电脑可能失效。此时用 **方案 B** 更稳。

---

## 方案 B：离线安装包（推荐、可重复）

### B1. 联网机：一键打包

在项目根目录执行（需已装好 Python、Node，且能访问 PyPI / npm）：

```bat
cd /d 你的项目目录
scripts\pack-offline-bundle.bat
```

成功后会生成目录：

```text
offline-bundle/
  README-OFFLINE.txt          ← 离线机速查
  installers/                 ← 请手动放入 Python/Node 安装包（脚本会提示）
  python-wheels/              ← pip 离线 wheel
  requirements.txt            ← 依赖清单副本
  npm-cache/                  ← npm 离线缓存（若打包成功）
  frontend-node_modules/      ← 可选：整包 node_modules 备份
  source/                     ← 可选：源码快照说明
```

脚本会做的事：

1. `pip download -r requirements.txt -d offline-bundle\python-wheels`  
2. 尝试用 `npm pack` / cache 或复制 `frontend\node_modules`  
3. 写出离线安装步骤  

你还需要 **手动下载** 两个安装程序到 `offline-bundle\installers\`：

| 文件 | 说明 |
| --- | --- |
| `python-3.xx.x-amd64.exe` | 与打包机 **同一大版本** 最稳（如都是 3.12 / 3.13） |
| `node-vxx.x.x-x64.msi` | Node.js LTS 安装包 |

可选：把整个 **git 仓库**（或 zip）一起放进 U 盘。

### B2. U 盘目录示例

```text
U:\odmr-offline\
  odmr\                          ← 源码（git clone 或拷贝）
  offline-bundle\
    installers\
      python-3.13.x-amd64.exe
      node-v24.x.x-x64.msi
    python-wheels\
    npm-cache\  或  frontend-node_modules\
    requirements.txt
```

### B3. 离线机：安装

#### 1）安装运行时（只做一次）

双击安装：

1. `python-*.exe` → 勾选 **Add python.exe to PATH**  
2. `node-*.msi` → 默认即可  

**新开**命令行窗口，检查：

```bat
python --version
node --version
npm.cmd --version
```

#### 2）安装项目依赖

把源码放到固定目录后：

```bat
cd /d U:\odmr-offline\odmr
scripts\install-offline.bat U:\odmr-offline\offline-bundle
```

或手动：

**Python（完全离线）：**

```bat
cd /d 你的源码目录
python -m pip install --no-index --find-links=U:\odmr-offline\offline-bundle\python-wheels -r requirements.txt
```

**前端 — 方式 1（拷贝 node_modules，最省事）：**

```bat
xcopy /E /I /Y U:\odmr-offline\offline-bundle\frontend-node_modules frontend\node_modules
```

**前端 — 方式 2（npm 离线缓存）：**

```bat
cd frontend
npm.cmd ci --offline --cache U:\odmr-offline\offline-bundle\npm-cache
```

若 `ci` 失败，可试：

```bat
npm.cmd install --offline --cache U:\odmr-offline\offline-bundle\npm-cache
```

仍失败时，退回方式 1 直接拷 `node_modules`。

#### 3）启动

```bat
cd /d 你的源码目录
start.bat
```

- 前端：http://127.0.0.1:5173  
- 后端：http://127.0.0.1:8000/docs  

---

## 方案 C：离线机已配好，只更新代码

U 盘只带源码 zip / git bundle 即可。

### 用 git bundle（不需要 GitHub）

**联网机：**

```bat
cd /d 你的项目目录
git bundle create odmr-master.bundle master
```

**离线机（已有仓库）：**

```bat
cd /d 你的项目目录
git pull U:\odmr-master.bundle master
```

**离线机（全新目录）：**

```bat
git clone U:\odmr-master.bundle odmr
cd odmr
```

依赖若有变化，再从新的 `offline-bundle\python-wheels` 执行一次离线 `pip install`。

---

## 手动打包命令（不用脚本时）

### Python wheels

```bat
cd /d 你的项目目录
mkdir offline-bundle\python-wheels
python -m pip download -r requirements.txt -d offline-bundle\python-wheels
```

建议在 **与离线机相同的 Python 大版本** 上打包（例如都是 3.13）。

### 仅当前环境已装包（备选）

```bat
python -m pip freeze > offline-bundle\requirements-lock.txt
python -m pip download -r offline-bundle\requirements-lock.txt -d offline-bundle\python-wheels
```

### 前端 node_modules

在联网机装好依赖后直接复制：

```bat
xcopy /E /I /Y frontend\node_modules offline-bundle\frontend-node_modules
```

或填充 npm 缓存：

```bat
cd frontend
npm.cmd install
npm.cmd cache max
xcopy /E /I /Y "%LocalAppData%\npm-cache" ..\offline-bundle\npm-cache
```

（不同 npm 版本缓存路径可能不同，以本机 `npm.cmd config get cache` 为准。）

---

## 体积与版本注意

| 项目 | 说明 |
| --- | --- |
| `frontend/node_modules` | 通常几百 MB～1GB+，U 盘要够大 |
| `python-wheels` | 通常几十～两百 MB（含 numpy 等） |
| Python 版本 | **打包机与离线机尽量同主版本**（3.12↔3.12），跨版本 wheel 可能装不上 |
| 系统架构 | 均为 **Windows 64 位** |
| `zhinst-toolkit` | 无仪器也可装；若 wheel 下载失败，可暂时从 `requirements.txt` 去掉再装其余包，有仪器再补 |

---

## 离线自检清单

```text
[ ] 离线机 python / node / npm.cmd 可用
[ ] pip install --no-index --find-links=...\python-wheels -r requirements.txt 成功
[ ] frontend\node_modules 存在，或 npm --offline 安装成功
[ ] python -c "from backend.app.main import app; print(app.title)" 有输出
[ ] start.bat 后 5173 / 8000 可访问
```

可选测试（不需外网）：

```bat
python -m unittest discover -s backend/tests -v
```

---

## 常见问题

### `pip` 仍尝试联网

务必带上：

```bat
python -m pip install --no-index --find-links=路径\python-wheels -r requirements.txt
```

不要省略 `--no-index`。

### 某个 wheel 缺失 / 平台不符

回到 **同版本 Python 的联网 Win64 机** 重新 `pip download`，或对该包单独：

```bat
python -m pip download 包名==版本 -d offline-bundle\python-wheels
```

### npm 报 offline 找不到包

优先使用 **整目录拷贝 `node_modules`**，比 npm offline 缓存更稳。

### esbuild 相关错误（换机后）

```bat
cd frontend
npm.cmd rebuild esbuild
```

无网时需保证 `node_modules` 来自 **同一平台（Windows）** 的拷贝，不要从 Linux/Mac 拷二进制。

---

## 相关文档

| 文档 | 内容 |
| --- | --- |
| [ENV_SETUP.md](./ENV_SETUP.md) | 有网时的从零安装 |
| [STARTUP.md](./STARTUP.md) | 日常启停 |
| `scripts\pack-offline-bundle.bat` | 联网机打包 |
| `scripts\install-offline.bat` | 离线机安装依赖 |
