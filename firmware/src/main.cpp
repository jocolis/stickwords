#include <HTTPClient.h>
#include <DNSServer.h>
#include <M5StickCPlus.h>
#include <Preferences.h>
#include <WebServer.h>
#include <WiFi.h>
#include <cmath>
#include <cstdio>
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
constexpr size_t kMaxSyncedCards = 20;
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
PendingReview pendingReviews[kMaxPendingReviews] = {};
Preferences storage;
RuntimeConfig runtimeConfig;
DNSServer dnsServer;
WebServer setupServer(80);
size_t syncedCardCount = 0;
size_t pendingReviewCount = 0;
char serverGeneratedAt[kMaxTimestampLength] = "";
char statusLine1[32] = "Sync...";
char statusLine2[32] = "";
char statusLine3[32] = "";
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
bool setupPortalActive = false;

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
    case Page::Status:
      return "status";
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
  setPage(Page::Status);
}

void copyBounded(char* dest, size_t destSize, const String& value);

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

void drawStatusPage() {
  M5.Lcd.setCursor(8, 36);
  M5.Lcd.setTextSize(2);
  M5.Lcd.println(statusLine1);
  if (statusLine2[0] != '\0') {
    M5.Lcd.println(statusLine2);
  }
  if (statusLine3[0] != '\0') {
    M5.Lcd.println(statusLine3);
  }
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
    case Page::Status:
      drawStatusPage();
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

void saveCachedTasks() {
  storage.begin("stickwords", false);
  storage.putUInt("card_count", static_cast<uint32_t>(syncedCardCount));
  storage.putString("generated", serverGeneratedAt);
  storage.putBytes("cards", syncedCards, sizeof(DeviceCard) * syncedCardCount);
  storage.end();
  Serial.printf("Cached cards=%u\n", static_cast<unsigned>(syncedCardCount));
}

bool loadCachedTasks() {
  storage.begin("stickwords", true);
  uint32_t storedCount = storage.getUInt("card_count", 0);
  if (storedCount > kMaxSyncedCards) {
    storedCount = kMaxSyncedCards;
  }

  const size_t expectedBytes = sizeof(DeviceCard) * storedCount;
  const size_t readBytes = storedCount == 0
                               ? 0
                               : storage.getBytes("cards", syncedCards, expectedBytes);
  const String generatedAt = storage.getString("generated", "");
  storage.end();

  if (storedCount == 0 || readBytes != expectedBytes) {
    return false;
  }

  syncedCardCount = storedCount;
  copyBounded(serverGeneratedAt, sizeof(serverGeneratedAt), generatedAt);
  Serial.printf("Loaded cached cards=%u\n", static_cast<unsigned>(syncedCardCount));
  resetReviewSet();
  return true;
}

void clearCachedTasks() {
  storage.begin("stickwords", false);
  storage.remove("card_count");
  storage.remove("generated");
  storage.remove("cards");
  storage.end();
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
  const size_t readBytes = storedCount == 0
                               ? 0
                               : storage.getBytes("pending", pendingReviews, expectedBytes);
  const uint32_t storedSequence = storage.getUInt("review_seq", 0);
  storage.end();

  if (storedCount > 0 && readBytes != expectedBytes) {
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
  M5.Lcd.fillScreen(BLACK);
  M5.Lcd.setCursor(8, 36);
  M5.Lcd.setTextColor(WHITE, BLACK);
  M5.Lcd.setTextSize(2);
  M5.Lcd.println(line1);
  if (line2[0] != '\0') {
    M5.Lcd.println(line2);
  }
  if (line3[0] != '\0') {
    M5.Lcd.println(line3);
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

RtcTimestamp readRtcTimestamp() {
  RTC_TimeTypeDef time = {};
  RTC_DateTypeDef date = {};
  M5.Rtc.GetTime(&time);
  M5.Rtc.GetDate(&date);
  return {
      date.Year,
      date.Month,
      date.Date,
      time.Hours,
      time.Minutes,
      time.Seconds,
      date.WeekDay,
  };
}

void logRtcNow() {
  const RtcTimestamp timestamp = readRtcTimestamp();
  if (!isValidRtcTimestamp(timestamp)) {
    Serial.println("RTC now=invalid valid=0");
    return;
  }
  Serial.println("RTC now=" + formatRtcTimestamp(timestamp) + " valid=1");
}

void setRtcFromGeneratedAt(const char* generatedAt) {
  RtcTimestamp timestamp = {};
  if (!parseUtcTimestamp(String(generatedAt), &timestamp)) {
    Serial.println("RTC set skipped: invalid generated_at");
    return;
  }

  RTC_TimeTypeDef time = {
      timestamp.hour,
      timestamp.minute,
      timestamp.second,
  };
  RTC_DateTypeDef date = {
      timestamp.weekDay,
      timestamp.month,
      timestamp.date,
      timestamp.year,
  };
  M5.Rtc.SetDate(&date);
  M5.Rtc.SetTime(&time);
  Serial.println("RTC set=" + formatRtcTimestamp(timestamp));
  logRtcNow();
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
    clearCachedTasks();
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
  for (size_t i = 0; i < pendingReviewCount; ++i) {
    PendingReview& existing = pendingReviews[i];
    if (!existing.uploaded && std::strcmp(existing.wordId, wordId) == 0) {
      Serial.printf("replace pending review word=%s\n", wordId);
      existing.rating = rating;
      existing.reviewedAtMs = millis();
      existing.sequence = ++reviewSequence;
      savePendingReviews();
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
    case Page::Status:
      break;
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
    case Page::Status:
      break;
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
  }
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
