#include <M5StickCPlus.h>
#include <cstring>

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
constexpr uint32_t kButtonLongPressMs = 650;
constexpr size_t kContentPageChars = 58;

ReviewResult reviewResults[kCardCount] = {};
Page currentPage = Page::Word;
size_t currentCardIndex = 0;
uint8_t contentPageIndex = 0;
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

void setPage(Page page) {
  currentPage = page;
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

void drawCenteredText(const char* text, int16_t y, uint8_t textSize) {
  M5.Lcd.setTextSize(textSize);
  const int16_t textWidth = M5.Lcd.textWidth(text);
  const int16_t x = (240 - textWidth) / 2;
  M5.Lcd.setCursor(x < 0 ? 0 : x, y);
  M5.Lcd.println(text);
}

void drawWordPage() {
  drawCenteredText(kCards[currentCardIndex].word, 52, 3);
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
  drawContentPage(kCards[currentCardIndex].meaning);
}

void drawExamplePage() {
  drawContentPage(kCards[currentCardIndex].example);
}

void drawRatingOption(Rating rating) {
  M5.Lcd.printf("%c %s\n", rating == selectedRating ? '>' : ' ', ratingName(rating));
}

void drawRatingPage() {
  M5.Lcd.setTextSize(2);
  M5.Lcd.println(kCards[currentCardIndex].word);
  M5.Lcd.println();
  drawRatingOption(Rating::Forgot);
  drawRatingOption(Rating::Hard);
  drawRatingOption(Rating::Good);
}

void drawDonePage() {
  drawCenteredText("Review complete", 38, 2);
  drawCenteredText("3/3 rated", 76, 2);
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

void resetReviewSet() {
  for (size_t i = 0; i < kCardCount; ++i) {
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
    contentPageIndex = 0;
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
  contentPageIndex = 0;
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
      setContentPage(Page::Meaning, 0);
      break;
    case Page::Meaning:
      if (hasMoreContentPage(kCards[currentCardIndex].meaning)) {
        setContentPage(Page::Meaning, contentPageIndex + 1);
      } else {
        setContentPage(Page::Example, 0);
      }
      break;
    case Page::Example:
      if (hasMoreContentPage(kCards[currentCardIndex].example)) {
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
                       static_cast<uint8_t>(contentPageCount(kCards[currentCardIndex].meaning) - 1));
      }
      break;
    case Page::Rating:
      setContentPage(Page::Example,
                     static_cast<uint8_t>(contentPageCount(kCards[currentCardIndex].example) - 1));
      break;
    case Page::Done:
      tryReRatePrevious();
      break;
  }
}

}  // namespace

void setup() {
  M5.begin();
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
