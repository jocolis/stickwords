# StickWords

**English | [中文](#stickwords-中文)**

StickWords is a lightweight vocabulary review system for the M5Stick C Plus. It pairs a small PC backend with a handheld M5Stick frontend, using CSV storage, spaced repetition, offline review caching, RTC-backed scheduling, and a LVGL clock page.

## Features

- PC web admin page for adding, importing, searching, suspending, and reviewing vocabulary records.
- CSV-first storage in `data/vocab.csv`.
- M5Stick C Plus firmware with:
  - Wi-Fi sync to the PC backend
  - setup portal for Wi-Fi and server URL configuration
  - Button A/Button B review flow
  - double-shake `good` rating
  - left/right landscape auto-rotation
  - BM8563 RTC calibration from the backend
  - cached offline review cards and pending review upload
  - LVGL clock page with live time, due count, battery arc, and idle power-off
- Optional PC Quick Add helper with DeepSeek-generated definitions via `DEEPSEEK_API_KEY`.

## Repository Layout

```text
app.py                         PC backend entrypoint
src/stickwords/                Backend service, scheduler, storage, and web UI
scripts/                       Windows launcher and Quick Add helper scripts
firmware/                      PlatformIO firmware for M5Stick C Plus
firmware/include/secrets.example.h
                               Safe firmware config template
docs/                          Roadmap, handoff, development log, and plans
tests/                         Python and firmware source tests
```

## PC Backend

Requirements:

- Windows, macOS, or Linux with Python 3.11+

Run:

```powershell
python app.py --host 0.0.0.0 --port 8000 --data-dir data
```

Then open:

```text
http://localhost:8000/admin
```

On Windows, you can also run:

```powershell
start_stickwords.bat
```

The admin page shows a suggested LAN server URL, usually like:

```text
http://192.168.x.x:8000
```

Use that LAN URL on the M5Stick setup page. Do not use `localhost` on the M5Stick, because `localhost` means the M5Stick itself.

## M5Stick Firmware

Requirements:

- M5Stick C Plus
- USB cable
- PlatformIO
- 2.4 GHz Wi-Fi
- PC and M5Stick on the same reachable LAN

Build:

```powershell
cd firmware
pio run
```

Upload, replacing `COM5` with your device port if needed:

```powershell
pio run --target upload --upload-port COM5
```

Serial monitor:

```powershell
pio device monitor --port COM5
```

### Runtime Setup

Hold Button B during boot, or boot without saved config, to enter setup mode.

1. Connect your phone or PC to the `StickWords-Setup` Wi-Fi network.
2. Open `http://192.168.4.1` if the captive portal does not open automatically.
3. Enter your 2.4 GHz Wi-Fi SSID, password, and the StickWords server URL shown on the PC admin page.
4. Save. The device restarts and uses the stored runtime config.

`firmware/include/secrets.h` is only a local developer fallback. It must not be committed.

## Data And Privacy

- `data/*.csv` is ignored by Git because vocabulary data may be personal.
- `firmware/include/secrets.h` is ignored by Git because it can contain real Wi-Fi credentials and LAN URLs.
- `firmware/include/secrets.example.h` is safe to publish because it contains placeholders only.
- LAN URLs such as `http://192.168.x.x:8000` are private-network examples. They are not usually reachable from the public internet, but exact local addresses are still unnecessary in public docs.
- Quick Add reads `DEEPSEEK_API_KEY` from your environment. Do not write real API keys into repository files.
- The setup portal has no password. Enable it intentionally and only on trusted local networks.
- The firmware currently uses plain HTTP on the local network.

## Quick Add

Optional helper for adding words from selected text:

```powershell
python scripts\quick_add.py
```

To enable DeepSeek definition generation:

```powershell
$env:DEEPSEEK_API_KEY='your-api-key'
```

## Tests

Run the Python and firmware source tests:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTHONPATH='src'
python -m unittest discover -s tests -v
```

Run firmware build verification:

```powershell
cd firmware
pio run
```

## Current Status

StickWords is an early personal project. The current system has a working PC backend, web admin page, M5Stick sync path, offline fallback, RTC-backed clock, review flow, and LVGL clock page. See `docs/handoff.md` for the latest implementation notes and validation procedures.

## License

MIT. See `LICENSE`.

---

# StickWords 中文

StickWords 是一个运行在 M5Stick C Plus 和 PC 后端上的轻量背单词系统。PC 负责 CSV 生词本、网页管理和复习调度，M5Stick 负责随身复习、离线缓存、RTC 时间显示和实体按键/体感交互。

## 功能

- PC 网页管理页：添加、导入、搜索、暂停和查看单词。
- 使用 `data/vocab.csv` 作为主要数据文件。
- M5Stick C Plus 固件：
  - 通过 Wi-Fi 和 PC 后端同步
  - 手机/电脑配置页，用于设置 Wi-Fi 和服务器地址
  - Button A / Button B 复习流程
  - 双摇两下提交 `good`
  - 左手/右手横屏自动旋转
  - 使用 BM8563 RTC，并从后端时间校准
  - 离线复习缓存和待上传复习记录
  - LVGL 时钟页：实时显示时间、due 数量、电池环和自动关机
- 可选 Quick Add 工具，可通过 DeepSeek 自动生成释义。

## 项目结构

```text
app.py                         PC 后端入口
src/stickwords/                后端服务、调度、存储和网页 UI
scripts/                       Windows 启动器和 Quick Add 脚本
firmware/                      M5Stick C Plus 的 PlatformIO 固件
firmware/include/secrets.example.h
                               安全的固件配置模板
docs/                          路线图、交接文档、开发日志和计划
tests/                         Python 测试和固件源码测试
```

## 启动 PC 后端

需要 Python 3.11+。

```powershell
python app.py --host 0.0.0.0 --port 8000 --data-dir data
```

然后打开：

```text
http://localhost:8000/admin
```

Windows 下也可以运行：

```powershell
start_stickwords.bat
```

网页管理页会显示建议给 M5Stick 使用的局域网地址，通常类似：

```text
http://192.168.x.x:8000
```

M5Stick 配置时要填这个局域网地址，不要填 `localhost`。在 M5Stick 上，`localhost` 指的是 M5Stick 自己，不是 PC。

## 刷 M5Stick 固件

需要：

- M5Stick C Plus
- USB 数据线
- PlatformIO
- 2.4 GHz Wi-Fi
- PC 和 M5Stick 在同一个可互相访问的局域网内

编译：

```powershell
cd firmware
pio run
```

上传，必要时把 `COM5` 换成你的设备端口：

```powershell
pio run --target upload --upload-port COM5
```

串口监听：

```powershell
pio device monitor --port COM5
```

## M5Stick 配置方式

开机时按住 Button B，或者设备还没有保存配置时，会进入 setup mode。

1. 手机或电脑连接 `StickWords-Setup` Wi-Fi。
2. 如果没有自动弹出配置页，手动打开 `http://192.168.4.1`。
3. 输入 2.4 GHz Wi-Fi 的 SSID、密码，以及 PC 网页管理页显示的 StickWords server URL。
4. 保存后设备会重启，并使用保存的运行时配置。

`firmware/include/secrets.h` 只是本地开发兜底文件，不应该提交到 Git。

## 数据与隐私

- `data/*.csv` 已被 Git 忽略，因为生词本可能包含个人数据。
- `firmware/include/secrets.h` 已被 Git 忽略，因为可能包含真实 Wi-Fi 密码和局域网地址。
- `firmware/include/secrets.example.h` 只包含占位符，可以发布。
- `http://192.168.x.x:8000` 这类地址是局域网地址，通常公网不能访问，但真实具体地址没有必要出现在公开文档中。
- Quick Add 从环境变量读取 `DEEPSEEK_API_KEY`，不要把真实 API key 写进仓库文件。
- M5Stick setup portal 没有密码，只应在可信局域网中主动启用。
- 当前固件使用局域网明文 HTTP。

## Quick Add

可选的快速加词工具：

```powershell
python scripts\quick_add.py
```

如需使用 DeepSeek 自动生成释义：

```powershell
$env:DEEPSEEK_API_KEY='your-api-key'
```

## 测试

运行 Python 和固件源码测试：

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTHONPATH='src'
python -m unittest discover -s tests -v
```

运行固件编译验证：

```powershell
cd firmware
pio run
```

## 当前状态

StickWords 目前是早期个人项目，但已经具备可演示的闭环：PC 后端、网页管理页、M5Stick 同步、离线缓存、RTC 时钟、复习流程和 LVGL 时钟页。最新实现细节和真机验证流程见 `docs/handoff.md`。

## 许可证

MIT，见 `LICENSE`。
