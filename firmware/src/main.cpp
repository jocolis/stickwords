#include <HTTPClient.h>
#include <M5StickCPlus.h>
#include <WiFi.h>
#include <cmath>
#include <cstring>
#include "secrets.h"

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
constexpr uint32_t kButtonLongPressMs = 650;
constexpr uint32_t kOrientationStableMs = 500;
constexpr uint32_t kShakeWindowMs = 650;
constexpr uint32_t kShakeCooldownMs = 900;
constexpr size_t kContentPageChars = 58;
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
  bool uploaded;
};

ReviewResult reviewResults[kMaxSyncedCards] = {};
DeviceCard syncedCards[kMaxSyncedCards] = {};
PendingReview pendingReviews[kMaxPendingReviews] = {};
size_t syncedCardCount = 0;
size_t pendingReviewCount = 0;
Page currentPage = Page::Word;
size_t currentCardIndex = 0;
uint8_t contentPageIndex = 0;
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

size_t contentPageCount(const char* text) {
  const size_t length = std::strlen(text);
  if (length == 0) {
    return 1;
  }
  return (length + kContentPageChars - 1) / kContentPageChars;
}

bool hasMoreContentPage(const char* text) {
  return static_cast<size_t>(contentPageIndex + 1) < contentPageCount(text);
}

void setContentPage(Page page, uint8_t pageIndex) {
  contentPageIndex = pageIndex;
  setPage(page);
}

size_t activeCardCount() {
  return syncedCardCount > 0 ? syncedCardCount : kCardCount;
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

void drawContentPage(const char* text) {
  M5.Lcd.setTextSize(2);

  const size_t start = static_cast<size_t>(contentPageIndex) * kContentPageChars;
  const size_t length = std::strlen(text);
  const size_t end = start + kContentPageChars < length ? start + kContentPageChars : length;

  for (size_t i = start; i < end; ++i) {
    M5.Lcd.print(text[i]);
  }

  if (end < length) {
    M5.Lcd.print("...");
  }
  M5.Lcd.println();
}

void drawMeaningPage() {
  const Card card = currentCard();
  drawContentPage(card.meaning);
}

void drawExamplePage() {
  const Card card = currentCard();
  drawContentPage(card.example);
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
  Serial.printf("WiFi connecting ssid=%s\n", STICKWORDS_WIFI_SSID);
  return false;
}

bool fetchDeviceTasks() {
  drawStatusMessage("Sync failed", "using samples");
  Serial.printf("Sync failed url=%s\n", STICKWORDS_SERVER_URL);
  return false;
}

bool uploadPendingReviews() {
  return false;
}

void resetReviewSet() {
  for (size_t i = 0; i < kMaxSyncedCards; ++i) {
    reviewResults[i] = {false, Rating::Forgot, 0};
  }
  currentCardIndex = 0;
  contentPageIndex = 0;
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
  uploadPendingReviews();

  if (isReRating && returnAfterReRatingIndex >= 0) {
    currentCardIndex = static_cast<size_t>(returnAfterReRatingIndex);
    contentPageIndex = 0;
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
  contentPageIndex = 0;
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
        setContentPage(Page::Meaning, contentPageIndex + 1);
      } else {
        setContentPage(Page::Example, 0);
      }
      break;
    case Page::Example:
      if (hasMoreContentPage(card.example)) {
        setContentPage(Page::Example, contentPageIndex + 1);
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
      if (contentPageIndex > 0) {
        setContentPage(Page::Meaning, contentPageIndex - 1);
      } else {
        setPage(Page::Word);
      }
      break;
    case Page::Example:
      if (contentPageIndex > 0) {
        setContentPage(Page::Example, contentPageIndex - 1);
      } else {
        setContentPage(Page::Meaning,
                       static_cast<uint8_t>(contentPageCount(card.meaning) - 1));
      }
      break;
    case Page::Rating:
      setContentPage(Page::Example,
                     static_cast<uint8_t>(contentPageCount(card.example) - 1));
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

  Serial.println("StickWords Stage 3C boot");
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
