# StickWords Stage 3B Review UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Stage 3A hardware-check firmware with a minimum local review UI prototype using three built-in fake cards.

**Architecture:** Keep the firmware as a single Arduino-style `main.cpp` for this small prototype, but structure it with explicit data structs, enums, rendering helpers, button handlers, and review-result helpers. Repository Python tests act as firmware source smoke tests; real behavior is verified on the M5Stick C Plus with PlatformIO build/upload/monitor.

**Tech Stack:** PlatformIO, Espressif 32 platform, Arduino framework, `m5stack/M5StickCPlus`, C++, Python `unittest`, Windows PowerShell.

---

## Scope

This plan implements Stage 3B only:

- Three built-in fake cards.
- Four review pages: word, meaning summary, full example, rating.
- Done page after all three cards are rated.
- Button A short press page advance / rating cycle / restart.
- Button A long press rating submit.
- Button B previous page / previous-card re-rating.
- In-memory rating results and overwrite behavior.
- Serial logs for page transitions, rating changes, saves, overwrites, and completion.

This plan does not implement:

- Wi-Fi.
- HTTP sync.
- PC backend API calls.
- CSV loading.
- Local persistent cache.
- Power-loss recovery.
- IMU tilt scoring.
- Double-shake `good`.
- Left/right hand auto-rotation.
- Sound, vibration, or confirmation delay.
- USB configuration.

## File Responsibilities

- `firmware/src/main.cpp`: Stage 3B firmware UI state machine and rendering.
- `tests/test_firmware_project.py`: Source-level smoke tests for the PlatformIO project and Stage 3B firmware markers.
- `docs/dev_log.md`: Stage 3B development log after implementation.
- `docs/handoff.md`: Current status and Stage 3B run/verification instructions.

## Task 1: Stage 3B Firmware Source Tests And State Machine

**Files:**
- Modify: `tests/test_firmware_project.py`
- Modify: `firmware/src/main.cpp`

- [ ] **Step 1: Replace Stage 3A source smoke test with Stage 3B source smoke test**

In `tests/test_firmware_project.py`, replace `test_firmware_source_contains_stage3a_hardware_checks` with:

```python
    def test_firmware_source_contains_stage3b_review_ui(self):
        source = (ROOT / "firmware" / "src" / "main.cpp").read_text(encoding="utf-8")

        self.assertIn("#include <M5StickCPlus.h>", source)
        self.assertIn("StickWords Stage 3B boot", source)
        self.assertIn("enum class Page", source)
        self.assertIn("Word", source)
        self.assertIn("MeaningSummary", source)
        self.assertIn("FullExample", source)
        self.assertIn("Rating", source)
        self.assertIn("Done", source)
        self.assertIn("struct Card", source)
        self.assertIn("struct ReviewResult", source)
        self.assertIn("kCards[]", source)
        self.assertIn("abandon", source)
        self.assertIn("benefit", source)
        self.assertIn("curious", source)
        self.assertIn("forgot", source)
        self.assertIn("hard", source)
        self.assertIn("good", source)
        self.assertIn("handleButtonAShortPress", source)
        self.assertIn("handleButtonALongPress", source)
        self.assertIn("handleButtonBShortPress", source)
        self.assertIn("submitRating", source)
        self.assertIn("tryReRatePrevious", source)
        self.assertIn("Review saved word=", source)
        self.assertIn("Review overwritten word=", source)
        self.assertIn("M5.Lcd.setRotation(1)", source)
```

- [ ] **Step 2: Run firmware project tests to verify they fail**

Run:

```powershell
$env:PYTHONPATH='src'; python -m unittest tests.test_firmware_project -v
```

Expected: FAIL because current firmware still logs `StickWords Stage 3A boot` and does not contain Stage 3B state machine markers.

- [ ] **Step 3: Replace firmware with Stage 3B implementation**

Replace `firmware/src/main.cpp` with:

