# StickWords Device Setup Portal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a M5Stick-hosted setup access point and web form so Wi-Fi credentials and the StickWords server URL can be configured without editing `secrets.h` and reflashing firmware.

**Architecture:** Keep the current single-file firmware structure for this milestone, because the firmware is already centralized in `firmware/src/main.cpp`. Add a small runtime config struct stored in ESP32 `Preferences`, use `WebServer` for setup mode, and route sync URLs through the saved runtime server URL. Keep `secrets.h` as an optional development fallback.

**Tech Stack:** PlatformIO, Arduino framework, ESP32 `WiFi`, ESP32 `WebServer`, ESP32 `Preferences`, M5StickCPlus, Python `unittest`.

---

## File Map

- Modify `firmware/src/main.cpp`: add runtime config storage, setup AP/web server, Button B boot check, and runtime URL use.
- Modify `tests/test_firmware_project.py`: add firmware source tests for setup portal behavior.
- Modify `docs/handoff.md`: replace `secrets.h`-first daily instructions with setup portal instructions after implementation.
- Modify `docs/dev_log.md`: record implementation, tests, and manual validation steps after implementation.

## Task 1: Firmware Source Test For Runtime Config And Setup Portal

**Files:**
- Modify: `tests/test_firmware_project.py`
- Test: `tests/test_firmware_project.py`

- [ ] **Step 1: Add failing firmware source test**

Add this test inside `FirmwareProjectTests`:

```python
    def test_stage4_firmware_has_setup_portal_runtime_config(self):
        source = firmware_source()
        setup_body = firmware_function_body(source, "setup")
        connect_body = firmware_function_body(source, "connectWifi")
        fetch_body = firmware_function_body(source, "fetchDeviceTasks")
        upload_body = firmware_function_body(source, "uploadPendingReviews")

        self.assertIn("#include <WebServer.h>", source)
        self.assertIn("struct RuntimeConfig", source)
        self.assertIn("RuntimeConfig runtimeConfig", source)
        self.assertIn("loadRuntimeConfig()", source)
        self.assertIn("saveRuntimeConfig(", source)
        self.assertIn("validateRuntimeConfig(", source)
        self.assertIn("normalizeServerUrl(", source)
        self.assertIn("startSetupPortal()", source)
        self.assertIn("handleSetupRoot()", source)
        self.assertIn("handleSetupSave()", source)
        self.assertIn("WebServer setupServer(80)", source)
        self.assertIn('WiFi.softAP("StickWords-Setup")', source)
        self.assertIn("ESP.restart()", source)
        self.assertIn('storage.getString("cfg_ssid"', source)
        self.assertIn('storage.putString("cfg_ssid"', source)
        self.assertIn('storage.getString("cfg_server"', source)
        self.assertIn('storage.putString("cfg_server"', source)

        self.assertIn("M5.BtnB.isPressed()", setup_body)
        self.assertIn("loadRuntimeConfig()", setup_body)
        self.assertIn("startSetupPortal()", setup_body)
        self.assertIn("runtimeConfig.ssid", connect_body)
        self.assertIn("runtimeConfig.password", connect_body)
        self.assertNotIn("STICKWORDS_WIFI_SSID", connect_body)
        self.assertNotIn("STICKWORDS_WIFI_PASSWORD", connect_body)
        self.assertIn("runtimeServerUrl()", fetch_body)
        self.assertIn("runtimeServerUrl()", upload_body)
        self.assertNotIn("STICKWORDS_SERVER_URL", fetch_body)
        self.assertNotIn("STICKWORDS_SERVER_URL", upload_body)
```

- [ ] **Step 2: Run the focused test and verify failure**

Run:

```powershell
$env:PYTHONPATH='src'; python -m unittest tests.test_firmware_project.FirmwareProjectTests.test_stage4_firmware_has_setup_portal_runtime_config -v
```

Expected: FAIL because `WebServer`, `RuntimeConfig`, setup portal handlers, and runtime URL functions do not exist yet.

- [ ] **Step 3: Commit only if test is added and red**

Do not commit yet if implementation will immediately follow in the same task. Keep the red test visible in the working tree.

## Task 2: Runtime Config Storage And URL Plumbing

**Files:**
- Modify: `firmware/src/main.cpp`
- Test: `tests/test_firmware_project.py`

- [ ] **Step 1: Add includes, constants, struct, and globals**

In `firmware/src/main.cpp`, add:

```cpp
#include <WebServer.h>
```

Add near existing constants:

```cpp
constexpr size_t kMaxSsidLength = 64;
constexpr size_t kMaxPasswordLength = 64;
constexpr size_t kMaxServerUrlLength = 96;
```

Add near `PendingReview`:

