# StickWords Stage 3B Review UI Design

## Goal

Stage 3B turns the M5Stick C Plus firmware from a hardware check into a minimum review UI prototype.

The goal is to prove that the device can run the core single-line review flow with local fake cards:

```text
word page -> meaning + example summary -> full example -> rating page -> next word
```

This stage validates UI state transitions, Button A/Button B behavior, rating selection, rating submission, and previous-card re-rating. It does not connect to the PC backend yet.

## Scope

Stage 3B will modify the existing PlatformIO firmware:

```text
firmware/src/main.cpp
```

The firmware will contain three built-in fake cards. Each card has:

```text
word
meaning
example
```

The firmware will store review results in RAM only. Results disappear after reboot. This is intentional for Stage 3B.

## Out Of Scope

Stage 3B will not implement:

- Wi-Fi.
- HTTP sync.
- PC backend API calls.
- CSV loading.
- Local persistent cache.
- Power-loss recovery.
- IMU tilt scoring.
- Double-shake `good`.
- Left-hand/right-hand auto-rotation.
- Sound, vibration, or a confirmation delay after saving a rating.
- USB configuration protocol.

These remain later stages.

## UI Pages

Stage 3B has four review pages:

```text
Word
MeaningSummary
FullExample
Rating
```

### Word Page

Shows:

```text
StickWords
1/3
abandon
```

Button behavior:

```text
Button A short press -> MeaningSummary
Button B short press -> previous-card re-rating only if this card follows a submitted rating
```

If there is no previous rating available, Button B stays on the word page and prints a serial note.

### Meaning + Example Summary Page

Shows:

```text
abandon
meaning: 放弃
example: Do not abandon...
```

The summary page shows the beginning of the example and uses `...` when shortened.

Button behavior:

```text
Button A short press -> FullExample
Button B short press -> Word
```

### Full Example Page

Shows the full example. If it is too long for the screen, Stage 3B may wrap or clip text; scrolling is not required in this stage.

Button behavior:

```text
Button A short press -> Rating
Button B short press -> MeaningSummary
```

### Rating Page

Shows:

```text
abandon
Rating
> forgot
  hard
  good
```

Button behavior:

```text
Button A short press -> cycle forgot / hard / good
Button A long press -> submit selected rating, immediately go to next word
Button B short press -> FullExample
```

There is no screen pause after submission. The firmware prints the saved rating to serial for debugging.

## Rating Model

Ratings are:

```text
forgot
hard
good
```

Stage 3B stores each result in RAM:

```text
card index
rating
review count
```

The firmware does not calculate due dates. It does not modify PC CSV data.

## Previous-Card Re-Rating

Stage 3B implements the previous-card re-rating behavior in memory.

After the user submits a rating and enters the next card's word page:

```text
Button B short press -> go back to the previous card's Rating page
```

The previous card's last submitted rating should be selected on the rating page.

If the user long-presses Button A again:

```text
The previous result is overwritten in RAM.
The firmware immediately returns to the next card's word page.
```

Serial logging should distinguish first save from overwrite:

```text
Review saved word=abandon rating=good
Review overwritten word=abandon old=good new=hard
```

This stage does not persist the overwritten result across reboot.

## End Of Review Set

After the last card is submitted, Stage 3B shows a done page:

```text
Review complete
3/3 cards rated
Button A: restart
```

Button behavior:

```text
Button A short press -> restart from the first card and clear RAM review results
Button B short press -> previous-card re-rating for the last card if available
```

This done page keeps Stage 3B testable without needing more fake data.

## Button Event Rules

Stage 3B uses only Button A and Button B:

```text
Button A short press:
  advance page, or cycle rating on Rating page, or restart on Done page

Button A long press:
  submit rating only on Rating page

Button B short press:
  go back one page, or trigger previous-card re-rating from a word/done page
```

Power key remains outside application control.

Double click is not used in Stage 3B.

## Rendering

The screen remains fixed landscape, as in Stage 3A:

```cpp
M5.Lcd.setRotation(1)
```

Stage 3B should redraw only when UI state changes, not every 250 ms. This reduces flicker and makes the UI feel steadier.

Text should be kept short and readable on the 240x135 screen. Long example text can be clipped or line-wrapped. A full scrolling text viewer is out of scope.

## Serial Logs

Serial logs are part of the Stage 3B verification surface.

Expected log examples:

```text
StickWords Stage 3B boot
Page word index=0
Page rating index=0 selected=forgot
Rating changed word=abandon rating=hard
Review saved word=abandon rating=hard
Re-rating previous word=abandon rating=hard
Review overwritten word=abandon old=hard new=good
Review complete
```

Logs help verify behavior without relying only on the small screen.

## Test And Verification

Repository-level tests should check that the firmware source contains:

- Stage 3B boot log.
- Three fake cards.
- The four review pages.
- The three ratings.
- Button A short press handling.
- Button A long press handling.
- Button B previous-page and previous-card behavior.
- Serial messages for saved and overwritten reviews.

Manual device verification:

1. Build succeeds with `pio run`.
2. Upload succeeds with `pio run --target upload --upload-port COM5`.
3. Serial monitor opens with `pio device monitor --port COM5`.
4. Device shows the first word page.
5. Button A advances through word, summary, full example, and rating.
6. On rating page, Button A short press cycles ratings.
7. On rating page, Button A long press submits and immediately shows the next card.
8. On the next card's word page, Button B returns to the previous card's rating page.
9. Re-rating overwrites the previous in-memory result and returns to the next card.
10. After three cards, the done page appears.

## Next Stage

After Stage 3B passes on the device, Stage 3C should add one interaction layer at a time:

```text
tilt rating -> double-shake good -> left/right hand auto-rotation
```

Wi-Fi sync and persistent recovery remain later stages.
