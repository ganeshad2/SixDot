import easyocr
import warnings
import os
import logging

# mutes the warnings
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
warnings.filterwarnings("ignore")
logging.getLogger("easyocr").setLevel(logging.FATAL)  # hides EasyOCR logs
logging.getLogger("torch").setLevel(logging.FATAL)    # hides PyTorch logs


reader = easyocr.Reader(['en'], gpu=False)  # disables CUDA warning


# folder of test images
image_folder = 'Test Images'

# loops through all jpg files (sorted by name)
for filename in sorted(os.listdir(image_folder)):
    if filename.lower().endswith('.jpg'):
        image_path = os.path.join(image_folder, filename)
        result = reader.readtext(image_path)

        print(f"\nImage: {filename}")
        print("easyOCR Output:")
        
        if result:
            for (bbox, text, prob) in result:
                print(text)
        else:
            print("(no text detected)")