```cpp
struct RuntimeConfig {
  char ssid[kMaxSsidLength];
  char password[kMaxPasswordLength];
  char serverUrl[kMaxServerUrlLength];
  bool valid;
};
```

Add near existing globals:

```cpp
RuntimeConfig runtimeConfig = {};
WebServer setupServer(80);
bool setupPortalActive = false;
```

- [ ] **Step 2: Add config helpers**

Add these functions after `copyBounded` so they can use it:

```cpp
String normalizeServerUrl(const String& value) {
  String normalized = value;
  normalized.trim();
  while (normalized.endsWith("/") && normalized.length() > String("http://").length()) {
    normalized.remove(normalized.length() - 1);
  }
  return normalized;
}

bool validateRuntimeConfig(const RuntimeConfig& config) {
  if (config.ssid[0] == '\0') {
    return false;
  }
  const String serverUrl = String(config.serverUrl);
  return serverUrl.startsWith("http://") && serverUrl.length() > String("http://").length();
}

bool loadRuntimeConfig() {
  storage.begin("stickwords", true);
  const String ssid = storage.getString("cfg_ssid", "");
  const String password = storage.getString("cfg_pass", "");
  const String server = storage.getString("cfg_server", "");
  storage.end();

  copyBounded(runtimeConfig.ssid, sizeof(runtimeConfig.ssid), ssid);
  copyBounded(runtimeConfig.password, sizeof(runtimeConfig.password), password);
  copyBounded(runtimeConfig.serverUrl, sizeof(runtimeConfig.serverUrl), normalizeServerUrl(server));
  runtimeConfig.valid = validateRuntimeConfig(runtimeConfig);
  Serial.printf("Runtime config valid=%u ssid=%s server=%s\n",
                runtimeConfig.valid ? 1 : 0, runtimeConfig.ssid, runtimeConfig.serverUrl);
  return runtimeConfig.valid;
}

void saveRuntimeConfig(const RuntimeConfig& config) {
  storage.begin("stickwords", false);
  storage.putString("cfg_ssid", config.ssid);
  storage.putString("cfg_pass", config.password);
  storage.putString("cfg_server", config.serverUrl);
  storage.end();
}

String runtimeServerUrl() {
  if (runtimeConfig.valid) {
    return String(runtimeConfig.serverUrl);
  }
  return String(STICKWORDS_SERVER_URL);
}
```

- [ ] **Step 3: Update Wi-Fi and HTTP code to use runtime config**

In `connectWifi()`, replace:

```cpp
WiFi.begin(STICKWORDS_WIFI_SSID, STICKWORDS_WIFI_PASSWORD);
```

with:

```cpp
WiFi.begin(runtimeConfig.ssid, runtimeConfig.password);
```

In `fetchDeviceTasks()`, replace:

```cpp
const String url = String(STICKWORDS_SERVER_URL) + "/api/device/tasks?limit=20";
```

with:

```cpp
const String url = runtimeServerUrl() + "/api/device/tasks?limit=20";
```

In `uploadPendingReviews()`, replace:

```cpp
const String url = String(STICKWORDS_SERVER_URL) + "/api/device/reviews";
```

with:

```cpp
const String url = runtimeServerUrl() + "/api/device/reviews";
```

- [ ] **Step 4: Run focused test**

Run:

```powershell
$env:PYTHONPATH='src'; python -m unittest tests.test_firmware_project.FirmwareProjectTests.test_stage4_firmware_has_setup_portal_runtime_config -v
```

Expected: still FAIL because setup portal handlers and boot flow are not implemented yet.

## Task 3: Setup Portal Web Server

**Files:**
- Modify: `firmware/src/main.cpp`
- Test: `tests/test_firmware_project.py`

- [ ] **Step 1: Add HTML response helpers**

Add these functions after runtime config helpers:

