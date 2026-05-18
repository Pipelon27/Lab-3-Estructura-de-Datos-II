import numpy as np
from PIL import Image

def main():
    img_path = "artifacts/coliseum_horizontal_court_render.png"
    img = Image.open(img_path)
    arr = np.array(img)
    
    # Let's crop the court region: y = 258..952, x = 476..1324
    court_region = arr[258:952, 476:1324, :3]
    
    # Reshape and find unique colors
    pixels = court_region.reshape(-1, 3)
    unique, counts = np.unique(pixels, axis=0, return_counts=True)
    
    # Sort and print
    indices = np.argsort(-counts)
    print("Unique colors in the rendered court region:")
    for i in range(min(15, len(indices))):
        idx = indices[i]
        print(f"  Color {unique[idx]}: count={counts[idx]}")

if __name__ == "__main__":
    main()
