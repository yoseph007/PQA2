
import cv2
import numpy as np
import pytesseract
from PIL import Image
import os

print("OCR Test Script")
print("--------------")

# Check pytesseract version
print(f"Pytesseract version: {pytesseract.__version__}")

# Create a simple test image with text
img = np.ones((100, 300), dtype=np.uint8) * 255
cv2.putText(img, "Hello OCR", (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 0), 2)

# Save the image temporarily
cv2.imwrite("test_ocr_image.png", img)

# Perform OCR
try:
    # First try with default tesseract path
    text = pytesseract.image_to_string(Image.open("test_ocr_image.png"))
    print("OCR Result:", text)
except Exception as e:
    print(f"OCR Error: {e}")
    
    # Try with explicit path for Windows users
    try:
        pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
        text = pytesseract.image_to_string(Image.open("test_ocr_image.png"))
        print("OCR Result with explicit path:", text)
    except Exception as e2:
        print(f"OCR Error with explicit path: {e2}")

# Clean up
if os.path.exists("test_ocr_image.png"):
    os.remove("test_ocr_image.png")

print("--------------")
print("OCR test completed")