```cpp
String htmlEscape(const String& value) {
  String escaped = "";
  for (size_t i = 0; i < value.length(); ++i) {
    const char current = value[i];
    if (current == '&') {
      escaped += "&amp;";
    } else if (current == '<') {
      escaped += "&lt;";
    } else if (current == '>') {
      escaped += "&gt;";
    } else if (current == '"') {
      escaped += "&quot;";
    } else {
      escaped += current;
    }
  }
  return escaped;
}

String setupPageHtml(const String& message = "") {
  String html = "<!doctype html><html><head><meta charset=\"utf-8\">";
  html += "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">";
  html += "<title>StickWords Setup</title>";
  html += "<style>body{font-family:Segoe UI,Arial,sans-serif;margin:24px;max-width:560px}";
  html += "label{display:block;margin-top:14px;font-weight:600}input{width:100%;font:inherit;padding:8px;margin-top:4px}";
  html += "button{margin-top:18px;padding:10px 14px;font:inherit;font-weight:700}</style></head><body>";
  html += "<h1>StickWords Setup</h1>";
  if (message.length() > 0) {
    html += "<p>";
    html += htmlEscape(message);
    html += "</p>";
  }
  html += "<form method=\"post\" action=\"/save\">";
  html += "<label>Wi-Fi SSID<input name=\"ssid\" value=\"";
  html += htmlEscape(runtimeConfig.ssid);
  html += "\"></label>";
  html += "<label>Wi-Fi Password<input name=\"password\" type=\"password\" value=\"";
  html += htmlEscape(runtimeConfig.password);
  html += "\"></label>";
  html += "<label>StickWords Server URL<input name=\"server\" value=\"";
  html += htmlEscape(runtimeConfig.serverUrl);
  html += "\" placeholder=\"http://192.168.x.x:8000\"></label>";
  html += "<button type=\"submit\">Save and restart</button></form></body></html>";
  return html;
}
```

- [ ] **Step 2: Add setup request handlers**

Add:

```cpp
void handleSetupRoot() {
  setupServer.send(200, "text/html; charset=utf-8", setupPageHtml());
}

void handleSetupSave() {
  RuntimeConfig submitted = {};
  copyBounded(submitted.ssid, sizeof(submitted.ssid), setupServer.arg("ssid"));
  copyBounded(submitted.password, sizeof(submitted.password), setupServer.arg("password"));
  copyBounded(submitted.serverUrl, sizeof(submitted.serverUrl),
              normalizeServerUrl(setupServer.arg("server")));
  submitted.valid = validateRuntimeConfig(submitted);

  if (!submitted.valid) {
    setupServer.send(400, "text/html; charset=utf-8",
                     setupPageHtml("SSID is required and server URL must start with http://"));
    return;
  }

  runtimeConfig = submitted;
  saveRuntimeConfig(runtimeConfig);
  setupServer.send(200, "text/html; charset=utf-8",
                   "<!doctype html><html><head><meta charset=\"utf-8\"><title>Saved</title></head>"
                   "<body><h1>Saved, restarting</h1></body></html>");
  drawStatusMessage("Saved", "restarting");
  delay(800);
  ESP.restart();
}
```

- [ ] **Step 3: Add setup portal loop**

Add:

```cpp
void startSetupPortal() {
  setupPortalActive = true;
  WiFi.mode(WIFI_AP);
  if (!WiFi.softAP("StickWords-Setup")) {
    Serial.println("Setup portal AP failed");
    drawStatusMessage("Setup failed", "check serial");
    setStatusPage("Setup failed", "check serial");
    return;
  }

  setupServer.on("/", HTTP_GET, handleSetupRoot);
  setupServer.on("/save", HTTP_POST, handleSetupSave);
  setupServer.begin();
  Serial.print("Setup portal ip=");
  Serial.println(WiFi.softAPIP());
  drawStatusMessage("Setup mode", "Open 192.168.4.1");
  setStatusPage("Setup mode", "Open 192.168.4.1");
}

void handleSetupPortalLoop() {
  if (setupPortalActive) {
    setupServer.handleClient();
  }
}
```

- [ ] **Step 4: Run focused test**

Run:

```powershell
$env:PYTHONPATH='src'; python -m unittest tests.test_firmware_project.FirmwareProjectTests.test_stage4_firmware_has_setup_portal_runtime_config -v
```

Expected: likely still FAIL until setup boot flow is connected.

## Task 4: Setup Boot Flow And Main Loop Integration

**Files:**
- Modify: `firmware/src/main.cpp`
- Test: `tests/test_firmware_project.py`

- [ ] **Step 1: Connect setup mode in `setup()`**

In `setup()`, after serial/orientation logging and before `loadPendingReviews()`, add:

```cpp
  M5.update();
  const bool forceSetup = M5.BtnB.isPressed();
  if (!loadRuntimeConfig() || forceSetup) {
    Serial.printf("Setup mode reason=%s\n", forceSetup ? "button" : "missing-config");
    startSetupPortal();
    logPage();
    render();
    return;
  }
```

Then keep existing:

```cpp
  loadPendingReviews();
  if (connectWifi()) {
    uploadPendingReviews();
    fetchDeviceTasks();
  } else if (loadCachedTasks()) {
    Serial.println("Using cached tasks after WiFi failure");
  }
```

- [ ] **Step 2: Connect setup portal loop**

At the start of `loop()`, after `M5.update();`, add:

```cpp
  if (setupPortalActive) {
    handleSetupPortalLoop();
    render();
    delay(20);
    return;
  }
```

- [ ] **Step 3: Run focused firmware test**

Run:

