# 便携版：U 盘拷贝 → 双击即用

目标：把整个控制台打成 **一个文件夹**，拷到 U 盘后，对方电脑 **不必安装 Python / Node**，双击即可运行。

## 对方怎么用（最终用户）

1. 把整个 `ODMR_Console` 文件夹拷到对方电脑（建议拷到硬盘，例如桌面）。  
2. 双击 **`双击启动.bat`**（或 `START.bat`）。  
3. 浏览器会打开：http://127.0.0.1:8000/  
4. 结束：关掉黑色命令行窗口，或双击 **`停止.bat`**。

**不要**只拷 bat 文件；必须整夹包含 `runtime\` 与 `app\`。

| 要求 | 说明 |
| --- | --- |
| 系统 | Windows 10/11 **64 位** |
| 安装软件 | **不需要** Python / Node |
| 杀毒 | 首次可能拦截 `python.exe`，请允许 |
| 真机仪器 | 仍需厂商驱动 / VISA（与便携无关） |

---

## 你怎么打包（在你这台有网的开发机）

### 前置

- 已安装 Python、Node（与日常开发相同）  
- 能访问 python.org / PyPI / npm（打包时要下载嵌入式 Python 与依赖）

### 一键打包

在项目根目录：

```bat
scripts\build-portable.bat
```

或：

```bat
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\build-portable.ps1
```

成功后输出：

```text
dist-portable\ODMR_Console\
  双击启动.bat
  停止.bat
  START.bat
  STOP.bat
  使用说明.txt
  runtime\python\     ← 嵌入式 Python + 已装依赖
  app\                ← 后端源码 + frontend/dist
```

把 **`ODMR_Console` 整夹** 拷进 U 盘即可。

### 体积参考

通常约 **200MB～600MB+**（含 numpy、前端构建产物、嵌入式 Python）。  
若 `zhinst-toolkit` 安装失败，脚本会尝试去掉该包装其余依赖，并在日志中提示。

### 缓存

下载的 embed / get-pip 会缓存在项目下：

```text
.portable-cache\
```

第二次打包会更快。该目录已在 `.gitignore` 中忽略。

---

## 原理（为何不用再装 Node）

| 传统开发 | 便携版 |
| --- | --- |
| 后端 `python main.py` :8000 | 嵌入式 `python.exe` 跑 `main_portable.py` |
| 前端 `npm run dev` :5173 | **打包时** `npm run build`，运行时不再需要 Node |
| Vite 代理 `/api` | 后端 **同一端口** 同时提供 API + 静态页面 |

浏览器只访问 **http://127.0.0.1:8000/**，API 与 WebSocket 走同源 `/api`。

---

## 开发时如何验证「带静态页」模式

先构建前端，再只起后端：

```bat
cd frontend
npm.cmd run build
cd ..
python main.py
```

浏览器打开 http://127.0.0.1:8000/ （无需 5173）。

日常改前端界面仍建议用 `npm run dev` + `start.bat`。

---

## 与离线配置文档的关系

| 文档 | 场景 |
| --- | --- |
| [PORTABLE.md](./PORTABLE.md)（本文） | **免安装**，给最终用户 U 盘即用 |
| [OFFLINE_SETUP.md](./OFFLINE_SETUP.md) | 对方电脑要自己装 Python/Node，用离线 wheel |
| [ENV_SETUP.md](./ENV_SETUP.md) | 有网从零开发环境 |

---

## 常见问题

### 双击后窗口一闪就关

用 `cmd` 进入文件夹运行 `双击启动.bat` 看报错。常见原因：只拷了部分文件、被杀毒删除了 `runtime\python`。

### 端口 8000 被占用

先运行 `停止.bat`，或关掉占用 8000 的程序。

### 对方无法连仪器

便携只解决 **本软件运行时**。Zurich LabOne、Keysight VISA 等仍须在对方机器安装。

### 是否支持 Mac / Linux

当前脚本与 embed 仅针对 **Windows x64**。

---

## 维护者检查清单

```text
[ ] scripts\build-portable.bat 成功
[ ] dist-portable\ODMR_Console\双击启动.bat 能开浏览器
[ ] 页面 /device /current /docs 正常
[ ] 整夹拷到另一路径再启动仍正常（测“可移动”）
```
