from PIL import Image
import numpy as np

def main():
    crops = [
        "artifacts/hoop_test_90_92_c21_23.png",
        "artifacts/hoop_test_90_92_c24_26.png",
        "artifacts/hoop_test_93_95_c21_23.png",
        "artifacts/hoop_test_93_95_c25_27.png"
    ]

    for cpath in crops:
        img = Image.open(cpath)
        arr = np.array(img)
        h, w, c = arr.shape
        tile_size = 32
        
        print(f"\n--- Crop: {cpath} ---")
        for r_offset in range(3):
            row_slice = arr[r_offset*tile_size:(r_offset+1)*tile_size, :, :]
            alpha = row_slice[:, :, 3]
            rgb = row_slice[:, :, :3]
            
            opaque = np.sum(alpha > 100)
            orange = np.sum((rgb[:, :, 0] > 180) & (rgb[:, :, 1] > 50) & (rgb[:, :, 1] < 150) & (rgb[:, :, 2] < 80) & (alpha > 100))
            white = np.sum((rgb[:, :, 0] > 220) & (rgb[:, :, 1] > 220) & (rgb[:, :, 2] > 220) & (alpha > 100))
            grey = np.sum((rgb[:, :, 0] > 80) & (rgb[:, :, 0] < 180) & (rgb[:, :, 1] > 80) & (rgb[:, :, 1] < 180) & (rgb[:, :, 2] > 80) & (rgb[:, :, 2] < 180) & (alpha > 100))
            
            print(f"  Row {r_offset} (0-2): opaque={opaque:4d}, orange={orange:3d}, white={white:3d}, grey={grey:3d}")

if __name__ == "__main__":
    main()