```cpp
#include <M5StickCPlus.h>
#include <cstring>

namespace {

enum class Page {
  Word,
  MeaningSummary,
  FullExample,
  Rating,
  Done,
};

enum class Rating {
  Forgot,
  Hard,
  Good,
};

struct Card {
  const char* word;
  const char* meaning;
  const char* example;
};

struct ReviewResult {
  bool hasRating;
  Rating rating;
  uint8_t reviewCount;
};

constexpr Card kCards[] = {
    {"abandon", "give up", "Do not abandon your plan when practice gets hard."},
    {"benefit", "good effect", "Daily review has a clear benefit."},
    {"curious", "wanting to know", "A curious learner asks better questions."},
};

constexpr size_t kCardCount = sizeof(kCards) / sizeof(kCards[0]);
constexpr uint32_t kButtonLongPressMs = 650;

ReviewResult reviewResults[kCardCount] = {};
Page currentPage = Page::Word;
size_t currentCardIndex = 0;
Rating selectedRating = Rating::Forgot;
int lastSubmittedIndex = -1;
int returnAfterReRatingIndex = -1;
bool isReRating = false;
bool needsRender = true;

const char* ratingName(Rating rating) {
  switch (rating) {
    case Rating::Forgot:
      return "forgot";
    case Rating::Hard:
      return "hard";
    case Rating::Good:
      return "good";
  }
  return "forgot";
}

const char* pageName(Page page) {
  switch (page) {
    case Page::Word:
      return "word";
    case Page::MeaningSummary:
      return "summary";
    case Page::FullExample:
      return "example";
    case Page::Rating:
      return "rating";
    case Page::Done:
      return "done";
  }
  return "word";
}

void logPage() {
  Serial.printf(
      "Page %s index=%u\n",
      pageName(currentPage),
      static_cast<unsigned>(currentCardIndex));
}

void setPage(Page page) {
  currentPage = page;
  needsRender = true;
  logPage();
}

void drawHeader(const Card& card) {
  M5.Lcd.setTextSize(2);
  M5.Lcd.println("StickWords");
  M5.Lcd.setTextSize(1);
  M5.Lcd.printf("%u/%u  %s\n\n", static_cast<unsigned>(currentCardIndex + 1),
                static_cast<unsigned>(kCardCount), card.word);
}

void drawWordPage() {
  const Card& card = kCards[currentCardIndex];
  drawHeader(card);
  M5.Lcd.setTextSize(3);
  M5.Lcd.println(card.word);
  M5.Lcd.setTextSize(1);
  M5.Lcd.println();
  M5.Lcd.println("A: next");
  M5.Lcd.println("B: re-rate prev");
}

void drawMeaningSummaryPage() {
  const Card& card = kCards[currentCardIndex];
  drawHeader(card);
  M5.Lcd.printf("meaning: %s\n\n", card.meaning);
  M5.Lcd.print("example: ");
  for (uint8_t i = 0; card.example[i] != '\0' && i < 18; ++i) {
    M5.Lcd.print(card.example[i]);
  }
  if (std::strlen(card.example) > 18) {
    M5.Lcd.print("...");
  }
  M5.Lcd.println();
  M5.Lcd.println();
  M5.Lcd.println("A: full example");
  M5.Lcd.println("B: back");
}

void drawFullExamplePage() {
  const Card& card = kCards[currentCardIndex];
  drawHeader(card);
  M5.Lcd.println(card.example);
  M5.Lcd.println();
  M5.Lcd.println("A: rating");
  M5.Lcd.println("B: back");
}

void drawRatingOption(Rating rating) {
  M5.Lcd.printf("%c %s\n", rating == selectedRating ? '>' : ' ', ratingName(rating));
}

void drawRatingPage() {
  const Card& card = kCards[currentCardIndex];
  drawHeader(card);
  M5.Lcd.println("Rating");
  drawRatingOption(Rating::Forgot);
  drawRatingOption(Rating::Hard);
  drawRatingOption(Rating::Good);
  M5.Lcd.println();
  M5.Lcd.println("A: change");
  M5.Lcd.println("Hold A: save");
  M5.Lcd.println("B: back");
}

void drawDonePage() {
  M5.Lcd.setTextSize(2);
  M5.Lcd.println("Review complete");
  M5.Lcd.setTextSize(1);
  M5.Lcd.printf("%u/%u cards rated\n\n", static_cast<unsigned>(kCardCount),
                static_cast<unsigned>(kCardCount));
  M5.Lcd.println("A: restart");
  M5.Lcd.println("B: re-rate last");
}

void render() {
  if (!needsRender) {
    return;
  }

  needsRender = false;
  M5.Lcd.fillScreen(BLACK);
  M5.Lcd.setCursor(8, 8);
  M5.Lcd.setTextColor(WHITE, BLACK);
  M5.Lcd.setTextSize(1);

  switch (currentPage) {
    case Page::Word:
      drawWordPage();
      break;
    case Page::MeaningSummary:
      drawMeaningSummaryPage();
      break;
    case Page::FullExample:
      drawFullExamplePage();
      break;
    case Page::Rating:
      drawRatingPage();
      break;
    case Page::Done:
      drawDonePage();
      break;
  }
}

Rating nextRating(Rating rating) {
  switch (rating) {
    case Rating::Forgot:
      return Rating::Hard;
    case Rating::Hard:
      return Rating::Good;
    case Rating::Good:
      return Rating::Forgot;
  }
  return Rating::Forgot;
}

void resetReviewSet() {
  for (size_t i = 0; i < kCardCount; ++i) {
    reviewResults[i] = {false, Rating::Forgot, 0};
  }
  currentCardIndex = 0;
  selectedRating = Rating::Forgot;
  lastSubmittedIndex = -1;
  returnAfterReRatingIndex = -1;
  isReRating = false;
  setPage(Page::Word);
}

void submitRating() {
  ReviewResult& result = reviewResults[currentCardIndex];
  const Card& card = kCards[currentCardIndex];

  if (result.hasRating) {
    Serial.printf("Review overwritten word=%s old=%s new=%s\n", card.word,
                  ratingName(result.rating), ratingName(selectedRating));
  } else {
    Serial.printf("Review saved word=%s rating=%s\n", card.word,
                  ratingName(selectedRating));
  }

  result.hasRating = true;
  result.rating = selectedRating;
  result.reviewCount += 1;
  lastSubmittedIndex = static_cast<int>(currentCardIndex);

  if (isReRating && returnAfterReRatingIndex >= 0) {
    currentCardIndex = static_cast<size_t>(returnAfterReRatingIndex);
    returnAfterReRatingIndex = -1;
    isReRating = false;
    setPage(currentCardIndex >= kCardCount ? Page::Done : Page::Word);
    return;
  }

  ++currentCardIndex;
  if (currentCardIndex >= kCardCount) {
    Serial.println("Review complete");
    setPage(Page::Done);
    return;
  }

  selectedRating = Rating::Forgot;
  setPage(Page::Word);
}

bool tryReRatePrevious() {
  const int previousIndex = currentPage == Page::Done
                                ? static_cast<int>(kCardCount - 1)
                                : static_cast<int>(currentCardIndex) - 1;

  if (previousIndex < 0 || !reviewResults[previousIndex].hasRating) {
    Serial.println("No previous review to re-rate");
    return false;
  }

  returnAfterReRatingIndex = currentPage == Page::Done
                                 ? static_cast<int>(kCardCount)
                                 : static_cast<int>(currentCardIndex);
  currentCardIndex = static_cast<size_t>(previousIndex);
  selectedRating = reviewResults[currentCardIndex].rating;
  isReRating = true;
  Serial.printf("Re-rating previous word=%s rating=%s\n", kCards[currentCardIndex].word,
                ratingName(selectedRating));
  setPage(Page::Rating);
  return true;
}

void handleButtonAShortPress() {
  switch (currentPage) {
    case Page::Word:
      setPage(Page::MeaningSummary);
      break;
    case Page::MeaningSummary:
      setPage(Page::FullExample);
      break;
    case Page::FullExample:
      selectedRating = reviewResults[currentCardIndex].hasRating
                           ? reviewResults[currentCardIndex].rating
                           : Rating::Forgot;
      setPage(Page::Rating);
      Serial.printf("Page rating index=%u selected=%s\n",
                    static_cast<unsigned>(currentCardIndex), ratingName(selectedRating));
      break;
    case Page::Rating:
      selectedRating = nextRating(selectedRating);
      Serial.printf("Rating changed word=%s rating=%s\n", kCards[currentCardIndex].word,
                    ratingName(selectedRating));
      needsRender = true;
      break;
    case Page::Done:
      resetReviewSet();
      break;
  }
}

void handleButtonALongPress() {
  if (currentPage == Page::Rating) {
    submitRating();
  }
}

void handleButtonBShortPress() {
  switch (currentPage) {
    case Page::Word:
      tryReRatePrevious();
      break;
    case Page::MeaningSummary:
      setPage(Page::Word);
      break;
    case Page::FullExample:
      setPage(Page::MeaningSummary);
      break;
    case Page::Rating:
      setPage(Page::FullExample);
      break;
    case Page::Done:
      tryReRatePrevious();
      break;
  }
}

}  // namespace

void setup() {
  M5.begin();
  M5.Imu.Init();
  Serial.begin(115200);
  delay(200);

  M5.Lcd.setRotation(1);
  M5.Lcd.setTextFont(1);
  M5.Lcd.setTextDatum(TL_DATUM);

  Serial.println("StickWords Stage 3B boot");
  logPage();
  render();
}

void loop() {
  M5.update();

  if (M5.BtnA.wasReleasefor(kButtonLongPressMs)) {
    handleButtonALongPress();
  } else if (M5.BtnA.wasReleased()) {
    handleButtonAShortPress();
  }

  if (M5.BtnB.wasReleased()) {
    handleButtonBShortPress();
  }

  render();
  delay(20);
}
```

