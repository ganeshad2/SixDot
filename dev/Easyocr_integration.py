import os
import warnings
import logging
import easyocr
from pathlib import Path


from lookup import translate_word, print_translation, run_motor, servo_lut

# mutes the warnings
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
warnings.filterwarnings("ignore")
logging.getLogger("easyocr").setLevel(logging.FATAL)
logging.getLogger("torch").setLevel(logging.FATAL)


reader = easyocr.Reader(['en'], gpu=False)                           # Creates english OCR model & disables CUDA warning


CAPTURE_DIR = Path.cwd() / "captures"


images = list(CAPTURE_DIR.glob("*.jpg"))                             # Gets latest image saved by camera.py
if not images:
    print("No images found in captures directory.")
    raise SystemExit()

IMAGE_PATH = max(images, key=lambda p: p.stat().st_mtime)

print(f"\nUsing image: {IMAGE_PATH.resolve()}")



results = reader.readtext(str(IMAGE_PATH))                           # Reads the image
word = [text for (_, text, _) in results] if results else []         # Makes it to return the text part (bounding box, text, score)

#print("\neasyOCR output:", word)


if not word:                                                         # Exit if nothing is found
    print("No text detected")
    raise SystemExit()



valid_words = []                                                      # list of words detected
for t in word:                                                        # loops through each letter of "word"
    cleaned = t.strip()
    if cleaned.isalpha():                                             # Checks if "word" is only letters
        valid_words.append(cleaned)

if not valid_words:
    print("No valid words found")
    raise SystemExit()

print("\nWords chosen for lookup:", valid_words)


for w in valid_words:
    print(f"\nWord chosen for lookup: '{w}'")
    braille_results = translate_word(w, servo_lut)
    print_translation(braille_results)
    run_motor(braille_results)
