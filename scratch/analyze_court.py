import pygame
import numpy as np
from PIL import Image

def analyze_court():
    img_path = "assets/Baloncesto.png"
    img = Image.open(img_path)
    
    # Court: cols = 108..531 (width 424), rows = 3..349 (height 347)
    court = img.crop((108, 3, 532, 350))
    court.save("scratch/court_crop.png")
    
    # Left Hoop: Hoop 2 (cols = 4..91, rows = 163..289, height = 127, width = 88)
    left_hoop = img.crop((4, 163, 92, 290))
    left_hoop.save("scratch/left_hoop_crop.png")
    
    # Right Hoop: Hoop 1 (cols = 4..91, rows = 3..129, height = 127, width = 88)
    right_hoop = img.crop((4, 3, 92, 130))
    right_hoop.save("scratch/right_hoop_crop.png")
    
    print("Cropped images saved to scratch folder.")

if __name__ == "__main__":
    analyze_court()