- [ ] **Step 4: Run firmware source tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m unittest tests.test_firmware_project -v
```

Expected: PASS.

- [ ] **Step 5: Run full Python test suite**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONPATH='src'; python -m unittest discover -s tests -v
```

Expected: PASS, 51 tests.

- [ ] **Step 6: Build firmware with PlatformIO**

Run:

```powershell
cd C:\Users\ASUS\Documents\M5Stick\firmware
pio run
```

Expected: SUCCESS.

If `pio` is unavailable in the active shell, use:

```powershell
$env:Path = "$env:USERPROFILE\.platformio\penv\Scripts;$env:Path"
pio run
```

- [ ] **Step 7: Commit**

Run:

```powershell
git add firmware/src/main.cpp tests/test_firmware_project.py
git commit -m "Implement Stage 3B review UI prototype"
```

## Task 2: Stage 3B Documentation

**Files:**
- Modify: `docs/dev_log.md`
- Modify: `docs/handoff.md`

- [ ] **Step 1: Append Stage 3B development log**

Append to `docs/dev_log.md`:

```markdown
## 2026-05-24 阶段 3B：按键版最小复习 UI

完成内容：

- 将 Stage 3A 硬件检查固件升级为 Stage 3B 本地复习 UI 原型。
- 内置 3 张假数据卡片，不连接 PC 后端。
- 实现单线流程：单词页 -> 释义摘要页 -> 完整例句页 -> 评分页 -> 下一词。
- 评分页支持 Button A 短按循环 `forgot / hard / good`，Button A 长按提交。
- 实现下一词单词页 Button B 回上一词评分页重新评分。
- 重新评分会覆盖 RAM 中上一条评分结果，并打印串口日志。
- 完成 3 张卡片后显示 done 页面。

测试结果：

- 仓库级 Python 测试：
  `$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONPATH='src'; python -m unittest discover -s tests -v`
- 固件编译：
  `cd C:\Users\ASUS\Documents\M5Stick\firmware`
  `pio run`

遇到的问题：

- Stage 3B 仍是固件内假数据和 RAM 结果，重启后评分消失。
- 为保持手感，评分提交后不加声音、不震动、不停顿，只通过串口记录结果。

解决方式：

- 使用明确的页面枚举、评分枚举和 RAM review result 数组组织状态机。
- 只在 UI 状态变化时重绘屏幕，降低闪烁。
- 将重评分支限制在刚进入下一词或完成页的 Button B 操作上。

下一步：

- 在真实 M5Stick C Plus 上验证 Stage 3B 交互。
- 通过后进入 Stage 3C：逐步加入倾斜评分、双摇 `good` 和左右手自动旋转。
```

