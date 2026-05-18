import numpy as np
from PIL import Image

def main():
    img_path = "assets/Baloncesto.png"
    img = Image.open(img_path)
    arr = np.array(img)
    
    # Let's crop the court region: cols = 108..531, rows = 3..349
    court = arr[3:350, 108:532, :3]
    h, w, c = court.shape
    
    # Reshape to a list of pixels
    pixels = court.reshape(-1, 3)
    # Find unique colors and their counts
    unique, counts = np.unique(pixels, axis=0, return_counts=True)
    
    # Sort by counts descending
    indices = np.argsort(-counts)
    print("Top 10 most common colors in court:")
    for i in range(min(10, len(indices))):
        idx = indices[i]
        print(f"  Color {unique[idx]}: count={counts[idx]}")

if __name__ == "__main__":
    main()
