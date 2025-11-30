import os
import warnings
import logging
import easyocr

from lookup import translate_word, print_translation, run_motor, servo_lut

# mutes the warnings
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
warnings.filterwarnings("ignore")
logging.getLogger("easyocr").setLevel(logging.FATAL)
logging.getLogger("torch").setLevel(logging.FATAL)


reader = easyocr.Reader(['en'], gpu=False)                     # Creates english OCR model & disables CUDA warning


IMAGE_PATH = r"dev\Test Images\Test image 1.1.jpg"             # Changing test image
print(f"\nUsing image: {os.path.abspath(IMAGE_PATH)}")


results = reader.readtext(IMAGE_PATH)                           # Reads the image
word = [text for (_, text, _) in results] if results else []    # Makes it to return the text part (bounding box, text, score)

#print("\neasyOCR output:", word)


if not word:                                                    # Exit if nothing is found
    print("No text detected")
    raise SystemExit()


main_word = None                                                # Placeholder
for t in word:                                                  # loops through each letter of "word"
    cleaned = t.strip()
    if cleaned.isalpha() and len(cleaned) >= 2:                 # Checks if "word" in only letters and has at least 2 of them
        main_word = cleaned
        break


print(f"\nWord chosen for lookup: '{main_word}'")


braille_results = translate_word(main_word, servo_lut)
print_translation(braille_results)
run_motor(braille_results)
