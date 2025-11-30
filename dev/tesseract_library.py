from PIL import Image
import pytesseract
import os

# Location of Tesseract executable
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

text = pytesseract.image_to_string(Image.open('dev/Test Images/Test image 1.1.jpg')).strip()
print("tesseract OCR Output:")
print(text)
