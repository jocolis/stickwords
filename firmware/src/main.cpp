#include <HTTPClient.h>
#include <M5StickCPlus.h>
#include <WiFi.h>
#include <cmath>
#include <cstring>
#include <esp_system.h>

#if __has_include("secrets.h")
#include "secrets.h"
#else
#error "Missing firmware/include/secrets.h: copy firmware/include/secrets.example.h to firmware/include/secrets.h, then edit Wi-Fi and PC URL values."
#endif

namespace {

enum class Page {
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

constexpr Card kCards[] = {
    {"abandon", "give up", "Do not abandon your plan when practice gets hard."},
    {"benefit", "good effect", "Daily review has a clear benefit."},
    {"curious", "wanting to know", "A curious learner asks better questions."},
};

constexpr size_t kCardCount = sizeof(kCards) / sizeof(kCards[0]);
constexpr size_t kMaxSyncedCards = 20;
constexpr size_t kMaxPendingReviews = 20;
constexpr size_t kMaxWordIdLength = 24;
constexpr size_t kMaxWordLength = 32;
constexpr size_t kMaxMeaningLength = 192;
constexpr size_t kMaxExampleLength = 256;
constexpr size_t kMaxTimestampLength = 25;
constexpr uint32_t kButtonLongPressMs = 650;
constexpr uint32_t kOrientationStableMs = 500;
constexpr uint32_t kShakeWindowMs = 650;
constexpr uint32_t kShakeCooldownMs = 900;
constexpr uint8_t kContentTextSize = 2;
constexpr int16_t kContentX = 6;
constexpr int16_t kContentY = 6;
constexpr int16_t kContentMaxX = 234;
constexpr int16_t kContentMaxY = 132;
constexpr int16_t kContentLineHeight = 18;
constexpr float kOrientationThreshold = 0.45F;
constexpr float kShakeThreshold = 1.65F;
constexpr float kShakeReleaseThreshold = 1.25F;

struct DeviceCard {
  char id[kMaxWordIdLength];
  char word[kMaxWordLength];
  char meaning[kMaxMeaningLength];
  char example[kMaxExampleLength];
};

struct PendingReview {
  char wordId[kMaxWordIdLength];
  Rating rating;
  uint32_t reviewedAtMs;
  uint32_t sequence;
  bool uploaded;
};

ReviewResult reviewResults[kMaxSyncedCards] = {};
DeviceCard syncedCards[kMaxSyncedCards] = {};
PendingReview pendingReviews[kMaxPendingReviews] = {};
size_t syncedCardCount = 0;
size_t pendingReviewCount = 0;
char serverGeneratedAt[kMaxTimestampLength] = "";
uint32_t tasksFetchedAtMs = 0;
uint32_t reviewBootNonce = 0;
uint32_t reviewSequence = 0;
Page currentPage = Page::Word;
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
bool shakeAboveThreshold = false;
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
  return M5.Lcd.textWidth(token);
}

size_t fitLongTokenEnd(const char* text, size_t start, size_t end) {
  size_t cursor = start;
  int16_t cursorX = kContentX;
  int16_t cursorY = kContentY;

  while (cursor < end) {
    String character = "";
    character += text[cursor];
    const int16_t charWidth = M5.Lcd.textWidth(character);
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
  M5.Lcd.setTextSize(kContentTextSize);
  const size_t length = std::strlen(text);
  size_t index = skipBreakChars(text, start);
  size_t lastFitEnd = index;
  int16_t cursorX = kContentX;
  int16_t cursorY = kContentY;

  while (index < length) {
    const size_t tokenStart = index;
    const size_t tokenEnd = nextTokenEnd(text, index);
    const int16_t tokenWidth = textWidthSlice(text, tokenStart, tokenEnd);
    const int16_t spaceWidth = cursorX == kContentX ? 0 : M5.Lcd.textWidth(" ");

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
  if (syncedCardCount == 0) {
    return kCardCount;
  }
  return syncedCardCount > kMaxSyncedCards ? kMaxSyncedCards : syncedCardCount;
}

const char* currentWordId() {
  return syncedCardCount > 0 ? syncedCards[currentCardIndex].id : kCards[currentCardIndex].word;
}

Card currentCard() {
  if (syncedCardCount == 0) {
    return kCards[currentCardIndex];
  }
  return {
      syncedCards[currentCardIndex].word,
      syncedCards[currentCardIndex].meaning,
      syncedCards[currentCardIndex].example,
  };
}

void readImu() {
  M5.IMU.getAccelData(&accelX, &accelY, &accelZ);
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
  M5.Lcd.setRotation(currentRotation);
  needsRender = true;
  Serial.printf("Orientation rotation=%u ax=%.2f ay=%.2f az=%.2f\n",
                static_cast<unsigned>(currentRotation), accelX, accelY, accelZ);
}

void drawCenteredText(const char* text, int16_t y, uint8_t textSize) {
  M5.Lcd.setTextSize(textSize);
  const int16_t textWidth = M5.Lcd.textWidth(text);
  const int16_t x = (240 - textWidth) / 2;
  M5.Lcd.setCursor(x < 0 ? 0 : x, y);
  M5.Lcd.println(text);
}

void drawWordPage() {
  const Card card = currentCard();
  drawCenteredText(card.word, 52, 3);
}

void drawWrappedContentPage(const char* text) {
  M5.Lcd.setTextSize(kContentTextSize);
  size_t index = skipBreakChars(text, contentPageStart);
  size_t lastDrawnEnd = index;
  int16_t cursorX = kContentX;
  int16_t cursorY = kContentY;

  while (text[index] != '\0') {
    const size_t tokenStart = index;
    const size_t tokenEnd = nextTokenEnd(text, index);
    const int16_t tokenWidth = textWidthSlice(text, tokenStart, tokenEnd);
    const int16_t spaceWidth = cursorX == kContentX ? 0 : M5.Lcd.textWidth(" ");

    if (cursorX != kContentX && cursorX + spaceWidth + tokenWidth > kContentMaxX) {
      cursorX = kContentX;
      cursorY += kContentLineHeight;
    }
    if (cursorY + kContentLineHeight > kContentMaxY) {
      break;
    }

    M5.Lcd.setCursor(cursorX, cursorY);
    if (cursorX != kContentX) {
      M5.Lcd.print(" ");
      cursorX += spaceWidth;
    }

    if (tokenWidth > kContentMaxX - kContentX && cursorX == kContentX) {
      size_t charIndex = tokenStart;
      while (charIndex < tokenEnd) {
        String character = "";
        character += text[charIndex];
        const int16_t charWidth = M5.Lcd.textWidth(character);
        if (cursorX + charWidth > kContentMaxX) {
          cursorX = kContentX;
          cursorY += kContentLineHeight;
          if (cursorY + kContentLineHeight > kContentMaxY) {
            index = charIndex;
            break;
          }
          M5.Lcd.setCursor(cursorX, cursorY);
        }
        M5.Lcd.print(character);
        cursorX += charWidth;
        charIndex += 1;
        lastDrawnEnd = charIndex;
      }
      if (lastDrawnEnd < tokenEnd) {
        break;
      }
    } else {
      for (size_t i = tokenStart; i < tokenEnd; ++i) {
        M5.Lcd.print(text[i]);
      }
      cursorX += tokenWidth;
      lastDrawnEnd = tokenEnd;
    }

    index = skipBreakChars(text, tokenEnd);
  }

  if (findNextContentPageStart(text, contentPageStart) < std::strlen(text)) {
    M5.Lcd.setCursor(kContentMaxX - M5.Lcd.textWidth("..."), kContentMaxY - kContentLineHeight);
    M5.Lcd.print("...");
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
  M5.Lcd.printf("%c %s\n", rating == selectedRating ? '>' : ' ', ratingName(rating));
}

void drawRatingPage() {
  const Card card = currentCard();
  M5.Lcd.setTextSize(2);
  M5.Lcd.print(card.word);
  M5.Lcd.println();
  M5.Lcd.println();
  drawRatingOption(Rating::Forgot);
  drawRatingOption(Rating::Hard);
  drawRatingOption(Rating::Good);
}

void drawDonePage() {
  drawCenteredText("Review complete", 38, 2);
  M5.Lcd.setTextSize(2);
  M5.Lcd.setCursor(74, 76);
  M5.Lcd.printf("%u/%u rated", static_cast<unsigned>(activeCardCount()),
                static_cast<unsigned>(activeCardCount()));
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

void drawStatusMessage(const char* line1, const char* line2 = "") {
  M5.Lcd.fillScreen(BLACK);
  M5.Lcd.setCursor(8, 36);
  M5.Lcd.setTextColor(WHITE, BLACK);
  M5.Lcd.setTextSize(2);
  M5.Lcd.println(line1);
  if (line2[0] != '\0') {
    M5.Lcd.println(line2);
  }
}

bool connectWifi() {
  drawStatusMessage("WiFi...");
  WiFi.mode(WIFI_STA);
  WiFi.begin(STICKWORDS_WIFI_SSID, STICKWORDS_WIFI_PASSWORD);

  const uint32_t startedAt = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - startedAt < 12000) {
    delay(250);
    M5.update();
  }

  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi failed");
    drawStatusMessage("WiFi failed", "using samples");
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

bool parseDeviceTasksJson(const String& body) {
  syncedCardCount = 0;
  copyBounded(serverGeneratedAt, sizeof(serverGeneratedAt), jsonStringValue(body, "generated_at"));
  int arrayStart = body.indexOf("\"tasks\"");
  arrayStart = body.indexOf('[', arrayStart);
  if (arrayStart < 0) {
    return false;
  }
  const int arrayEnd = findJsonArrayEnd(body, arrayStart);
  if (arrayEnd < 0) {
    return false;
  }

  int cursor = arrayStart;
  while (syncedCardCount < kMaxSyncedCards) {
    const int objectStart = body.indexOf('{', cursor);
    if (objectStart < 0 || objectStart > arrayEnd) {
      break;
    }
    const int objectEnd = findJsonObjectEnd(body, objectStart, arrayEnd);
    if (objectEnd < 0 || objectEnd > arrayEnd) {
      break;
    }

    const String object = body.substring(objectStart, objectEnd + 1);
    DeviceCard& card = syncedCards[syncedCardCount];
    copyBounded(card.id, sizeof(card.id), jsonStringValue(object, "id"));
    copyBounded(card.word, sizeof(card.word), jsonStringValue(object, "word"));
    copyBounded(card.meaning, sizeof(card.meaning), jsonStringValue(object, "meaning"));
    copyBounded(card.example, sizeof(card.example), jsonStringValue(object, "example"));
    if (card.id[0] != '\0' && card.word[0] != '\0') {
      syncedCardCount += 1;
    }
    cursor = objectEnd + 1;
  }

  return true;
}

bool fetchDeviceTasks() {
  drawStatusMessage("Sync...");
  HTTPClient http;
  const String url = String(STICKWORDS_SERVER_URL) + "/api/device/tasks?limit=20";
  Serial.println("GET " + url);
  http.begin(url);
  const int status = http.GET();
  if (status != 200) {
    Serial.printf("Sync failed status=%d\n", status);
    http.end();
    syncedCardCount = 0;
    serverGeneratedAt[0] = '\0';
    drawStatusMessage("Sync failed", "using samples");
    return false;
  }

  const String body = http.getString();
  http.end();
  if (!parseDeviceTasksJson(body)) {
    Serial.println("Sync parse failed");
    syncedCardCount = 0;
    serverGeneratedAt[0] = '\0';
    drawStatusMessage("Sync failed", "using samples");
    return false;
  }
  tasksFetchedAtMs = millis();

  if (syncedCardCount == 0) {
    Serial.println("No due cards");
    drawStatusMessage("No due cards");
    return true;
  }

  Serial.printf("Synced cards=%u\n", static_cast<unsigned>(syncedCardCount));
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
  for (size_t i = 0; i < pendingReviewCount; ++i) {
    PendingReview& existing = pendingReviews[i];
    if (!existing.uploaded && std::strcmp(existing.wordId, wordId) == 0) {
      Serial.printf("replace pending review word=%s\n", wordId);
      existing.rating = rating;
      existing.reviewedAtMs = millis();
      existing.sequence = ++reviewSequence;
      return;
    }
  }

  if (pendingReviewCount >= kMaxPendingReviews) {
    Serial.println("Pending review queue full");
    return;
  }

  PendingReview& pending = pendingReviews[pendingReviewCount++];
  copyBounded(pending.wordId, sizeof(pending.wordId), String(wordId));
  pending.rating = rating;
  pending.reviewedAtMs = millis();
  pending.sequence = ++reviewSequence;
  pending.uploaded = false;
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
    body += currentReviewTimestamp();
    body += "\",\"event_id\":\"";
    body += eventId;
    body += "\"}";
  }
  body += "]}";
  return body;
}

void markPendingReviewsUploaded() {
  pendingReviewCount = 0;
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

int jsonIntValue(const String& compactBody, const char* key) {
  const String marker = String("\"") + key + "\":";
  const int markerIndex = compactBody.indexOf(marker);
  if (markerIndex < 0) {
    return -1;
  }
  int cursor = markerIndex + marker.length();
  int end = cursor;
  while (end < compactBody.length() && compactBody[end] >= '0' && compactBody[end] <= '9') {
    end += 1;
  }
  if (end == cursor) {
    return -1;
  }
  return compactBody.substring(cursor, end).toInt();
}

bool uploadResponseAccepted(const String& response, size_t attemptedReviews) {
  const String compact = compactJsonMarkers(response);
  if (compact.indexOf("\"failed\":0") < 0) {
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
  const String url = String(STICKWORDS_SERVER_URL) + "/api/device/reviews";
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
  uploadPendingReviews();

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
  const Card card = currentCard();
  switch (currentPage) {
    case Page::Word:
      setContentPage(Page::Meaning, 0);
      break;
    case Page::Meaning:
      if (hasMoreContentPage(card.meaning)) {
        setContentPage(Page::Meaning, findNextContentPageStart(card.meaning, contentPageStart));
      } else {
        setContentPage(Page::Example, 0);
      }
      break;
    case Page::Example:
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
    case Page::Rating:
      selectedRating = nextRating(selectedRating);
      Serial.printf("Rating changed word=%s rating=%s\n", card.word, ratingName(selectedRating));
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
  const Card card = currentCard();
  switch (currentPage) {
    case Page::Word:
      tryReRatePrevious();
      break;
    case Page::Meaning:
      if (contentPageStart > 0) {
        setContentPage(Page::Meaning, findPreviousContentPageStart(card.meaning, contentPageStart));
      } else {
        setPage(Page::Word);
      }
      break;
    case Page::Example:
      if (contentPageStart > 0) {
        setContentPage(Page::Example, findPreviousContentPageStart(card.example, contentPageStart));
      } else {
        setContentPage(Page::Meaning, findPreviousContentPageStart(card.meaning, std::strlen(card.meaning)));
      }
      break;
    case Page::Rating:
      setContentPage(Page::Example, findPreviousContentPageStart(card.example, std::strlen(card.example)));
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

  readImu();
  currentRotation = detectLandscapeRotation();
  pendingRotation = currentRotation;
  pendingRotationSince = millis();
  M5.Lcd.setRotation(currentRotation);
  M5.Lcd.setTextFont(1);
  M5.Lcd.setTextDatum(TL_DATUM);
  reviewBootNonce = esp_random();

  Serial.println("StickWords Stage 4 boot");
  Serial.printf("Orientation rotation=%u ax=%.2f ay=%.2f az=%.2f\n",
                static_cast<unsigned>(currentRotation), accelX, accelY, accelZ);
  if (connectWifi()) {
    fetchDeviceTasks();
  }
  logPage();
  render();
}

void loop() {
  M5.update();
  const uint32_t now = millis();
  readImu();
  updateAutoRotation(now);
  updateShakeGood(now);

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
