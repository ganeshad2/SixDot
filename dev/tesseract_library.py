from PIL import Image
import pytesseract
import os

# Location of Tesseract executable
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

text = pytesseract.image_to_string(Image.open('Test Images/Test image 9.3.jpg')).strip()
print("tesseract OCR Output:")
print(text)
