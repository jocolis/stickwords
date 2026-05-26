# StickWords Offline Due Scheduling Design

## Goal

Allow the M5Stick C Plus to keep reviewing while Wi-Fi or the PC backend is unavailable.

On each successful sync, the PC sends an offline review package containing:

- Review cards due within the next 7 days.
- A small new-card reserve, initially up to 20 new words.
- The scheduling metadata needed for the M5Stick to update those cached cards after offline reviews.

When offline, the M5Stick uses its BM8563 RTC to decide which cached cards are currently due. If a cached card is reviewed offline and becomes due again during the same offline period, the M5Stick can show it again.

## Non-Goals

- Do not cache the full `vocab.csv` on the M5Stick.
- Do not implement deck support or card browsing.
- Do not make the M5Stick the source of truth. The PC CSV remains canonical after sync.
- Do not add Chinese font rendering in this milestone.
- Do not solve automatic PC/backend discovery in this milestone.

## PC Sync Payload

Extend `GET /api/device/tasks?limit=...` to include an offline package while preserving the current `tasks` array for the immediate review flow.

Recommended response shape:

```json
{
  "generated_at": "2026-05-26T10:00:00Z",
  "tasks": [
    {
      "id": "w-000001",
      "word": "abandon",
      "meaning": "to leave something behind",
      "example": "He abandoned the plan.",
      "status": "review",
      "due_at": "2026-05-26T09:00:00Z",
      "review_count": 3,
      "ease": 2.5,
      "interval_days": 4,
      "lapses": 0
    }
  ],
  "offline": {
    "horizon_days": 7,
    "max_new": 20,
    "cards": [
      {
        "id": "w-000002",
        "word": "remote",
        "meaning": "far away",
        "example": "They worked from a remote village.",
        "status": "review",
        "due_at": "2026-05-29T09:00:00Z",
        "review_count": 1,
        "ease": 2.55,
        "interval_days": 1,
        "lapses": 0
      }
    ]
  }
}
```

The `tasks` array remains the immediate due/new list used after an online boot. The `offline.cards` array is the broader local cache. To keep the firmware simpler, cards in both arrays use the same object shape.

## PC Selection Rules

The offline package is built from non-suspended words only.

Due cards:

- Include words whose status is not `new`.
- Include when `due_at <= generated_at + 7 days`.
- Sort by `due_at`, then case-insensitive word.
- Cap at 20 due cards for the first implementation.

New cards:

- Include words whose status is `new`.
- Sort by `added_at`, then case-insensitive word.
- Cap at 20 new cards.

The firmware should raise its cache capacity from the current 20 cards to 40 cards for this milestone. If the combined due and new set still exceeds firmware capacity later, due cards win over new cards.

## Firmware Data Model

Extend `DeviceCard` to store scheduling metadata:

- `status`
- `dueAt`
- `reviewCount`
- `ease`
- `intervalDays`
- `lapses`

Use bounded fixed-size fields, matching the current firmware style. Timestamps stay as UTC ISO strings internally, with display conversion remaining separate.

The firmware should persist the whole offline cache in ESP32 flash through `Preferences`, replacing the old "last immediate tasks only" cache.

For the first implementation, use separate limits for clarity:

- `kMaxImmediateCards = 20` for the currently due review flow.
- `kMaxOfflineCards = 40` for the 7-day due plus new reserve cache.

## Offline Task Selection

On boot:

1. Load pending review events.
2. If Wi-Fi and backend sync succeed, upload pending events first, then fetch the latest online payload and replace the offline cache.
3. If Wi-Fi or sync fails, load the offline cache.
4. Read RTC. If RTC is invalid, show a status page such as `RTC invalid / sync needed`.
5. Select cached review cards whose `due_at <= RTC now`.
6. If no review cards are due, optionally select new cards from the cached reserve.
7. If no cards are available, show `No due cards`.

This keeps offline behavior predictable: the M5Stick only schedules cards it has already received from the PC.

## Offline Local Scheduling

After a cached card is reviewed offline, the M5Stick updates that card locally using the same simplified scheduling rules as the PC:

- `forgot`: status becomes `learning`, lapses increases by 1, ease decreases by 0.20 with floor 1.30, interval becomes 0, due becomes reviewed time plus 10 minutes.
- `hard`: status becomes `review`, ease decreases by 0.05 with floor 1.30, interval becomes `max(1, round(interval_days * 1.2))`, due becomes reviewed time plus interval days.
- `good`: status becomes `review`, ease increases by 0.05 with ceiling 3.00, interval becomes 1 if it was 0, otherwise `max(1, round(interval_days * ease))`, due becomes reviewed time plus interval days.

This enables the same card to become due again during a long offline session.

## Pending Review Events

Change the firmware pending queue from "one latest pending review per word" to an append-only event queue.

Each offline review should store:

- `word_id`
- `rating`
- `reviewed_at`
- `sequence`
- upload marker

The PC already processes review events through event IDs and skips duplicates. On reconnect, the M5Stick uploads every not-yet-uploaded event. The PC applies new events in review-time order and persists the final current state in `vocab.csv`.

`vocab.csv` remains one row per word. If `review_events.csv` exists, it preserves the multi-event history; otherwise the essential result is still the updated current state.

## Conflict And Recovery Rules

- Duplicate uploads are handled by event ID idempotency on the PC.
- If upload partially fails, keep unsent events in the pending queue.
- If the M5Stick cache is stale because the user edited CSV on the PC while the device was offline, PC sync remains authoritative after reconnect.
- If a word was suspended or deleted on the PC while offline events exist for it, the PC should reject or report those events as failed using the existing error path.
- If pending queue capacity is full, the firmware should stop accepting more offline ratings and show a clear status message instead of silently losing events.

## Testing Strategy

PC tests:

- Offline payload includes future due cards within 7 days and excludes later cards.
- Offline payload includes new cards up to the configured limit.
- Suspended words are excluded.
- Device review processing applies multiple events for the same word in timestamp order.
- Duplicate event IDs are skipped.

Firmware source tests:

- `DeviceCard` includes scheduling fields.
- JSON parser reads scheduling fields.
- Cache save/load persists scheduling fields.
- Offline selection uses RTC time and `due_at`.
- Pending queue appends multiple reviews for the same word.
- Pending review JSON uses each event's own `reviewed_at`.
- Local scheduling updates cached card state after rating.

Manual M5Stick tests:

- Online sync caches future cards.
- Disable Wi-Fi or stop the backend, then boot from cache.
- A future-due card does not show before its RTC time.
- After RTC reaches due time, the card appears offline.
- Review a card offline with `forgot`; after 10 minutes, it appears again.
- Restore Wi-Fi and confirm all offline review events upload.

## Implementation Notes

This should be implemented in two code milestones:

1. PC payload and firmware cache/selection: sync an offline package, cache it, and select currently due cards offline.
2. Local offline scheduling and append-only pending events: update cached state after ratings and upload multiple events for the same word.

This split keeps each firmware change small enough to test on the device before adding the next layer.
