import cv2
from google.colab.patches import cv2_imshow

#from matplotlib import pyplot as plt

image_path = "/home/sixdot/Documents/git/SixDot/test_data/test1.jpeg"
image = cv2.imread(image_path)
image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
print("Grayscale Image")
cv2_imshow(gray)


