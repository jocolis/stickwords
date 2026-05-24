# StickWords Stage 3B UI Polish Design

## Goal

Improve the Stage 3B M5Stick C Plus review UI so the small 240x135 landscape screen is used mainly for the current review content.

The review interaction logic stays unchanged:

```text
word -> summary -> full example -> rating -> next word
```

Button behavior, rating submission, and previous-card re-rating remain the same.

## Scope

This polish changes only `firmware/src/main.cpp` rendering behavior.

It will:

- Remove the `StickWords` title from review pages.
- Remove the `1/3 abandon` header line from review pages.
- Remove bottom button hints such as `A: next`, `B: back`, and `Hold A: save`.
- Give the main content more vertical room.
- Keep serial logs for debugging instead of showing operation help on screen.

## Page Layout

### Word Page

The word page shows only the current word.

Layout:

```text
abandon
```

The word is large and centered on the screen.

### Meaning Summary Page

The summary page shows:

```text
abandon
meaning: give up
example: Do not abandon...
```

Meaning and example text should be larger than the previous Stage 3B version.

The example summary may end with `...`.

### Full Example Page

The full example page uses the available screen area for the example text.

Scrolling is still out of scope. If a line is too long, clipping is acceptable in this stage.

### Rating Page

The rating page keeps the current word and the three choices:

```text
abandon
> forgot
  hard
  good
```

The `>` marker remains the visible selection indicator.

No button hints are shown.

### Done Page

The done page shows:

```text
Review complete
3/3 rated
```

No button hints are shown.

## Out Of Scope

This polish does not change:

- Button behavior.
- Rating values.
- Previous-card re-rating.
- Serial logs.
- Fake card data.
- Wi-Fi.
- Persistence.
- Tilt scoring.
- Double-shake `good`.
- Auto-rotation.

## Verification

Repository-level tests should check that the firmware source no longer contains old screen hints:

```text
A: next
B: back
Hold A: save
M5.Lcd.println("StickWords")
```

The test should still allow `StickWords Stage 3B boot` as a serial boot log.

Manual validation on device:

1. Word page shows only a large centered word.
2. Summary page uses more of the vertical space.
3. Full example page has no header or button hints.
4. Rating page shows the current word and `forgot / hard / good`.
5. Button behavior is unchanged.
