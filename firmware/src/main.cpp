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
