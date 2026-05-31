#include <HTTPClient.h>
#include <DNSServer.h>
#include <M5Unified.h>
#include <Preferences.h>
#include <WebServer.h>
#include <src/core/lv_disp.h>
#include <src/core/lv_obj.h>
#include <src/core/lv_refr.h>
#include <src/font/lv_symbol_def.h>
#include <src/hal/lv_hal_disp.h>
#include <src/misc/lv_timer.h>
#include <src/widgets/lv_arc.h>
#include <src/widgets/lv_label.h>
#include <WiFi.h>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <esp_system.h>

#if __has_include("secrets.h")
#include "secrets.h"
#else
#error "Missing firmware/include/secrets.h: copy firmware/include/secrets.example.h to firmware/include/secrets.h, then edit Wi-Fi and PC URL values."
#endif

namespace {

enum class Page {
  Status,
  Clock,
  Word,
  Meaning,
  Example,
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
constexpr size_t kMaxImmediateCards = 20;
constexpr size_t kMaxOfflineCards = 40;
constexpr size_t kMaxSyncedCards = kMaxImmediateCards;
constexpr size_t kMaxPendingReviews = 20;
constexpr size_t kMaxWordIdLength = 24;
constexpr size_t kMaxWordLength = 32;
constexpr size_t kMaxMeaningLength = 192;
constexpr size_t kMaxExampleLength = 256;
constexpr size_t kMaxTimestampLength = 25;
constexpr size_t kMaxSsidLength = 33;
constexpr size_t kMaxPasswordLength = 65;
constexpr size_t kMaxServerUrlLength = 96;
constexpr uint32_t kButtonLongPressMs = 650;
constexpr uint32_t kOrientationStableMs = 500;
constexpr uint32_t kIdlePowerOffMs = 180000;
constexpr uint32_t kClockIdlePowerOffMs = 300000;
constexpr uint32_t kClockRefreshMs = 50;
constexpr uint32_t kClockColonPulseMs = 1000;
constexpr lv_opa_t kClockColonMinOpacity = 0;
constexpr lv_opa_t kClockColonMaxOpacity = 255;
constexpr uint32_t kShakeWindowMs = 650;
constexpr uint32_t kShakeCooldownMs = 900;
constexpr uint8_t kClockDisplayUtcOffsetHours = 8;
constexpr uint8_t kContentTextSize = 2;
constexpr int16_t kContentX = 6;
constexpr int16_t kContentY = 6;
constexpr int16_t kContentMaxX = 234;
constexpr int16_t kContentMaxY = 132;
constexpr int16_t kContentLineHeight = 18;
constexpr float kOrientationThreshold = 0.45F;
constexpr float kShakeThreshold = 1.65F;
constexpr float kShakeReleaseThreshold = 1.25F;

struct LegacyDeviceCard {
  char id[kMaxWordIdLength];
  char word[kMaxWordLength];
  char meaning[kMaxMeaningLength];
  char example[kMaxExampleLength];
};

struct DeviceCard {
  char id[kMaxWordIdLength];
  char word[kMaxWordLength];
  char meaning[kMaxMeaningLength];
  char example[kMaxExampleLength];
  char status[12];
  char dueAt[kMaxTimestampLength];
  uint16_t reviewCount;
  float ease;
  int16_t intervalDays;
  uint16_t lapses;
};

struct CardArrayParseResult {
  bool valid;
  size_t count;
};

struct PendingReview {
  char wordId[kMaxWordIdLength];
  Rating rating;
  char reviewedAt[kMaxTimestampLength];
  uint32_t sequence;
  bool uploaded;
};

struct LegacyPendingReview {
  char wordId[kMaxWordIdLength];
  Rating rating;
  uint32_t reviewedAtMs;
  uint32_t sequence;
  bool uploaded;
};

struct RuntimeConfig {
  char ssid[kMaxSsidLength];
  char password[kMaxPasswordLength];
  char serverUrl[kMaxServerUrlLength];
  bool valid;
};

struct RtcTimestamp {
  uint16_t year;
  uint8_t month;
  uint8_t date;
  uint8_t hour;
  uint8_t minute;
  uint8_t second;
  uint8_t weekDay;
};

ReviewResult reviewResults[kMaxSyncedCards] = {};
DeviceCard syncedCards[kMaxSyncedCards] = {};
DeviceCard offlineCards[kMaxOfflineCards] = {};
PendingReview pendingReviews[kMaxPendingReviews] = {};
Preferences storage;
Preferences cacheStorage;
RuntimeConfig runtimeConfig;
DNSServer dnsServer;
WebServer setupServer(80);
size_t syncedCardCount = 0;
size_t offlineCardCount = 0;
size_t pendingReviewCount = 0;
char serverGeneratedAt[kMaxTimestampLength] = "";
char statusLine1[32] = "Sync...";
char statusLine2[32] = "";
char statusLine3[32] = "";
uint32_t tasksFetchedAtMs = 0;
uint32_t reviewBootNonce = 0;
uint32_t reviewSequence = 0;
Page currentPage = Page::Word;
Page clockExitPage = Page::Word;
size_t currentCardIndex = 0;
size_t contentPageStart = 0;
uint8_t currentRotation = 1;
uint8_t pendingRotation = 1;
uint32_t pendingRotationSince = 0;
float accelX = 0.0F;
float accelY = 0.0F;
float accelZ = 0.0F;
uint8_t shakeCount = 0;
uint32_t shakeWindowStartedAt = 0;
uint32_t lastShakeAt = 0;
uint32_t lastClockRefreshAt = 0;
uint32_t lastInteractionAt = 0;
RtcTimestamp clockBaseTimestamp = {};
uint32_t clockBaseMillis = 0;
bool shakeAboveThreshold = false;
bool clockBaseValid = false;
Rating selectedRating = Rating::Forgot;
int lastSubmittedIndex = -1;
int returnAfterReRatingIndex = -1;
bool isReRating = false;
bool needsRender = true;
bool setupPortalActive = false;
bool powerOffStarted = false;
bool statusReturnsToClock = false;

static lv_disp_draw_buf_t lvDrawBuf;
static lv_color_t lvBuf1[240 * 16];
static lv_color_t lvBuf2[240 * 16];
static lv_disp_drv_t lvDispDrv;

lv_obj_t* clockScr = nullptr;
lv_obj_t* clockTime = nullptr;
lv_obj_t* clockTimeBold = nullptr;
lv_obj_t* clockColon = nullptr;
lv_obj_t* clockColonBold = nullptr;
lv_obj_t* clockMinute = nullptr;
lv_obj_t* clockMinuteBold = nullptr;
lv_obj_t* clockDayLabel = nullptr;
lv_obj_t* clockDayLabelBold = nullptr;
lv_obj_t* clockDateLabel = nullptr;
lv_obj_t* clockDueBg = nullptr;
lv_obj_t* clockDueText = nullptr;
lv_obj_t* clockBatArc = nullptr;
lv_obj_t* clockBatLabel = nullptr;
lv_obj_t* clockCheckMark = nullptr;
lv_obj_t* clockCheckCircle = nullptr;

void lvglFlushCb(lv_disp_drv_t* disp, const lv_area_t* area, lv_color_t* pixels) {
  const uint32_t w = area->x2 - area->x1 + 1;
  const uint32_t h = area->y2 - area->y1 + 1;
  M5.Display.startWrite();
  M5.Display.setSwapBytes(true);
  M5.Display.setAddrWindow(area->x1, area->y1, w, h);
  M5.Display.pushPixels(reinterpret_cast<uint16_t*>(pixels), w * h);
  M5.Display.endWrite();
  lv_disp_flush_ready(disp);
}

RtcTimestamp readRtcTimestamp();
bool isValidRtcTimestamp(const RtcTimestamp& timestamp);
RtcTimestamp currentClockTimestamp();
RtcTimestamp toClockDisplayTimestamp(const RtcTimestamp& timestamp);
String formatRtcTime(const RtcTimestamp& timestamp);
uint32_t idleTimeoutMs();
size_t activeCardCount();
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

float minFloat(float left, float right) {
  return left < right ? left : right;
}

float maxFloat(float left, float right) {
  return left > right ? left : right;
}

const char* pageName(Page page) {
  switch (page) {
    case Page::Status:
      return "status";
    case Page::Clock:
      return "clock";
    case Page::Word:
      return "word";
    case Page::Meaning:
      return "meaning";
    case Page::Example:
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

void resetShakeDetection() {
  shakeCount = 0;
  shakeWindowStartedAt = 0;
  shakeAboveThreshold = false;
}

void setPage(Page page) {
  currentPage = page;
  resetShakeDetection();
  needsRender = true;
  logPage();
}

bool isBreakChar(char value) {
  return value == ' ' || value == '\n' || value == '\r' || value == '\t';
}

size_t skipBreakChars(const char* text, size_t index) {
  while (text[index] != '\0' && isBreakChar(text[index])) {
    index += 1;
  }
  return index;
}

size_t nextTokenEnd(const char* text, size_t index) {
  while (text[index] != '\0' && !isBreakChar(text[index])) {
    index += 1;
  }
  return index;
}

int16_t textWidthSlice(const char* text, size_t start, size_t end) {
  String token = "";
  for (size_t i = start; i < end; ++i) {
    token += text[i];
  }
  return M5.Display.textWidth(token);
}

size_t fitLongTokenEnd(const char* text, size_t start, size_t end) {
  size_t cursor = start;
  int16_t cursorX = kContentX;
  int16_t cursorY = kContentY;

  while (cursor < end) {
    String character = "";
    character += text[cursor];
    const int16_t charWidth = M5.Display.textWidth(character);
    if (cursorX + charWidth > kContentMaxX) {
      cursorX = kContentX;
      cursorY += kContentLineHeight;
    }
    if (cursorY + kContentLineHeight > kContentMaxY) {
      return cursor > start ? cursor : cursor + 1;
    }
    cursorX += charWidth;
    cursor += 1;
  }
  return end;
}

size_t findNextContentPageStart(const char* text, size_t start) {
  M5.Display.setTextSize(kContentTextSize);
  const size_t length = std::strlen(text);
  size_t index = skipBreakChars(text, start);
  size_t lastFitEnd = index;
  int16_t cursorX = kContentX;
  int16_t cursorY = kContentY;

  while (index < length) {
    const size_t tokenStart = index;
    const size_t tokenEnd = nextTokenEnd(text, index);
    const int16_t tokenWidth = textWidthSlice(text, tokenStart, tokenEnd);
    const int16_t spaceWidth = cursorX == kContentX ? 0 : M5.Display.textWidth(" ");

    if (cursorX != kContentX && cursorX + spaceWidth + tokenWidth > kContentMaxX) {
      cursorX = kContentX;
      cursorY += kContentLineHeight;
    }
    if (cursorY + kContentLineHeight > kContentMaxY) {
      return tokenStart > start ? tokenStart : fitLongTokenEnd(text, tokenStart, tokenEnd);
    }

    if (tokenWidth > kContentMaxX - kContentX && cursorX == kContentX) {
      const size_t fittedEnd = fitLongTokenEnd(text, tokenStart, tokenEnd);
      if (fittedEnd < tokenEnd) {
        return fittedEnd;
      }
    }

    cursorX += spaceWidth + tokenWidth;
    lastFitEnd = tokenEnd;
    index = skipBreakChars(text, tokenEnd);
  }

  return lastFitEnd >= length ? length : skipBreakChars(text, lastFitEnd);
}

size_t findPreviousContentPageStart(const char* text, size_t start) {
  size_t previous = 0;
  size_t cursor = 0;

  while (cursor < start) {
    const size_t next = findNextContentPageStart(text, cursor);
    if (next >= start || next == cursor) {
      return previous;
    }
    previous = next;
    cursor = next;
  }

  return previous;
}

bool hasMoreContentPage(const char* text) {
  return findNextContentPageStart(text, contentPageStart) < std::strlen(text);
}

void setContentPage(Page page, size_t pageStart) {
  contentPageStart = pageStart;
  setPage(page);
}

size_t activeCardCount() {
  return syncedCardCount > kMaxSyncedCards ? kMaxSyncedCards : syncedCardCount;
}

const char* currentWordId() {
  return syncedCards[currentCardIndex].id;
}

Card currentCard() {
  return {
      syncedCards[currentCardIndex].word,
      syncedCards[currentCardIndex].meaning,
      syncedCards[currentCardIndex].example,
  };
}

void readImu() {
  M5.Imu.getAccel(&accelX, &accelY, &accelZ);
}

float accelMagnitude() {
  return std::sqrt(accelX * accelX + accelY * accelY + accelZ * accelZ);
}

uint8_t detectLandscapeRotation() {
  if (accelX > kOrientationThreshold) {
    return 1;
  }
  if (accelX < -kOrientationThreshold) {
    return 3;
  }
  return currentRotation;
}

void updateAutoRotation(uint32_t now) {
  const uint8_t detectedRotation = detectLandscapeRotation();

  if (detectedRotation == currentRotation) {
    pendingRotation = currentRotation;
    pendingRotationSince = now;
    return;
  }

  if (detectedRotation != pendingRotation) {
    pendingRotation = detectedRotation;
    pendingRotationSince = now;
    return;
  }

  if (now - pendingRotationSince < kOrientationStableMs) {
    return;
  }

  currentRotation = detectedRotation;
  M5.Display.setRotation(currentRotation);
  if (currentPage == Page::Clock) {
    if (clockScr != nullptr) {
      lv_obj_invalidate(clockScr);
    }
    lastClockRefreshAt = 0;
  }
  needsRender = true;
  Serial.printf("Orientation rotation=%u ax=%.2f ay=%.2f az=%.2f\n",
                static_cast<unsigned>(currentRotation), accelX, accelY, accelZ);
}

void drawCenteredText(const char* text, int16_t y, uint8_t textSize) {
  M5.Display.setTextSize(textSize);
  const int16_t textWidth = M5.Display.textWidth(text);
  const int16_t x = (240 - textWidth) / 2;
  M5.Display.setCursor(x < 0 ? 0 : x, y);
  M5.Display.println(text);
}

void copyStatusLine(char* dest, size_t destSize, const char* source) {
  if (destSize == 0) {
    return;
  }
  std::strncpy(dest, source, destSize - 1);
  dest[destSize - 1] = '\0';
}

void setStatusPage(const char* line1, const char* line2 = "", const char* line3 = "") {
  copyStatusLine(statusLine1, sizeof(statusLine1), line1);
  copyStatusLine(statusLine2, sizeof(statusLine2), line2);
  copyStatusLine(statusLine3, sizeof(statusLine3), line3);
  statusReturnsToClock = std::strcmp(line1, "No due cards") == 0;
  setPage(Page::Status);
}

void copyBounded(char* dest, size_t destSize, const String& value);
RtcTimestamp readRtcTimestamp();
bool isValidRtcTimestamp(const RtcTimestamp& timestamp);
RtcTimestamp toClockDisplayTimestamp(const RtcTimestamp& timestamp);
String formatRtcDate(const RtcTimestamp& timestamp);
String formatRtcTime(const RtcTimestamp& timestamp);

String normalizeServerUrl(const String& server) {
  String normalized = server;
  normalized.trim();
  while (normalized.endsWith("/") && std::strcmp(normalized.c_str(), "http://") != 0) {
    normalized.remove(normalized.length() - 1);
  }
  return normalized;
}

bool validateRuntimeConfig(const RuntimeConfig& config) {
  String ssid = String(config.ssid);
  ssid.trim();
  return ssid.length() > 0 &&
         std::strncmp(config.serverUrl, "http://", std::strlen("http://")) == 0 &&
         std::strlen(config.serverUrl) > std::strlen("http://");
}

bool loadRuntimeConfig() {
  storage.begin("stickwords", true);
  copyBounded(runtimeConfig.ssid, sizeof(runtimeConfig.ssid), storage.getString("cfg_ssid", ""));
  copyBounded(runtimeConfig.password, sizeof(runtimeConfig.password), storage.getString("cfg_pass", ""));
  copyBounded(
      runtimeConfig.serverUrl,
      sizeof(runtimeConfig.serverUrl),
      normalizeServerUrl(storage.getString("cfg_server", "")));
  storage.end();
  runtimeConfig.valid = validateRuntimeConfig(runtimeConfig);
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
  if (runtimeConfig.valid && validateRuntimeConfig(runtimeConfig)) {
    return String(runtimeConfig.serverUrl);
  }
  return normalizeServerUrl(String(STICKWORDS_SERVER_URL));
}

int weekdayIndex(uint16_t year, uint8_t month, uint8_t date) {
  static int offsets[] = {0, 3, 2, 5, 0, 3, 5, 1, 4, 6, 2, 4};
  int adjustedYear = year;
  if (month < 3) {
    adjustedYear -= 1;
  }
  return (adjustedYear + adjustedYear / 4 - adjustedYear / 100 +
          adjustedYear / 400 + offsets[month - 1] + date) %
         7;
}

lv_opa_t clockColonOpacity(uint32_t now) {
  const uint16_t phase = now % kClockColonPulseMs;
  const uint16_t halfPulse = kClockColonPulseMs / 2;
  const uint16_t rising = phase <= halfPulse ? phase : kClockColonPulseMs - phase;
  return static_cast<lv_opa_t>(
      kClockColonMinOpacity +
      (rising * (kClockColonMaxOpacity - kClockColonMinOpacity)) / halfPulse);
}

void createClockUI() {
  if (clockScr != nullptr) {
    return;
  }

  clockScr = lv_obj_create(nullptr);
  lv_obj_clear_flag(clockScr, LV_OBJ_FLAG_SCROLLABLE);
  lv_obj_set_style_bg_color(clockScr, lv_color_black(), 0);
  lv_obj_set_style_bg_opa(clockScr, LV_OPA_COVER, 0);
  lv_obj_set_style_pad_all(clockScr, 0, 0);

  clockCheckCircle = lv_obj_create(clockScr);
  lv_obj_remove_style_all(clockCheckCircle);
  lv_obj_set_size(clockCheckCircle, 14, 14);
  lv_obj_set_pos(clockCheckCircle, 10, 6);
  lv_obj_set_style_radius(clockCheckCircle, LV_RADIUS_CIRCLE, 0);
  lv_obj_set_style_bg_color(clockCheckCircle, lv_color_hex(0x22C55E), 0);
  lv_obj_set_style_bg_opa(clockCheckCircle, LV_OPA_TRANSP, 0);
  lv_obj_set_style_border_color(clockCheckCircle, lv_color_hex(0x22C55E), 0);
  lv_obj_set_style_border_width(clockCheckCircle, 2, 0);
  lv_obj_clear_flag(clockCheckCircle, LV_OBJ_FLAG_SCROLLABLE);

  clockCheckMark = lv_label_create(clockCheckCircle);
  lv_label_set_text(clockCheckMark, LV_SYMBOL_OK);
  lv_obj_set_style_text_color(clockCheckMark, lv_color_hex(0x22C55E), 0);
  lv_obj_set_style_text_font(clockCheckMark, &lv_font_montserrat_12, 0);
  lv_obj_center(clockCheckMark);

  clockDueBg = lv_obj_create(clockScr);
  lv_obj_set_size(clockDueBg, 70, 22);
  lv_obj_align(clockDueBg, LV_ALIGN_TOP_RIGHT, -10, 6);
  lv_obj_set_style_radius(clockDueBg, 11, 0);
  lv_obj_set_style_bg_color(clockDueBg, lv_color_hex(0xEF4444), 0);
  lv_obj_set_style_bg_opa(clockDueBg, LV_OPA_COVER, 0);
  lv_obj_set_style_border_width(clockDueBg, 0, 0);
  lv_obj_set_style_pad_all(clockDueBg, 0, 0);
  lv_obj_clear_flag(clockDueBg, LV_OBJ_FLAG_SCROLLABLE);

  clockDueText = lv_label_create(clockDueBg);
  lv_obj_set_style_text_color(clockDueText, lv_color_white(), 0);
  lv_obj_set_style_text_font(clockDueText, &lv_font_montserrat_14, 0);
  lv_obj_center(clockDueText);

  clockTime = lv_label_create(clockScr);
  lv_obj_set_pos(clockTime, 10, 34);
  lv_obj_set_style_text_font(clockTime, &lv_font_montserrat_48, 0);
  lv_obj_set_style_text_color(clockTime, lv_color_white(), 0);

  clockTimeBold = lv_label_create(clockScr);
  lv_obj_set_pos(clockTimeBold, 11, 34);
  lv_obj_set_style_text_font(clockTimeBold, &lv_font_montserrat_48, 0);
  lv_obj_set_style_text_color(clockTimeBold, lv_color_white(), 0);

  clockColon = lv_label_create(clockScr);
  lv_label_set_text(clockColon, ":");
  lv_obj_set_pos(clockColon, 74, 34);
  lv_obj_set_style_text_font(clockColon, &lv_font_montserrat_48, 0);
  lv_obj_set_style_text_color(clockColon, lv_color_hex(0x8F839D), 0);

  clockColonBold = lv_label_create(clockScr);
  lv_label_set_text(clockColonBold, ":");
  lv_obj_set_pos(clockColonBold, 75, 34);
  lv_obj_set_style_text_font(clockColonBold, &lv_font_montserrat_48, 0);
  lv_obj_set_style_text_color(clockColonBold, lv_color_hex(0x8F839D), 0);

  clockMinute = lv_label_create(clockScr);
  lv_obj_set_pos(clockMinute, 95, 34);
  lv_obj_set_style_text_font(clockMinute, &lv_font_montserrat_48, 0);
  lv_obj_set_style_text_color(clockMinute, lv_color_white(), 0);

  clockMinuteBold = lv_label_create(clockScr);
  lv_obj_set_pos(clockMinuteBold, 96, 34);
  lv_obj_set_style_text_font(clockMinuteBold, &lv_font_montserrat_48, 0);
  lv_obj_set_style_text_color(clockMinuteBold, lv_color_white(), 0);

  clockDayLabel = lv_label_create(clockScr);
  lv_obj_set_pos(clockDayLabel, 10, 90);
  lv_obj_set_style_text_font(clockDayLabel, &lv_font_montserrat_24, 0);
  lv_obj_set_style_text_color(clockDayLabel, lv_color_hex(0xEF4444), 0);

  clockDayLabelBold = lv_label_create(clockScr);
  lv_obj_set_pos(clockDayLabelBold, 11, 90);
  lv_obj_set_style_text_font(clockDayLabelBold, &lv_font_montserrat_24, 0);
  lv_obj_set_style_text_color(clockDayLabelBold, lv_color_hex(0xEF4444), 0);

  clockDateLabel = lv_label_create(clockScr);
  lv_obj_set_pos(clockDateLabel, 70, 90);
  lv_obj_set_style_text_font(clockDateLabel, &lv_font_montserrat_24, 0);
  lv_obj_set_style_text_color(clockDateLabel, lv_color_white(), 0);

  clockBatArc = lv_arc_create(clockScr);
  lv_obj_set_size(clockBatArc, 56, 56);
  lv_obj_align(clockBatArc, LV_ALIGN_RIGHT_MID, -12, 8);
  lv_arc_set_rotation(clockBatArc, 270);
  lv_arc_set_bg_angles(clockBatArc, 0, 360);
  lv_arc_set_range(clockBatArc, 0, 100);
  lv_obj_set_style_arc_color(clockBatArc, lv_color_hex(0x333333), LV_PART_MAIN);
  lv_obj_set_style_arc_width(clockBatArc, 4, LV_PART_MAIN);
  lv_obj_set_style_arc_color(clockBatArc, lv_color_hex(0x22C55E), LV_PART_INDICATOR);
  lv_obj_set_style_arc_width(clockBatArc, 4, LV_PART_INDICATOR);
  lv_obj_set_style_arc_rounded(clockBatArc, true, 0);
  lv_obj_remove_style(clockBatArc, nullptr, LV_PART_KNOB);
  lv_obj_clear_flag(clockBatArc, LV_OBJ_FLAG_CLICKABLE);

  clockBatLabel = lv_label_create(clockScr);
  lv_obj_set_style_text_font(clockBatLabel, &lv_font_montserrat_18, 0);
  lv_obj_set_style_text_color(clockBatLabel, lv_color_white(), 0);
  lv_obj_align_to(clockBatLabel, clockBatArc, LV_ALIGN_CENTER, 0, 0);

  lv_scr_load(clockScr);
}

void updateClockUI() {
  if (clockScr == nullptr) {
    createClockUI();
  }

  const RtcTimestamp timestamp = currentClockTimestamp();
  if (!isValidRtcTimestamp(timestamp)) {
    lv_label_set_text(clockTime, "RTC invalid");
    lv_label_set_text(clockTimeBold, "RTC invalid");
    lv_label_set_text(clockColon, "");
    lv_label_set_text(clockColonBold, "");
    lv_label_set_text(clockMinute, "");
    lv_label_set_text(clockMinuteBold, "");
    lv_label_set_text(clockDayLabel, "Sync needed");
    lv_label_set_text(clockDayLabelBold, "Sync needed");
    lv_label_set_text(clockDateLabel, "");
    lv_label_set_text(clockDueText, "DUE0");
    lv_obj_center(clockDueText);
    lv_arc_set_value(clockBatArc, 0);
    lv_label_set_text(clockBatLabel, "0");
    lv_obj_align_to(clockBatLabel, clockBatArc, LV_ALIGN_CENTER, 0, 0);
    return;
  }

  const RtcTimestamp display = toClockDisplayTimestamp(timestamp);
  char hourBuffer[3];
  char minuteBuffer[3];
  std::snprintf(hourBuffer, sizeof(hourBuffer), "%02u", static_cast<unsigned>(display.hour));
  std::snprintf(minuteBuffer, sizeof(minuteBuffer), "%02u", static_cast<unsigned>(display.minute));
  lv_label_set_text(clockTime, hourBuffer);
  lv_label_set_text(clockTimeBold, hourBuffer);
  lv_label_set_text(clockColon, ":");
  lv_label_set_text(clockColonBold, ":");
  const lv_opa_t colonOpacity = clockColonOpacity(millis());
  lv_obj_set_style_text_opa(clockColon, colonOpacity, 0);
  lv_obj_set_style_text_opa(clockColonBold, colonOpacity, 0);
  lv_label_set_text(clockMinute, minuteBuffer);
  lv_label_set_text(clockMinuteBold, minuteBuffer);

  static const char* weekdays[] = {"SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"};
  lv_label_set_text(clockDayLabel, weekdays[weekdayIndex(display.year, display.month, display.date)]);
  lv_label_set_text(clockDayLabelBold, weekdays[weekdayIndex(display.year, display.month, display.date)]);

  char dateBuffer[4];
  std::snprintf(dateBuffer, sizeof(dateBuffer), "%u", static_cast<unsigned>(display.date));
  lv_label_set_text(clockDateLabel, dateBuffer);

  char dueBuffer[8];
  std::snprintf(dueBuffer, sizeof(dueBuffer), "DUE %u", static_cast<unsigned>(activeCardCount()));
  lv_label_set_text(clockDueText, dueBuffer);
  lv_obj_center(clockDueText);

  std::int32_t batteryLevel = M5.Power.getBatteryLevel();
  if (batteryLevel < 0) {
    batteryLevel = 0;
  }
  if (batteryLevel > 100) {
    batteryLevel = 100;
  }
  lv_arc_set_value(clockBatArc, static_cast<int16_t>(batteryLevel));

  lv_color_t batteryColor = lv_color_hex(0xEF4444);
  if (batteryLevel > 50) {
    batteryColor = lv_color_hex(0x22C55E);
  } else if (batteryLevel > 20) {
    batteryColor = lv_color_hex(0xEAB308);
  }
  lv_obj_set_style_arc_color(clockBatArc, batteryColor, LV_PART_INDICATOR);

  char batteryBuffer[8];
  std::snprintf(batteryBuffer, sizeof(batteryBuffer), "%d", static_cast<int>(batteryLevel));
  lv_label_set_text(clockBatLabel, batteryBuffer);
  lv_obj_align_to(clockBatLabel, clockBatArc, LV_ALIGN_CENTER, 0, 0);
}

void drawStatusPage() {
  M5.Display.setCursor(8, 36);
  M5.Display.setTextSize(2);
  M5.Display.println(statusLine1);
  if (statusLine2[0] != '\0') {
    M5.Display.println(statusLine2);
  }
  if (statusLine3[0] != '\0') {
    M5.Display.println(statusLine3);
  }
}

void drawClockPage() {
  updateClockUI();
  if (clockScr != nullptr) {
    lv_obj_invalidate(clockScr);
  }
  lv_timer_handler();
  lv_refr_now(nullptr);
}

void drawWordPage() {
  const Card card = currentCard();
  drawCenteredText(card.word, 52, 3);
}

void drawWrappedContentPage(const char* text) {
  M5.Display.setTextSize(kContentTextSize);
  size_t index = skipBreakChars(text, contentPageStart);
  size_t lastDrawnEnd = index;
  int16_t cursorX = kContentX;
  int16_t cursorY = kContentY;

  while (text[index] != '\0') {
    const size_t tokenStart = index;
    const size_t tokenEnd = nextTokenEnd(text, index);
    const int16_t tokenWidth = textWidthSlice(text, tokenStart, tokenEnd);
    const int16_t spaceWidth = cursorX == kContentX ? 0 : M5.Display.textWidth(" ");

    if (cursorX != kContentX && cursorX + spaceWidth + tokenWidth > kContentMaxX) {
      cursorX = kContentX;
      cursorY += kContentLineHeight;
    }
    if (cursorY + kContentLineHeight > kContentMaxY) {
      break;
    }

    M5.Display.setCursor(cursorX, cursorY);
    if (cursorX != kContentX) {
      M5.Display.print(" ");
      cursorX += spaceWidth;
    }

    if (tokenWidth > kContentMaxX - kContentX && cursorX == kContentX) {
      size_t charIndex = tokenStart;
      while (charIndex < tokenEnd) {
        String character = "";
        character += text[charIndex];
        const int16_t charWidth = M5.Display.textWidth(character);
        if (cursorX + charWidth > kContentMaxX) {
          cursorX = kContentX;
          cursorY += kContentLineHeight;
          if (cursorY + kContentLineHeight > kContentMaxY) {
            index = charIndex;
            break;
          }
          M5.Display.setCursor(cursorX, cursorY);
        }
        M5.Display.print(character);
        cursorX += charWidth;
        charIndex += 1;
        lastDrawnEnd = charIndex;
      }
      if (lastDrawnEnd < tokenEnd) {
        break;
      }
    } else {
      for (size_t i = tokenStart; i < tokenEnd; ++i) {
        M5.Display.print(text[i]);
      }
      cursorX += tokenWidth;
      lastDrawnEnd = tokenEnd;
    }

    index = skipBreakChars(text, tokenEnd);
  }

  if (findNextContentPageStart(text, contentPageStart) < std::strlen(text)) {
    M5.Display.setCursor(kContentMaxX - M5.Display.textWidth("..."), kContentMaxY - kContentLineHeight);
    M5.Display.print("...");
  }
}

void drawMeaningPage() {
  const Card card = currentCard();
  drawWrappedContentPage(card.meaning);
}

void drawExamplePage() {
  const Card card = currentCard();
  drawWrappedContentPage(card.example);
}

void drawRatingOption(Rating rating) {
  M5.Display.printf("%c %s\n", rating == selectedRating ? '>' : ' ', ratingName(rating));
}

void drawRatingPage() {
  const Card card = currentCard();
  M5.Display.setTextSize(2);
  M5.Display.print(card.word);
  M5.Display.println();
  M5.Display.println();
  drawRatingOption(Rating::Forgot);
  drawRatingOption(Rating::Hard);
  drawRatingOption(Rating::Good);
}

void drawDonePage() {
  drawCenteredText("Review complete", 38, 2);
  M5.Display.setTextSize(2);
  M5.Display.setCursor(74, 76);
  M5.Display.printf("%u/%u rated", static_cast<unsigned>(activeCardCount()),
                static_cast<unsigned>(activeCardCount()));
}

void render() {
  if (!needsRender) {
    return;
  }

  needsRender = false;
  if (currentPage == Page::Clock) {
    drawClockPage();
    return;
  }

  M5.Display.fillScreen(BLACK);
  M5.Display.setCursor(8, 8);
  M5.Display.setTextColor(WHITE, BLACK);
  M5.Display.setTextSize(1);

  switch (currentPage) {
    case Page::Status:
      drawStatusPage();
      break;
    case Page::Clock:
      drawClockPage();
      break;
    case Page::Word:
      drawWordPage();
      break;
    case Page::Meaning:
      drawMeaningPage();
      break;
    case Page::Example:
      drawExamplePage();
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

void resetReviewSet();

void copyLegacyCard(DeviceCard* card, const LegacyDeviceCard& legacy, const String& generatedAt) {
  copyBounded(card->id, sizeof(card->id), String(legacy.id));
  copyBounded(card->word, sizeof(card->word), String(legacy.word));
  copyBounded(card->meaning, sizeof(card->meaning), String(legacy.meaning));
  copyBounded(card->example, sizeof(card->example), String(legacy.example));
  copyBounded(card->status, sizeof(card->status), "review");
  copyBounded(card->dueAt, sizeof(card->dueAt), generatedAt);
  card->reviewCount = 0;
  card->ease = 2.5F;
  card->intervalDays = 0;
  card->lapses = 0;
}

void saveCachedTasks() {
  if (!cacheStorage.begin("stickcache", false, "cache")) {
    Serial.println("Cache storage open failed");
    return;
  }
  cacheStorage.remove("card_count");
  cacheStorage.remove("offline_count");
  cacheStorage.remove("cards");
  cacheStorage.remove("offline");
  cacheStorage.putString("generated", serverGeneratedAt);
  const size_t expectedCardBytes = sizeof(DeviceCard) * syncedCardCount;
  const size_t savedCardBytes = syncedCardCount == 0
                                    ? 0
                                    : cacheStorage.putBytes("cards", syncedCards, expectedCardBytes);
  const size_t expectedOfflineBytes = sizeof(DeviceCard) * offlineCardCount;
  const size_t savedOfflineBytes = offlineCardCount == 0
                                       ? 0
                                       : cacheStorage.putBytes("offline", offlineCards, expectedOfflineBytes);
  const size_t savedCardCount = savedCardBytes == expectedCardBytes ? syncedCardCount : 0;
  const size_t savedOfflineCount = savedOfflineBytes == expectedOfflineBytes ? offlineCardCount : 0;
  cacheStorage.putUInt("card_count", static_cast<uint32_t>(savedCardCount));
  cacheStorage.putUInt("offline_count", static_cast<uint32_t>(savedOfflineCount));
  cacheStorage.end();
  Serial.printf("Cached cards=%u offline=%u\n", static_cast<unsigned>(savedCardCount),
                static_cast<unsigned>(savedOfflineCount));
}

bool readCachedTasksFromStorage(Preferences& prefs, bool allowLegacyCards) {
  uint32_t storedCount = prefs.getUInt("card_count", 0);
  if (storedCount > kMaxSyncedCards) {
    storedCount = kMaxSyncedCards;
  }

  uint32_t storedOfflineCount = prefs.getUInt("offline_count", 0);
  if (storedOfflineCount > kMaxOfflineCards) {
    storedOfflineCount = kMaxOfflineCards;
  }
  const size_t cardBytesLength = storedCount == 0 ? 0 : prefs.getBytesLength("cards");
  const size_t expectedBytes = sizeof(DeviceCard) * storedCount;
  const size_t expectedLegacyBytes = sizeof(LegacyDeviceCard) * storedCount;
  const size_t readBytes = storedCount == 0 || cardBytesLength != expectedBytes
                               ? 0
                               : prefs.getBytes("cards", syncedCards, expectedBytes);
  const size_t expectedOfflineBytes = sizeof(DeviceCard) * storedOfflineCount;
  const size_t readOfflineBytes = storedOfflineCount == 0
                                      ? 0
                                      : prefs.getBytes("offline", offlineCards, expectedOfflineBytes);
  const String generatedAt = prefs.getString("generated", "");

  if (storedCount == 0 && storedOfflineCount == 0) {
    return false;
  }
  if (allowLegacyCards && storedCount > 0 && cardBytesLength == expectedLegacyBytes) {
    LegacyDeviceCard* legacyCards =
        static_cast<LegacyDeviceCard*>(malloc(expectedLegacyBytes));
    if (legacyCards == nullptr ||
        prefs.getBytes("cards", legacyCards, expectedLegacyBytes) != expectedLegacyBytes) {
      free(legacyCards);
      return false;
    }
    for (size_t i = 0; i < storedCount; ++i) {
      copyLegacyCard(&syncedCards[i], legacyCards[i], generatedAt);
    }
    free(legacyCards);
  } else if (storedCount > 0 && readBytes != expectedBytes) {
    return false;
  }
  if (storedOfflineCount > 0 && readOfflineBytes != expectedOfflineBytes) {
    return false;
  }

  syncedCardCount = storedCount;
  offlineCardCount = storedOfflineCount;
  if (offlineCardCount == 0) {
    for (size_t i = 0; i < syncedCardCount && i < kMaxOfflineCards; ++i) {
      offlineCards[i] = syncedCards[i];
      offlineCardCount += 1;
    }
  }
  copyBounded(serverGeneratedAt, sizeof(serverGeneratedAt), generatedAt);
  Serial.printf("Loaded cached cards=%u\n", static_cast<unsigned>(syncedCardCount));
  resetReviewSet();
  return true;
}

bool loadCachedTasks() {
  if (cacheStorage.begin("stickcache", true, "cache")) {
    const bool loaded = readCachedTasksFromStorage(cacheStorage, false);
    cacheStorage.end();
    if (loaded) {
      return true;
    }
  }

  storage.begin("stickwords", true);
  const bool loadedLegacy = readCachedTasksFromStorage(storage, true);
  storage.end();
  if (loadedLegacy) {
    saveCachedTasks();
  }
  return loadedLegacy;
}

void clearCachedTasks() {
  if (!cacheStorage.begin("stickcache", false, "cache")) {
    return;
  }
  cacheStorage.remove("card_count");
  cacheStorage.remove("generated");
  cacheStorage.remove("cards");
  cacheStorage.remove("offline_count");
  cacheStorage.remove("offline");
  cacheStorage.end();
}

void savePendingReviews() {
  storage.begin("stickwords", false);
  storage.putUInt("pending_count", static_cast<uint32_t>(pendingReviewCount));
  storage.putUInt("review_seq", reviewSequence);
  storage.putBytes("pending", pendingReviews, sizeof(PendingReview) * pendingReviewCount);
  storage.end();
  Serial.printf("Saved pending reviews=%u\n", static_cast<unsigned>(pendingReviewCount));
}

bool loadPendingReviews() {
  storage.begin("stickwords", true);
  uint32_t storedCount = storage.getUInt("pending_count", 0);
  if (storedCount > kMaxPendingReviews) {
    storedCount = kMaxPendingReviews;
  }

  const size_t expectedBytes = sizeof(PendingReview) * storedCount;
  const size_t storedBytes = storedCount == 0 ? 0 : storage.getBytesLength("pending");
  size_t readBytes = 0;
  bool loadedLegacy = false;
  if (storedCount > 0 && storedBytes == expectedBytes) {
    readBytes = storage.getBytes("pending", pendingReviews, expectedBytes);
  } else if (storedCount > 0 &&
             storedBytes == sizeof(LegacyPendingReview) * storedCount) {
    LegacyPendingReview legacyPending[kMaxPendingReviews] = {};
    readBytes = storage.getBytes("pending", legacyPending, storedBytes);
    if (readBytes == storedBytes) {
      for (size_t i = 0; i < storedCount; ++i) {
        copyBounded(pendingReviews[i].wordId, sizeof(pendingReviews[i].wordId),
                    String(legacyPending[i].wordId));
        pendingReviews[i].rating = legacyPending[i].rating;
        copyBounded(pendingReviews[i].reviewedAt, sizeof(pendingReviews[i].reviewedAt),
                    String("1970-01-01T00:00:00Z"));
        pendingReviews[i].sequence = legacyPending[i].sequence;
        pendingReviews[i].uploaded = legacyPending[i].uploaded;
      }
      loadedLegacy = true;
    }
  }
  const uint32_t storedSequence = storage.getUInt("review_seq", 0);
  storage.end();

  if (storedCount > 0 && !loadedLegacy && readBytes != expectedBytes) {
    pendingReviewCount = 0;
    return false;
  }

  pendingReviewCount = storedCount;
  if (storedSequence > reviewSequence) {
    reviewSequence = storedSequence;
  }
  Serial.printf("Loaded pending reviews=%u\n", static_cast<unsigned>(pendingReviewCount));
  return pendingReviewCount > 0;
}

void clearPendingReviews() {
  storage.begin("stickwords", false);
  storage.remove("pending_count");
  storage.remove("review_seq");
  storage.remove("pending");
  storage.end();
}

void drawStatusMessage(const char* line1, const char* line2 = "", const char* line3 = "") {
  M5.Display.fillScreen(BLACK);
  M5.Display.setCursor(8, 36);
  M5.Display.setTextColor(WHITE, BLACK);
  M5.Display.setTextSize(2);
  M5.Display.println(line1);
  if (line2[0] != '\0') {
    M5.Display.println(line2);
  }
  if (line3[0] != '\0') {
    M5.Display.println(line3);
  }
}

String htmlEscape(const String& value) {
  String escaped = "";
  for (int i = 0; i < value.length(); ++i) {
    const char current = value[i];
    if (current == '&') {
      escaped += "&amp;";
    } else if (current == '<') {
      escaped += "&lt;";
    } else if (current == '>') {
      escaped += "&gt;";
    } else if (current == '"') {
      escaped += "&quot;";
    } else if (current == '\'') {
      escaped += "&#39;";
    } else {
      escaped += current;
    }
  }
  return escaped;
}

String setupPageHtml(const String& message = "") {
  String body = "<!doctype html><html><head><meta name='viewport' "
                "content='width=device-width,initial-scale=1'><title>StickWords Setup</title>"
                "</head><body><h1>StickWords Setup</h1><form method='post' action='/save'>";
  if (message.length() > 0) {
    body += "<p>";
    body += htmlEscape(message);
    body += "</p>";
  }
  body += "<label>SSID <input name='ssid' value='" + htmlEscape(String(runtimeConfig.ssid)) + "'></label><br>";
  body += "<label>Password <input name='password' type='password' ";
  body += "placeholder='leave blank to keep current password'></label><br>";
  body += "<label>Server <input name='server' value='" + htmlEscape(String(runtimeConfig.serverUrl)) + "'></label><br>";
  body += "<button type='submit'>Save</button></form></body></html>";
  return body;
}

void handleSetupRoot() {
  setupServer.send(200, "text/html", setupPageHtml());
}

void handleCaptivePortal() {
  setupServer.sendHeader("Location", "http://192.168.4.1/", true);
  setupServer.send(302, "text/plain", "");
}

void handleSetupSave() {
  RuntimeConfig submitted = {};
  String ssid = setupServer.arg("ssid");
  ssid.trim();
  copyBounded(submitted.ssid, sizeof(submitted.ssid), ssid);
  copyBounded(submitted.password, sizeof(submitted.password), setupServer.arg("password"));
  if (submitted.password[0] == '\0' && runtimeConfig.valid) {
    copyBounded(submitted.password, sizeof(submitted.password), String(runtimeConfig.password));
  }
  copyBounded(
      submitted.serverUrl,
      sizeof(submitted.serverUrl),
      normalizeServerUrl(setupServer.arg("server")));
  submitted.valid = validateRuntimeConfig(submitted);

  if (!submitted.valid) {
    setupServer.send(400, "text/html",
                     setupPageHtml("SSID is required and server URL must start with http://"));
    return;
  }

  runtimeConfig = submitted;
  saveRuntimeConfig(runtimeConfig);
  drawStatusMessage("Saved", "restarting");
  setupServer.send(200, "text/html", setupPageHtml("Saved, restarting"));
  delay(300);
  ESP.restart();
}

void startSetupPortal() {
  WiFi.mode(WIFI_AP);
  if (!WiFi.softAP("StickWords-Setup")) {
    Serial.println("Setup portal AP failed");
    setStatusPage("Setup failed", "check serial");
    drawStatusMessage("Setup failed", "check serial");
    return;
  }

  setupPortalActive = true;
  dnsServer.start(53, "*", WiFi.softAPIP());
  setupServer.on("/", HTTP_GET, handleSetupRoot);
  setupServer.on("/save", HTTP_POST, handleSetupSave);
  setupServer.on("/generate_204", HTTP_GET, handleCaptivePortal);
  setupServer.on("/gen_204", HTTP_GET, handleCaptivePortal);
  setupServer.on("/hotspot-detect.html", HTTP_GET, handleCaptivePortal);
  setupServer.on("/library/test/success.html", HTTP_GET, handleCaptivePortal);
  setupServer.on("/fwlink", HTTP_GET, handleCaptivePortal);
  setupServer.onNotFound(handleCaptivePortal);
  setupServer.begin();
  Serial.print("Setup portal ip=");
  Serial.println(WiFi.softAPIP());
  setStatusPage("Setup mode", "WiFi: StickWords-Setup", "Open: 192.168.4.1");
  drawStatusMessage("Setup mode", "WiFi: StickWords-Setup", "Open: 192.168.4.1");
}

void handleSetupPortalLoop() {
  dnsServer.processNextRequest();
  setupServer.handleClient();
}

bool connectWifi() {
  drawStatusMessage("WiFi...");
  WiFi.mode(WIFI_STA);
  WiFi.begin(runtimeConfig.ssid, runtimeConfig.password);

  const uint32_t startedAt = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - startedAt < 12000) {
    delay(250);
    M5.update();
  }

  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi failed");
    drawStatusMessage("WiFi failed", "check network");
    setStatusPage("WiFi failed", "check network");
    return false;
  }

  Serial.print("WiFi connected ip=");
  Serial.println(WiFi.localIP());
  return true;
}

void copyBounded(char* dest, size_t destSize, const String& value) {
  if (destSize == 0) {
    return;
  }
  value.substring(0, destSize - 1).toCharArray(dest, destSize);
}

String parseJsonStringAt(const String& source, int quoteIndex, int* nextIndex = nullptr) {
  String value = "";
  bool escaped = false;
  for (int i = quoteIndex + 1; i < source.length(); ++i) {
    const char current = source[i];
    if (escaped) {
      if (current == 'n') {
        value += '\n';
      } else if (current == 'r') {
        value += '\r';
      } else if (current == 't') {
        value += '\t';
      } else {
        value += current;
      }
      escaped = false;
      continue;
    }
    if (current == '\\') {
      escaped = true;
      continue;
    }
    if (current == '"') {
      if (nextIndex != nullptr) {
        *nextIndex = i + 1;
      }
      return value;
    }
    value += current;
  }
  return "";
}

String jsonStringValue(const String& object, const char* key) {
  const String marker = String("\"") + key + "\":";
  const int markerIndex = object.indexOf(marker);
  if (markerIndex < 0) {
    return "";
  }
  const int start = object.indexOf('"', markerIndex + marker.length());
  if (start < 0) {
    return "";
  }
  return parseJsonStringAt(object, start);
}

int jsonIntValue(const String& object, const char* key, int fallback = 0) {
  const String marker = String("\"") + key + "\":";
  const int markerIndex = object.indexOf(marker);
  if (markerIndex < 0) {
    return fallback;
  }
  int cursor = markerIndex + marker.length();
  while (cursor < object.length() && (object[cursor] == ' ' || object[cursor] == '\t')) {
    cursor += 1;
  }
  int sign = 1;
  if (cursor < object.length() && object[cursor] == '-') {
    sign = -1;
    cursor += 1;
  }
  int value = 0;
  bool hasDigit = false;
  while (cursor < object.length() && object[cursor] >= '0' && object[cursor] <= '9') {
    hasDigit = true;
    value = value * 10 + (object[cursor] - '0');
    cursor += 1;
  }
  return hasDigit ? value * sign : fallback;
}

float jsonFloatValue(const String& object, const char* key, float fallback = 0.0F) {
  const String marker = String("\"") + key + "\":";
  const int markerIndex = object.indexOf(marker);
  if (markerIndex < 0) {
    return fallback;
  }
  int cursor = markerIndex + marker.length();
  while (cursor < object.length() && (object[cursor] == ' ' || object[cursor] == '\t')) {
    cursor += 1;
  }
  return object.substring(cursor).toFloat();
}

int findJsonArrayEnd(const String& body, int arrayStart) {
  bool inString = false;
  bool escaped = false;
  int depth = 0;
  for (int i = arrayStart; i < body.length(); ++i) {
    const char current = body[i];
    if (inString) {
      if (escaped) {
        escaped = false;
      } else if (current == '\\') {
        escaped = true;
      } else if (current == '"') {
        inString = false;
      }
      continue;
    }
    if (current == '"') {
      inString = true;
    } else if (current == '[') {
      depth += 1;
    } else if (current == ']') {
      depth -= 1;
      if (depth == 0) {
        return i;
      }
    }
  }
  return -1;
}

int findJsonObjectEnd(const String& body, int objectStart, int limit) {
  bool inString = false;
  bool escaped = false;
  int depth = 0;
  for (int i = objectStart; i <= limit && i < body.length(); ++i) {
    const char current = body[i];
    if (inString) {
      if (escaped) {
        escaped = false;
      } else if (current == '\\') {
        escaped = true;
      } else if (current == '"') {
        inString = false;
      }
      continue;
    }
    if (current == '"') {
      inString = true;
    } else if (current == '{') {
      depth += 1;
    } else if (current == '}') {
      depth -= 1;
      if (depth == 0) {
        return i;
      }
    }
  }
  return -1;
}

CardArrayParseResult parseCardArrayJson(const String& body, const char* arrayKey,
                                        DeviceCard* cards, size_t maxCards) {
  const String keyMarker = String("\"") + arrayKey + "\"";
  const int keyIndex = body.indexOf(keyMarker);
  if (keyIndex < 0) {
    return {false, 0};
  }
  const int arrayStart = body.indexOf('[', keyIndex);
  if (arrayStart < 0) {
    return {false, 0};
  }
  const int arrayEnd = findJsonArrayEnd(body, arrayStart);
  if (arrayEnd < 0) {
    return {false, 0};
  }

  size_t cardCount = 0;
  int cursor = arrayStart;
  while (cardCount < maxCards) {
    const int objectStart = body.indexOf('{', cursor);
    if (objectStart < 0 || objectStart > arrayEnd) {
      break;
    }
    const int objectEnd = findJsonObjectEnd(body, objectStart, arrayEnd);
    if (objectEnd < 0 || objectEnd > arrayEnd) {
      return {false, 0};
    }

    const String object = body.substring(objectStart, objectEnd + 1);
    DeviceCard& card = cards[cardCount];
    copyBounded(card.id, sizeof(card.id), jsonStringValue(object, "id"));
    copyBounded(card.word, sizeof(card.word), jsonStringValue(object, "word"));
    copyBounded(card.meaning, sizeof(card.meaning), jsonStringValue(object, "meaning"));
    copyBounded(card.example, sizeof(card.example), jsonStringValue(object, "example"));
    copyBounded(card.status, sizeof(card.status), jsonStringValue(object, "status"));
    copyBounded(card.dueAt, sizeof(card.dueAt), jsonStringValue(object, "due_at"));
    card.reviewCount = static_cast<uint16_t>(jsonIntValue(object, "review_count", 0));
    card.ease = jsonFloatValue(object, "ease", 2.5F);
    card.intervalDays = static_cast<int16_t>(jsonIntValue(object, "interval_days", 0));
    card.lapses = static_cast<uint16_t>(jsonIntValue(object, "lapses", 0));
    if (card.id[0] != '\0' && card.word[0] != '\0') {
      cardCount += 1;
    }
    cursor = objectEnd + 1;
  }

  return {true, cardCount};
}

bool parseDeviceTasksJson(const String& body) {
  syncedCardCount = 0;
  offlineCardCount = 0;
  copyBounded(serverGeneratedAt, sizeof(serverGeneratedAt), jsonStringValue(body, "generated_at"));
  const CardArrayParseResult tasksResult =
      parseCardArrayJson(body, "tasks", syncedCards, kMaxImmediateCards);
  if (!tasksResult.valid) {
    return false;
  }
  syncedCardCount = tasksResult.count;
  const int offlineStart = body.indexOf("\"offline\"");
  if (offlineStart >= 0) {
    const CardArrayParseResult offlineResult =
        parseCardArrayJson(body.substring(offlineStart), "cards", offlineCards, kMaxOfflineCards);
    if (!offlineResult.valid) {
      return false;
    }
    offlineCardCount = offlineResult.count;
  }
  if (offlineCardCount == 0 && syncedCardCount > 0) {
    for (size_t i = 0; i < syncedCardCount && i < kMaxOfflineCards; ++i) {
      offlineCards[i] = syncedCards[i];
      offlineCardCount += 1;
    }
  }

  // Metadata parsed by parseCardArrayJson: jsonStringValue(object, "status"),
  // jsonStringValue(object, "due_at"), jsonIntValue(object, "review_count", 0),
  // jsonFloatValue(object, "ease", 2.5F), jsonIntValue(object, "interval_days", 0),
  // jsonIntValue(object, "lapses", 0), "offline", "cards".
  return true;
}

int twoDigitsAt(const String& value, int index) {
  if (index + 1 >= value.length() ||
      value[index] < '0' || value[index] > '9' ||
      value[index + 1] < '0' || value[index + 1] > '9') {
    return -1;
  }
  return (value[index] - '0') * 10 + (value[index + 1] - '0');
}

bool isLeapYear(uint16_t year) {
  return year % 400 == 0 || (year % 4 == 0 && year % 100 != 0);
}

uint8_t daysInMonth(uint16_t year, uint8_t month) {
  switch (month) {
    case 2:
      return isLeapYear(year) ? 29 : 28;
    case 4:
    case 6:
    case 9:
    case 11:
      return 30;
    case 1:
    case 3:
    case 5:
    case 7:
    case 8:
    case 10:
    case 12:
      return 31;
  }
  return 0;
}

bool isValidRtcTimestamp(const RtcTimestamp& timestamp) {
  return timestamp.year >= 2024 &&
         timestamp.month >= 1 && timestamp.month <= 12 &&
         timestamp.date >= 1 &&
         timestamp.date <= daysInMonth(timestamp.year, timestamp.month) &&
         timestamp.hour <= 23 &&
         timestamp.minute <= 59 &&
         timestamp.second <= 59;
}

bool parseUtcTimestamp(const String& value, RtcTimestamp* timestamp) {
  if (timestamp == nullptr || value.length() != 20 ||
      value[4] != '-' || value[7] != '-' || value[10] != 'T' ||
      value[13] != ':' || value[16] != ':' || value[19] != 'Z') {
    return false;
  }
  const int yearHigh = twoDigitsAt(value, 0);
  const int yearLow = twoDigitsAt(value, 2);
  const int month = twoDigitsAt(value, 5);
  const int date = twoDigitsAt(value, 8);
  const int hour = twoDigitsAt(value, 11);
  const int minute = twoDigitsAt(value, 14);
  const int second = twoDigitsAt(value, 17);
  if (yearHigh < 0 || yearLow < 0 || month < 0 || date < 0 ||
      hour < 0 || minute < 0 || second < 0) {
    return false;
  }
  timestamp->year = static_cast<uint16_t>(yearHigh * 100 + yearLow);
  timestamp->month = static_cast<uint8_t>(month);
  timestamp->date = static_cast<uint8_t>(date);
  timestamp->hour = static_cast<uint8_t>(hour);
  timestamp->minute = static_cast<uint8_t>(minute);
  timestamp->second = static_cast<uint8_t>(second);
  timestamp->weekDay = 0;
  return isValidRtcTimestamp(*timestamp);
}

RtcTimestamp toClockDisplayTimestamp(const RtcTimestamp& timestamp) {
  RtcTimestamp display = timestamp;
  display.hour += kClockDisplayUtcOffsetHours;
  while (display.hour >= 24) {
    display.hour -= 24;
    display.date += 1;
    const uint8_t monthDays = daysInMonth(display.year, display.month);
    if (display.date <= monthDays) {
      continue;
    }
    display.date = 1;
    display.month += 1;
    if (display.month <= 12) {
      continue;
    }
    display.month = 1;
    display.year += 1;
  }
  return display;
}

String formatRtcTimestamp(const RtcTimestamp& timestamp) {
  char buffer[25];
  std::snprintf(
      buffer,
      sizeof(buffer),
      "%04u-%02u-%02uT%02u:%02u:%02uZ",
      static_cast<unsigned>(timestamp.year),
      static_cast<unsigned>(timestamp.month),
      static_cast<unsigned>(timestamp.date),
      static_cast<unsigned>(timestamp.hour),
      static_cast<unsigned>(timestamp.minute),
      static_cast<unsigned>(timestamp.second));
  return String(buffer);
}

void addMinutesToTimestamp(RtcTimestamp* timestamp, uint16_t minutes) {
  if (timestamp == nullptr) {
    return;
  }

  const uint16_t totalMinutes = static_cast<uint16_t>(timestamp->minute) + minutes;
  timestamp->minute = static_cast<uint8_t>(totalMinutes % 60);
  timestamp->hour += static_cast<uint8_t>(totalMinutes / 60);
  while (timestamp->hour >= 24) {
    timestamp->hour -= 24;
    timestamp->date += 1;
    const uint8_t monthDays = daysInMonth(timestamp->year, timestamp->month);
    if (timestamp->date <= monthDays) {
      continue;
    }
    timestamp->date = 1;
    timestamp->month += 1;
    if (timestamp->month <= 12) {
      continue;
    }
    timestamp->month = 1;
    timestamp->year += 1;
  }
}

void addSecondsToTimestamp(RtcTimestamp* timestamp, uint32_t seconds) {
  if (timestamp == nullptr) {
    return;
  }

  const uint32_t totalSeconds = static_cast<uint32_t>(timestamp->second) + seconds;
  timestamp->second = static_cast<uint8_t>(totalSeconds % 60);
  uint32_t minutes = totalSeconds / 60;
  while (minutes > 0) {
    const uint16_t chunk = minutes > 1440 ? 1440 : static_cast<uint16_t>(minutes);
    addMinutesToTimestamp(timestamp, chunk);
    minutes -= chunk;
  }
}

void addDaysToTimestamp(RtcTimestamp* timestamp, uint16_t days) {
  for (uint16_t i = 0; i < days; ++i) {
    addMinutesToTimestamp(timestamp, 24 * 60);
  }
}

int compareRtcTimestamp(const RtcTimestamp& left, const RtcTimestamp& right) {
  if (left.year != right.year) return left.year < right.year ? -1 : 1;
  if (left.month != right.month) return left.month < right.month ? -1 : 1;
  if (left.date != right.date) return left.date < right.date ? -1 : 1;
  if (left.hour != right.hour) return left.hour < right.hour ? -1 : 1;
  if (left.minute != right.minute) return left.minute < right.minute ? -1 : 1;
  if (left.second != right.second) return left.second < right.second ? -1 : 1;
  return 0;
}

bool isCardDue(const DeviceCard& card, const RtcTimestamp& now) {
  if (card.dueAt[0] == '\0') {
    return false;
  }
  RtcTimestamp due = {};
  if (!parseUtcTimestamp(String(card.dueAt), &due)) {
    return false;
  }
  return compareRtcTimestamp(due, now) <= 0;
}

void applyLocalReview(DeviceCard& card, Rating rating, const RtcTimestamp& reviewedAt) {
  card.reviewCount += 1;
  RtcTimestamp due = reviewedAt;

  if (rating == Rating::Forgot) {
    copyBounded(card.status, sizeof(card.status), "learning");
    card.lapses += 1;
    card.ease = maxFloat(1.3F, card.ease - 0.2F);
    card.intervalDays = 0;
    addMinutesToTimestamp(&due, 10);
  } else if (rating == Rating::Hard) {
    copyBounded(card.status, sizeof(card.status), "review");
    card.ease = maxFloat(1.3F, card.ease - 0.05F);
    card.intervalDays =
        static_cast<int16_t>(maxFloat(1.0F, roundf(card.intervalDays * 1.2F)));
    addDaysToTimestamp(&due, static_cast<uint16_t>(card.intervalDays));
  } else {
    copyBounded(card.status, sizeof(card.status), "review");
    card.ease = minFloat(3.0F, card.ease + 0.05F);
    if (card.intervalDays == 0) {
      card.intervalDays = 1;
    } else {
      card.intervalDays =
          static_cast<int16_t>(maxFloat(1.0F, roundf(card.intervalDays * card.ease)));
    }
    addDaysToTimestamp(&due, static_cast<uint16_t>(card.intervalDays));
  }

  copyBounded(card.dueAt, sizeof(card.dueAt), formatRtcTimestamp(due));
}

String formatRtcDate(const RtcTimestamp& timestamp) {
  char buffer[11];
  std::snprintf(
      buffer,
      sizeof(buffer),
      "%04u-%02u-%02u",
      static_cast<unsigned>(timestamp.year),
      static_cast<unsigned>(timestamp.month),
      static_cast<unsigned>(timestamp.date));
  return String(buffer);
}

String formatRtcTime(const RtcTimestamp& timestamp) {
  char buffer[9];
  std::snprintf(
      buffer,
      sizeof(buffer),
      "%02u:%02u:%02u",
      static_cast<unsigned>(timestamp.hour),
      static_cast<unsigned>(timestamp.minute),
      static_cast<unsigned>(timestamp.second));
  return String(buffer);
}

RtcTimestamp readRtcTimestamp() {
  m5::rtc_time_t time = {};
  m5::rtc_date_t date = {};
  M5.Rtc.getTime(&time);
  M5.Rtc.getDate(&date);
  return {
      static_cast<uint16_t>(date.year),
      static_cast<uint8_t>(date.month),
      static_cast<uint8_t>(date.date),
      static_cast<uint8_t>(time.hours),
      static_cast<uint8_t>(time.minutes),
      static_cast<uint8_t>(time.seconds),
      static_cast<uint8_t>(date.weekDay),
  };
}

void syncClockBase(const RtcTimestamp& timestamp) {
  if (!isValidRtcTimestamp(timestamp)) {
    clockBaseValid = false;
    return;
  }

  clockBaseTimestamp = timestamp;
  clockBaseMillis = millis();
  clockBaseValid = true;
}

RtcTimestamp currentClockTimestamp() {
  if (!clockBaseValid) {
    const RtcTimestamp timestamp = readRtcTimestamp();
    syncClockBase(timestamp);
    return timestamp;
  }

  RtcTimestamp timestamp = clockBaseTimestamp;
  addSecondsToTimestamp(&timestamp, (millis() - clockBaseMillis) / 1000);
  return timestamp;
}

void logRtcNow() {
  const RtcTimestamp timestamp = readRtcTimestamp();
  if (!isValidRtcTimestamp(timestamp)) {
    Serial.println("RTC now=invalid valid=0");
    return;
  }
  Serial.println("RTC now=" + formatRtcTimestamp(timestamp) + " valid=1");
}

void recordInteraction(uint32_t now) {
  lastInteractionAt = now;
}

void handleIdlePowerOff(uint32_t now) {
  if (powerOffStarted || now < lastInteractionAt || now - lastInteractionAt < idleTimeoutMs()) {
    return;
  }

  powerOffStarted = true;
  Serial.println("Idle power off");
  if (pendingReviewCount > 0) {
    savePendingReviews();
  }
  drawStatusMessage("Power off");
  delay(100);
  M5.Power.powerOff();
}

uint32_t idleTimeoutMs() {
  return currentPage == Page::Clock ? kClockIdlePowerOffMs : kIdlePowerOffMs;
}

void showClockPage() {
  if (currentPage != Page::Clock) {
    clockExitPage = currentPage;
  }
  recordInteraction(millis());
  lastClockRefreshAt = 0;
  setPage(Page::Clock);
}

void updateClockPage(uint32_t now) {
  if (currentPage == Page::Clock && now - lastClockRefreshAt >= kClockRefreshMs) {
    lastClockRefreshAt = now;
    needsRender = true;
  }
}

void setRtcFromGeneratedAt(const char* generatedAt) {
  RtcTimestamp timestamp = {};
  if (!parseUtcTimestamp(String(generatedAt), &timestamp)) {
    Serial.println("RTC set skipped: invalid generated_at");
    return;
  }

  m5::rtc_time_t time = {
      static_cast<int8_t>(timestamp.hour),
      static_cast<int8_t>(timestamp.minute),
      static_cast<int8_t>(timestamp.second),
  };
  m5::rtc_date_t date = {
      static_cast<int16_t>(timestamp.year),
      static_cast<int8_t>(timestamp.month),
      static_cast<int8_t>(timestamp.date),
      static_cast<int8_t>(timestamp.weekDay),
  };
  M5.Rtc.setDate(&date);
  M5.Rtc.setTime(&time);
  syncClockBase(timestamp);
  Serial.println("RTC set=" + formatRtcTimestamp(timestamp));
  logRtcNow();
}

bool selectOfflineDueCards() {
  syncedCardCount = 0;
  const RtcTimestamp now = readRtcTimestamp();
  if (!isValidRtcTimestamp(now)) {
    setStatusPage("RTC invalid", "sync needed");
    drawStatusMessage("RTC invalid", "sync needed");
    return false;
  }

  for (size_t i = 0; i < offlineCardCount && syncedCardCount < kMaxImmediateCards; ++i) {
    const DeviceCard& card = offlineCards[i];
    if (std::strcmp(card.status, "new") != 0 && isCardDue(card, now)) {
      syncedCards[syncedCardCount++] = card;
    }
  }

  if (syncedCardCount == 0) {
    for (size_t i = 0; i < offlineCardCount && syncedCardCount < kMaxImmediateCards; ++i) {
      const DeviceCard& card = offlineCards[i];
      if (std::strcmp(card.status, "new") == 0) {
        syncedCards[syncedCardCount++] = card;
      }
    }
  }

  if (syncedCardCount == 0) {
    setStatusPage("No due cards");
    drawStatusMessage("No due cards");
    return false;
  }

  resetReviewSet();
  Serial.printf("Selected offline cards=%u\n", static_cast<unsigned>(syncedCardCount));
  return true;
}

bool fetchDeviceTasks() {
  drawStatusMessage("Sync...");
  HTTPClient http;
  const String url = runtimeServerUrl() + "/api/device/tasks?limit=20";
  Serial.println("GET " + url);
  http.begin(url);
  const int status = http.GET();
  if (status != 200) {
    Serial.printf("Sync failed status=%d\n", status);
    http.end();
    syncedCardCount = 0;
    serverGeneratedAt[0] = '\0';
    if (loadCachedTasks()) {
      Serial.println("Using cached tasks after sync failure");
      selectOfflineDueCards();
      return true;
    }
    drawStatusMessage("Sync failed", "check server");
    setStatusPage("Sync failed", "check server");
    return false;
  }

  const String body = http.getString();
  http.end();
  if (!parseDeviceTasksJson(body)) {
    Serial.println("Sync parse failed");
    syncedCardCount = 0;
    serverGeneratedAt[0] = '\0';
    if (loadCachedTasks()) {
      Serial.println("Using cached tasks after parse failure");
      selectOfflineDueCards();
      return true;
    }
    drawStatusMessage("Sync failed", "check server");
    setStatusPage("Sync failed", "check server");
    return false;
  }
  setRtcFromGeneratedAt(serverGeneratedAt);
  tasksFetchedAtMs = millis();

  if (syncedCardCount == 0) {
    Serial.println("No due cards");
    if (offlineCardCount > 0) {
      saveCachedTasks();
    } else {
      clearCachedTasks();
    }
    drawStatusMessage("No due cards");
    setStatusPage("No due cards");
    return true;
  }

  Serial.printf("Synced cards=%u\n", static_cast<unsigned>(syncedCardCount));
  saveCachedTasks();
  resetReviewSet();
  return true;
}

String currentReviewTimestamp() {
  if (serverGeneratedAt[0] != '\0') {
    return String(serverGeneratedAt);
  }
  return "1970-01-01T00:00:00Z";
}

void queuePendingReview(const char* wordId, Rating rating) {
  if (pendingReviewCount >= kMaxPendingReviews) {
    Serial.println("Pending review queue full");
    drawStatusMessage("Review queue full", "sync needed");
    return;
  }

  PendingReview& pending = pendingReviews[pendingReviewCount++];
  copyBounded(pending.wordId, sizeof(pending.wordId), String(wordId));
  pending.rating = rating;
  copyBounded(pending.reviewedAt, sizeof(pending.reviewedAt), currentReviewTimestamp());
  pending.sequence = ++reviewSequence;
  pending.uploaded = false;
  savePendingReviews();
}

size_t pendingReviewUploadCount() {
  size_t count = 0;
  for (size_t i = 0; i < pendingReviewCount; ++i) {
    if (!pendingReviews[i].uploaded) {
      count += 1;
    }
  }
  return count;
}

String buildPendingReviewsJson() {
  String body = "{\"device_id\":\"m5stick-c-plus\",\"reviews\":[";
  bool first = true;
  for (size_t i = 0; i < pendingReviewCount; ++i) {
    PendingReview& pending = pendingReviews[i];
    if (pending.uploaded) {
      continue;
    }
    if (!first) {
      body += ",";
    }
    first = false;

    const String eventId =
        String("m5stick-c-plus-") + String(reviewBootNonce, HEX) + "-" +
        String(pending.sequence) + "-" + pending.wordId;
    body += "{\"word_id\":\"";
    body += pending.wordId;
    body += "\",\"rating\":\"";
    body += ratingName(pending.rating);
    body += "\",\"reviewed_at\":\"";
    body += pending.reviewedAt;
    body += "\",\"event_id\":\"";
    body += eventId;
    body += "\"}";
  }
  body += "]}";
  return body;
}

void markPendingReviewsUploaded() {
  pendingReviewCount = 0;
  clearPendingReviews();
}

String compactJsonMarkers(const String& body) {
  String compact = "";
  bool inString = false;
  bool escaped = false;
  for (int i = 0; i < body.length(); ++i) {
    const char current = body[i];
    if (inString) {
      compact += current;
      if (escaped) {
        escaped = false;
      } else if (current == '\\') {
        escaped = true;
      } else if (current == '"') {
        inString = false;
      }
      continue;
    }
    if (current == '"') {
      inString = true;
      compact += current;
    } else if (current != ' ' && current != '\n' && current != '\r' && current != '\t') {
      compact += current;
    }
  }
  return compact;
}

bool uploadResponseAccepted(const String& response, size_t attemptedReviews) {
  const String compact = compactJsonMarkers(response);
  if (compact.indexOf("\"failed\":0") < 0) {
    return false;
  }
  if (compact.indexOf("\"accepted\":") < 0 ||
      compact.indexOf("\"skipped_duplicate\":") < 0) {
    return false;
  }

  const int accepted = jsonIntValue(compact, "accepted");
  const int skipped = jsonIntValue(compact, "skipped_duplicate");
  if (accepted < 0 || skipped < 0) {
    return false;
  }
  return static_cast<size_t>(accepted + skipped) >= attemptedReviews;
}

bool uploadPendingReviews() {
  if (pendingReviewCount == 0 || WiFi.status() != WL_CONNECTED) {
    return false;
  }

  const size_t attemptedReviews = pendingReviewUploadCount();
  if (attemptedReviews == 0) {
    return false;
  }

  HTTPClient http;
  const String url = runtimeServerUrl() + "/api/device/reviews";
  const String body = buildPendingReviewsJson();
  Serial.println("POST " + url);
  http.begin(url);
  http.addHeader("Content-Type", "application/json");
  const int status = http.POST(body);
  const String response = http.getString();
  http.end();

  if (status != 200) {
    Serial.printf("Review upload failed status=%d\n", status);
    return false;
  }

  Serial.println("Review upload response=" + response);
  if (!uploadResponseAccepted(response, attemptedReviews)) {
    Serial.println("Review upload response kept pending reviews");
    return false;
  }
  markPendingReviewsUploaded();
  return true;
}

void resetReviewSet() {
  for (size_t i = 0; i < kMaxSyncedCards; ++i) {
    reviewResults[i] = {false, Rating::Forgot, 0};
  }
  currentCardIndex = 0;
  contentPageStart = 0;
  selectedRating = Rating::Forgot;
  lastSubmittedIndex = -1;
  returnAfterReRatingIndex = -1;
  isReRating = false;
  setPage(Page::Word);
}

void submitRating() {
  ReviewResult& result = reviewResults[currentCardIndex];
  const Card card = currentCard();

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
  queuePendingReview(currentWordId(), selectedRating);
  const RtcTimestamp reviewedAt = readRtcTimestamp();
  if (isValidRtcTimestamp(reviewedAt)) {
    applyLocalReview(syncedCards[currentCardIndex], selectedRating, reviewedAt);
    for (size_t i = 0; i < offlineCardCount; ++i) {
      if (std::strcmp(offlineCards[i].id, syncedCards[currentCardIndex].id) == 0) {
        offlineCards[i] = syncedCards[currentCardIndex];
        break;
      }
    }
    saveCachedTasks();
  }

  if (isReRating && returnAfterReRatingIndex >= 0) {
    currentCardIndex = static_cast<size_t>(returnAfterReRatingIndex);
    contentPageStart = 0;
    returnAfterReRatingIndex = -1;
    isReRating = false;
    setPage(currentCardIndex >= activeCardCount() ? Page::Done : Page::Word);
    return;
  }

  ++currentCardIndex;
  if (currentCardIndex >= activeCardCount()) {
    Serial.println("Review complete");
    setPage(Page::Done);
    return;
  }

  selectedRating = Rating::Forgot;
  contentPageStart = 0;
  setPage(Page::Word);
}

void updateShakeGood(uint32_t now) {
  if (currentPage != Page::Rating) {
    resetShakeDetection();
    return;
  }

  if (now - lastShakeAt < kShakeCooldownMs) {
    return;
  }

  const float magnitude = accelMagnitude();
  if (magnitude < kShakeReleaseThreshold) {
    shakeAboveThreshold = false;
    return;
  }

  if (magnitude < kShakeThreshold || shakeAboveThreshold) {
    return;
  }

  shakeAboveThreshold = true;
  if (shakeCount == 0 || now - shakeWindowStartedAt > kShakeWindowMs) {
    shakeCount = 1;
    shakeWindowStartedAt = now;
    return;
  }

  shakeCount += 1;
  if (shakeCount < 2) {
    return;
  }

  selectedRating = Rating::Good;
  lastShakeAt = now;
  recordInteraction(now);
  Serial.printf("Shake good word=%s magnitude=%.2f\n", currentCard().word, magnitude);
  submitRating();
}

bool tryReRatePrevious() {
  const size_t cardCount = activeCardCount();
  const int previousIndex = currentPage == Page::Done
                                ? static_cast<int>(cardCount - 1)
                                : static_cast<int>(currentCardIndex) - 1;

  if (previousIndex < 0 || !reviewResults[previousIndex].hasRating) {
    Serial.println("No previous review to re-rate");
    return false;
  }

  returnAfterReRatingIndex = currentPage == Page::Done
                                 ? static_cast<int>(cardCount)
                                 : static_cast<int>(currentCardIndex);
  currentCardIndex = static_cast<size_t>(previousIndex);
  selectedRating = reviewResults[currentCardIndex].rating;
  isReRating = true;
  Serial.printf("Re-rating previous word=%s rating=%s\n", currentCard().word,
                ratingName(selectedRating));
  setPage(Page::Rating);
  return true;
}

void handleButtonAShortPress() {
  recordInteraction(millis());
  switch (currentPage) {
    case Page::Status:
      if (statusReturnsToClock) {
        showClockPage();
      }
      break;
    case Page::Clock:
      setPage(clockExitPage);
      break;
    case Page::Word:
      setContentPage(Page::Meaning, 0);
      break;
    case Page::Meaning: {
      const Card card = currentCard();
      if (hasMoreContentPage(card.meaning)) {
        setContentPage(Page::Meaning, findNextContentPageStart(card.meaning, contentPageStart));
      } else {
        setContentPage(Page::Example, 0);
      }
      break;
    }
    case Page::Example: {
      const Card card = currentCard();
      if (hasMoreContentPage(card.example)) {
        setContentPage(Page::Example, findNextContentPageStart(card.example, contentPageStart));
      } else {
        selectedRating = reviewResults[currentCardIndex].hasRating
                             ? reviewResults[currentCardIndex].rating
                             : Rating::Forgot;
        setPage(Page::Rating);
        Serial.printf("Page rating index=%u selected=%s\n",
                      static_cast<unsigned>(currentCardIndex), ratingName(selectedRating));
      }
      break;
    }
    case Page::Rating: {
      const Card card = currentCard();
      selectedRating = nextRating(selectedRating);
      Serial.printf("Rating changed word=%s rating=%s\n", card.word, ratingName(selectedRating));
      needsRender = true;
      break;
    }
    case Page::Done:
      resetReviewSet();
      break;
  }
}

void handleButtonALongPress() {
  recordInteraction(millis());
  if (currentPage == Page::Status && statusReturnsToClock) {
    showClockPage();
    return;
  }
  if (currentPage == Page::Rating) {
    submitRating();
  }
}

void handleButtonBShortPress() {
  recordInteraction(millis());
  switch (currentPage) {
    case Page::Status:
      break;
    case Page::Clock:
      break;
    case Page::Word:
      tryReRatePrevious();
      break;
    case Page::Meaning: {
      const Card card = currentCard();
      if (contentPageStart > 0) {
        setContentPage(Page::Meaning, findPreviousContentPageStart(card.meaning, contentPageStart));
      } else {
        setPage(Page::Word);
      }
      break;
    }
    case Page::Example: {
      const Card card = currentCard();
      if (contentPageStart > 0) {
        setContentPage(Page::Example, findPreviousContentPageStart(card.example, contentPageStart));
      } else {
        setContentPage(Page::Meaning, findPreviousContentPageStart(card.meaning, std::strlen(card.meaning)));
      }
      break;
    }
    case Page::Rating: {
      const Card card = currentCard();
      setContentPage(Page::Example, findPreviousContentPageStart(card.example, std::strlen(card.example)));
      break;
    }
    case Page::Done:
      tryReRatePrevious();
      break;
  }
}

}  // namespace

void setup() {
  auto cfg = M5.config();
  cfg.serial_baudrate = 115200;
  cfg.internal_imu = true;
  cfg.clear_display = true;
  M5.begin(cfg);
  delay(200);

  lv_init();
  lv_disp_draw_buf_init(&lvDrawBuf, lvBuf1, lvBuf2, 240 * 16);
  lv_disp_drv_init(&lvDispDrv);
  lvDispDrv.hor_res = 240;
  lvDispDrv.ver_res = 135;
  lvDispDrv.flush_cb = lvglFlushCb;
  lvDispDrv.draw_buf = &lvDrawBuf;
  lv_disp_drv_register(&lvDispDrv);
  createClockUI();

  readImu();
  currentRotation = detectLandscapeRotation();
  pendingRotation = currentRotation;
  pendingRotationSince = millis();
  M5.Display.setRotation(currentRotation);
  M5.Display.setTextFont(1);
  M5.Display.setTextDatum(TL_DATUM);
  reviewBootNonce = esp_random();
  lastInteractionAt = millis();

  Serial.println("StickWords Stage 4 boot");
  Serial.printf("Orientation rotation=%u ax=%.2f ay=%.2f az=%.2f\n",
                static_cast<unsigned>(currentRotation), accelX, accelY, accelZ);
  logRtcNow();
  M5.update();
  const bool forceSetup = M5.BtnB.isPressed();
  if (!loadRuntimeConfig() || forceSetup) {
    Serial.println(forceSetup ? "Setup portal forced" : "Setup portal missing config");
    startSetupPortal();
    logPage();
    render();
    return;
  }

  loadPendingReviews();
  if (connectWifi()) {
    uploadPendingReviews();
    fetchDeviceTasks();
  } else if (loadCachedTasks()) {
    Serial.println("Using cached tasks after WiFi failure");
    selectOfflineDueCards();
  }
  showClockPage();
  logPage();
  render();
}

void loop() {
  M5.update();
  if (setupPortalActive) {
    handleSetupPortalLoop();
    render();
    delay(20);
    return;
  }

  const uint32_t now = millis();
  readImu();
  updateAutoRotation(now);
  updateClockPage(now);
  updateShakeGood(now);

  if (M5.BtnA.wasReleaseFor(kButtonLongPressMs)) {
    handleButtonALongPress();
  } else if (M5.BtnA.wasReleased()) {
    handleButtonAShortPress();
  }

  if (M5.BtnB.wasReleased()) {
    handleButtonBShortPress();
  }

  handleIdlePowerOff(millis());
  if (currentPage == Page::Clock) {
    lv_timer_handler();
  }
  render();
  delay(20);
}