```powershell
$env:PYTHONPATH='src'; python -m unittest tests.test_firmware_project.FirmwareProjectTests.test_stage4_firmware_has_setup_portal_runtime_config -v
```

Expected: PASS.

- [ ] **Step 4: Run all firmware source tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m unittest tests.test_firmware_project -v
```

Expected: all firmware source tests pass. If old tests assert `STICKWORDS_SERVER_URL` is directly used, update those tests to allow runtime configuration while still keeping `secrets.h` as fallback.

- [ ] **Step 5: Build firmware**

Run:

```powershell
cd C:\Users\ASUS\Documents\M5Stick\firmware
C:\Users\ASUS\.platformio\penv\Scripts\pio.exe run
```

Expected: PlatformIO build succeeds.

- [ ] **Step 6: Commit firmware setup portal**

Run:

```powershell
git add firmware/src/main.cpp tests/test_firmware_project.py
git commit -m "Add M5Stick setup portal"
```

## Task 5: Documentation And Verification

**Files:**
- Modify: `docs/handoff.md`
- Modify: `docs/dev_log.md`

- [ ] **Step 1: Update handoff instructions**

In `docs/handoff.md`, replace the `How To Configure Firmware Sync` section with:

```markdown
## How To Configure M5Stick Wi-Fi And Server URL

The normal path is the M5Stick setup portal:

1. Upload firmware once.
2. Hold Button B while rebooting the M5Stick.
3. Connect a PC or phone to the `StickWords-Setup` Wi-Fi network.
4. Open `http://192.168.4.1`.
5. Enter the 2.4 GHz Wi-Fi SSID, password, and StickWords server URL shown on the PC admin page.
6. Save and wait for the M5Stick to restart.

`firmware\include\secrets.h` remains a developer fallback and must not contain committed real credentials.
```

- [ ] **Step 2: Append dev log entry**

Append a dated entry to `docs/dev_log.md` containing:

```markdown
## 2026-05-25 Stage 4 polish: M5Stick setup portal

完成内容：

- 增加 Button B 开机进入配置模式。
- 增加 `StickWords-Setup` 临时热点和 `http://192.168.4.1` 配置页。
- 将 Wi-Fi SSID、密码和 PC 后端 URL 保存到 ESP32 flash。
- 正常启动优先使用运行时配置，不再需要日常编辑 `secrets.h`。

测试结果：

- 固件源码测试通过。
- 仓库级 Python 全量测试通过。
- PlatformIO 固件编译通过。

下一步：

- 上传到真机，验证配置页保存后能重启并同步。
```

- [ ] **Step 3: Run final verification**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONPATH='src'; python -m unittest discover -s tests -v
cd C:\Users\ASUS\Documents\M5Stick\firmware
C:\Users\ASUS\.platformio\penv\Scripts\pio.exe run
cd C:\Users\ASUS\Documents\M5Stick
git diff --check
```

Expected:

- `Ran 84 tests ... OK` or the current updated count.
- PlatformIO build succeeds.
- `git diff --check` reports no whitespace errors, aside from normal Windows line-ending warnings if present.

- [ ] **Step 4: Commit docs**

Run:

```powershell
git add docs/handoff.md docs/dev_log.md
git commit -m "Document M5Stick setup portal"
```

## Manual Validation Checklist

After implementation and upload:

- [ ] Hold Button B while rebooting.
- [ ] M5Stick screen shows `Setup mode` and `Open 192.168.4.1`.
- [ ] PC or phone can connect to `StickWords-Setup`.
- [ ] Browser can open `http://192.168.4.1`.
- [ ] Invalid blank SSID submission does not overwrite config.
- [ ] Valid Wi-Fi and server URL save successfully.
- [ ] M5Stick restarts.
- [ ] Serial log shows runtime config is valid.
- [ ] Serial log shows Wi-Fi connected.
- [ ] Serial log shows `GET http://.../api/device/tasks?limit=20`.

## Self-Review

Spec coverage:

- Button B setup entry: Task 4.
- Automatic setup mode when no runtime config exists: Task 4.
- Temporary AP and browser form: Task 3.
- Runtime config persistence: Task 2.
- Runtime Wi-Fi and server URL use: Task 2.
- Invalid form handling: Task 3.
- Existing cache fallback preservation: Task 4 keeps existing Wi-Fi failure branch.
- Documentation: Task 5.

Placeholder scan:

- No `TBD`, `TODO`, or undefined placeholder steps remain.

Type consistency:

- Runtime config functions consistently use `RuntimeConfig`, `runtimeConfig`, `loadRuntimeConfig()`, `saveRuntimeConfig()`, `validateRuntimeConfig()`, `normalizeServerUrl()`, and `runtimeServerUrl()`.
