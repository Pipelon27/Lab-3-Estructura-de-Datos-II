import os
from PIL import Image

def main():
    img_path = "assets/Baloncesto.png"
    if not os.path.exists(img_path):
        print(f"File {img_path} not found!")
        return
        
    img = Image.open(img_path)
    print(f"Baloncesto.png dimensions: {img.size}")
    print(f"Format: {img.format}, Mode: {img.mode}")

if __name__ == "__main__":
    main()
