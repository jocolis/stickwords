# StickWords Stage 3B UI Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Polish the Stage 3B M5Stick review UI so screen space is focused on the current review content.

**Architecture:** Keep the existing Stage 3B state machine and button handlers unchanged. Adjust only rendering helpers in `firmware/src/main.cpp` and strengthen source smoke tests in `tests/test_firmware_project.py`.

**Tech Stack:** PlatformIO, Arduino framework, M5StickCPlus, Python `unittest`.

---

## Task 1: Remove Headers And Button Hints

**Files:**
- Modify: `firmware/src/main.cpp`
- Modify: `tests/test_firmware_project.py`

- [ ] **Step 1: Add UI polish source assertions**

In `tests/test_firmware_project.py`, add a new test:

```python
    def test_stage3b_screen_removes_old_headers_and_button_hints(self):
        source = (ROOT / "firmware" / "src" / "main.cpp").read_text(encoding="utf-8")

        self.assertNotIn('M5.Lcd.println("StickWords")', source)
        self.assertNotIn("A: next", source)
        self.assertNotIn("A: full example", source)
        self.assertNotIn("A: rating", source)
        self.assertNotIn("A: change", source)
        self.assertNotIn("A: restart", source)
        self.assertNotIn("B: back", source)
        self.assertNotIn("B: re-rate", source)
        self.assertNotIn("Hold A: save", source)
        self.assertIn("StickWords Stage 3B boot", source)
```

- [ ] **Step 2: Run firmware tests to verify they fail**

Run:

```powershell
$env:PYTHONPATH='src'; python -m unittest tests.test_firmware_project -v
```

Expected: FAIL because current firmware still prints screen title/button hints.

- [ ] **Step 3: Update rendering helpers**

Modify `firmware/src/main.cpp`:

- Remove `drawHeader`.
- Add a centered text helper:

```cpp
void drawCenteredText(const char* text, int16_t y, uint8_t textSize) {
  M5.Lcd.setTextSize(textSize);
  const int16_t textWidth = M5.Lcd.textWidth(text);
  const int16_t x = (240 - textWidth) / 2;
  M5.Lcd.setCursor(x < 0 ? 0 : x, y);
  M5.Lcd.println(text);
}
```

- Change `drawWordPage()` to only show the word, centered:

```cpp
void drawWordPage() {
  drawCenteredText(kCards[currentCardIndex].word, 52, 3);
}
```

- Change `drawMeaningSummaryPage()` to use more vertical space:

```cpp
void drawMeaningSummaryPage() {
  const Card& card = kCards[currentCardIndex];
  M5.Lcd.setTextSize(2);
  M5.Lcd.println(card.word);
  M5.Lcd.println();
  M5.Lcd.setTextSize(1);
  M5.Lcd.printf("meaning: %s\n", card.meaning);
  M5.Lcd.println();
  M5.Lcd.print("example: ");
  for (uint8_t i = 0; card.example[i] != '\0' && i < 38; ++i) {
    M5.Lcd.print(card.example[i]);
  }
  if (std::strlen(card.example) > 38) {
    M5.Lcd.print("...");
  }
  M5.Lcd.println();
}
```

- Change `drawFullExamplePage()`:

```cpp
void drawFullExamplePage() {
  M5.Lcd.setTextSize(2);
  M5.Lcd.println(kCards[currentCardIndex].example);
}
```

- Change `drawRatingPage()`:

```cpp
void drawRatingPage() {
  const Card& card = kCards[currentCardIndex];
  M5.Lcd.setTextSize(2);
  M5.Lcd.println(card.word);
  M5.Lcd.println();
  drawRatingOption(Rating::Forgot);
  drawRatingOption(Rating::Hard);
  drawRatingOption(Rating::Good);
}
```

- Change `drawDonePage()`:

```cpp
void drawDonePage() {
  drawCenteredText("Review complete", 38, 2);
  drawCenteredText("3/3 rated", 76, 2);
}
```

- Ensure no screen-rendered button hints remain.

- [ ] **Step 4: Run firmware tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m unittest tests.test_firmware_project -v
```

Expected: PASS.

- [ ] **Step 5: Run full Python tests**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONPATH='src'; python -m unittest discover -s tests -v
```

Expected: PASS.

- [ ] **Step 6: Build firmware**

Run:

```powershell
cd C:\Users\ASUS\Documents\M5Stick\firmware
$env:Path = "$env:USERPROFILE\.platformio\penv\Scripts;$env:Path"
pio run
```

Expected: SUCCESS.

- [ ] **Step 7: Commit**

Run:

```powershell
git add firmware/src/main.cpp tests/test_firmware_project.py
git commit -m "Polish Stage 3B review UI layout"
```

## Task 2: Final Verification

- [ ] **Step 1: Run full Python tests**

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONPATH='src'; python -m unittest discover -s tests -v
```

- [ ] **Step 2: Run PlatformIO build**

```powershell
cd C:\Users\ASUS\Documents\M5Stick\firmware
$env:Path = "$env:USERPROFILE\.platformio\penv\Scripts;$env:Path"
pio run
```

- [ ] **Step 3: Give user upload command**

```powershell
pio run --target upload --upload-port COM5
pio device monitor --port COM5
```

Ask the user to verify:

```text
1. Word page shows only a large centered word.
2. Summary page has no title/header/footer hints and uses more vertical space.
3. Full example page has no title/header/footer hints.
4. Rating page shows current word and ratings only.
5. Done page shows Review complete and 3/3 rated only.
6. Button behavior is unchanged.
```
