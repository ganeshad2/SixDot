import logging
import os
import warnings
from pathlib import Path

import easyocr

from lookup import print_translation, run_motor, servo_lut, translate_word

# Mute noisy OCR warnings and logs.
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
warnings.filterwarnings("ignore")
logging.getLogger("easyocr").setLevel(logging.FATAL)
logging.getLogger("torch").setLevel(logging.FATAL)

CAPTURE_DIR = Path.cwd() / "captures"
reader = easyocr.Reader(["en"], gpu=False)


def get_latest_capture_path():
    images = list(CAPTURE_DIR.glob("*.jpg"))
    if not images:
        return None
    return max(images, key=lambda p: p.stat().st_mtime)


def detect_words_from_image(image_path):
    results = reader.readtext(str(image_path))
    raw_words = [text for (_, text, _) in results] if results else []

    valid_words = []
    for text in raw_words:
        cleaned = text.strip()
        if cleaned.isalpha():
            valid_words.append(cleaned)

    return valid_words


def detect_words_from_latest_capture():
    image_path = get_latest_capture_path()
    if image_path is None:
        return None, [], "No images found in captures directory."

    valid_words = detect_words_from_image(image_path)
    if not valid_words:
        return image_path, [], "No valid words found."

    return image_path, valid_words, None


def run_lookup_for_words(words):
    for word in words:
        print(f"\nWord chosen for lookup: '{word}'")
        braille_results = translate_word(word, servo_lut)
        print_translation(braille_results)
        run_motor(braille_results)


def main():
    image_path, valid_words, error_message = detect_words_from_latest_capture()
    if error_message:
        print(error_message)
        raise SystemExit()

    print(f"\nUsing image: {image_path.resolve()}")
    print("\nWords chosen for lookup:", valid_words)
    run_lookup_for_words(valid_words)


if __name__ == "__main__":
    main()