- [ ] **Step 2: Update handoff current status and firmware instructions**

In `docs/handoff.md`:

Change current status to:

```markdown
Stage 2 PC web management page is implemented and tested.
Stage 3A M5Stick hardware check firmware is implemented and validated on the real device.
Stage 3B review UI prototype is implemented and ready for real-device validation.
```

In `What Works`, add:

```markdown
- Stage 3B review UI prototype:
  - three built-in fake cards
  - word, summary, full example, rating, and done pages
  - Button A short press advances pages or cycles rating
  - Button A long press submits rating
  - Button B returns to previous page or re-rates previous card
  - in-memory rating overwrite logs
```

In `Known Limits`, add or keep:

```markdown
- Stage 3B still uses built-in fake cards.
- Stage 3B ratings are stored only in RAM and disappear after reboot.
- Firmware does not implement tilt scoring yet.
- Firmware does not implement double-shake `good` yet.
```

Change `Next Stage` to:

```markdown
Validate Stage 3B on the real M5Stick C Plus. After it passes, build Stage 3C: add tilt rating, double-shake `good`, and left/right hand auto-rotation one at a time.
```

- [ ] **Step 3: Run full Python test suite**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONPATH='src'; python -m unittest discover -s tests -v
```

Expected: PASS, 51 tests.

- [ ] **Step 4: Commit**

Run:

```powershell
git add docs/dev_log.md docs/handoff.md
git commit -m "Document Stage 3B review UI workflow"
```

## Task 3: Final Verification And Real-Device Checklist

**Files:**
- Modify: `docs/dev_log.md` and `docs/handoff.md` only if real-device validation results should be recorded.

- [ ] **Step 1: Run full Python test suite**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONPATH='src'; python -m unittest discover -s tests -v
```

