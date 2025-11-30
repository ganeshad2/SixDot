from paddleocr import PaddleOCR
import warnings
import logging
import os

# mutes the warnings
warnings.filterwarnings("ignore")
logging.getLogger("ppocr").setLevel(logging.FATAL)
logging.getLogger("paddleocr").setLevel(logging.FATAL)

# OCR engine
reader = PaddleOCR(lang='en')   


image_folder = 'dev/Test Images'

# loops through all jpg files (sorted by name)
for filename in sorted(os.listdir(image_folder)):
    if filename.lower().endswith('.jpg'):
        image_path = os.path.join(image_folder, filename)
        result = reader.ocr(image_path, cls=True) # cls helps with rotation correction 

        print(f"\nImage: {filename}")
        print("paddleOCR Output:")

        if result and result[0]:
            for line in result[0]:
                print(line[1][0])
        else:
            print("(no text detected)")