Expected: PASS, 51 tests.

- [ ] **Step 2: Build firmware**

Run:

```powershell
cd C:\Users\ASUS\Documents\M5Stick\firmware
pio run
```

Expected: SUCCESS.

- [ ] **Step 3: Check git status**

Run:

```powershell
git status --short
```

Expected: no output.

- [ ] **Step 4: Give the user real-device validation commands**

Ask the user to run:

```powershell
cd C:\Users\ASUS\Documents\M5Stick\firmware
pio run --target upload --upload-port COM5
pio device monitor --port COM5
```

Ask them to verify:

```text
1. First screen shows word page for abandon.
2. Button A advances to summary.
3. Button A advances to full example.
4. Button A advances to rating.
5. On rating page, Button A short press cycles forgot/hard/good.
6. On rating page, Button A long press submits and immediately opens benefit.
7. On benefit word page, Button B returns to abandon rating page.
8. Re-rating abandon overwrites the previous serial result and returns to benefit.
9. Repeating through all cards reaches Review complete.
10. Button A on Review complete restarts the three-card set.
```

- [ ] **Step 5: Record real-device validation if the user confirms**

If the user confirms all checks pass, update:

```text
docs/dev_log.md
docs/handoff.md
```

Commit:

```powershell
git add docs/dev_log.md docs/handoff.md
git commit -m "Record Stage 3B device validation"
```

## Self-Review

Spec coverage:

- Three fake cards: Task 1.
- Word, summary, full example, rating, done pages: Task 1.
- Button A short press flow: Task 1.
- Button A long press submit: Task 1.
- Button B page back and previous-card re-rating: Task 1.
- In-memory rating result and overwrite: Task 1.
- No confirmation delay/sound/vibration: Task 1 and docs.
- Serial logs: Task 1.
- Repository tests: Task 1.
- Documentation and handoff: Task 2.
- Real-device checklist: Task 3.

Out-of-scope protection:

- No Wi-Fi code.
- No HTTP code.
- No CSV code.
- No persistent storage.
- No tilt scoring.
- No double-shake detection.
- No auto-rotation.
- No USB configuration.

Type and API consistency:

- `Page`, `Rating`, `Card`, and `ReviewResult` are defined before use.
- Button handlers are named exactly as tests expect: `handleButtonAShortPress`, `handleButtonALongPress`, `handleButtonBShortPress`.
- Re-rating helper is named `tryReRatePrevious`.
- Serial speed remains `115200`.
- Screen remains fixed landscape with `M5.Lcd.setRotation(1)`.
