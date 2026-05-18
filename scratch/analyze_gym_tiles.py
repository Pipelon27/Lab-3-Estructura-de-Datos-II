from PIL import Image
import numpy as np

def main():
    img_path = "assets/13_School_32x32.png"
    img = Image.open(img_path)
    arr = np.array(img)
    tile_size = 32

    # We will print tiles that are props (have semi-transparency or transparency at corners)
    print("Classifying gym tiles (rows 60-95):")
    for r in range(60, 95):
        for c in range(32):
            tile = arr[r*tile_size:(r+1)*tile_size, c*tile_size:(c+1)*tile_size, :]
            alpha = tile[:, :, 3]
            opaque_count = np.sum(alpha > 200)
            transparent_count = np.sum(alpha < 50)
            
            if opaque_count > 0:
                rgb = tile[:, :, :3]
                # Is it a solid floor tile? (Fully opaque, no transparent pixels)
                if transparent_count == 0:
                    # Let's check if it's the light orange wood floor
                    # Gym floor has a lot of orange/yellow/brown hues: R > 150, G > 100, B < 120
                    wood_floor = np.all((rgb[:, :, 0] > 140) & (rgb[:, :, 1] > 90) & (rgb[:, :, 2] < 120))
                    if wood_floor:
                        # Solid gym floor tile!
                        pass
                else:
                    # It has transparency, so it is a prop or a tile with transparent background!
                    # Let's check for hoops!
                    # Basketball hoop rim is orange-red.
                    # Basketball board is white/transparent/grey.
                    # Base of the hoop is metal/wood.
                    # Let's count specific color ranges in the tile:
                    orange = np.sum((rgb[:, :, 0] > 180) & (rgb[:, :, 1] > 50) & (rgb[:, :, 1] < 140) & (rgb[:, :, 2] < 80))
                    white = np.sum((rgb[:, :, 0] > 220) & (rgb[:, :, 1] > 220) & (rgb[:, :, 2] > 220))
                    grey = np.sum((rgb[:, :, 0] > 100) & (rgb[:, :, 0] < 200) & (rgb[:, :, 1] > 100) & (rgb[:, :, 1] < 200) & (rgb[:, :, 2] > 100) & (rgb[:, :, 2] < 200))
                    
                    if orange > 20 or white > 20:
                        # Let's check if it's a court line or a hoop
                        # Hoops are usually vertical structures spanning 2 or 3 tiles high.
                        # Let's print candidate hoop/prop tiles!
                        print(f"Prop Candidate - Tile ({c}, {r}): opaque={opaque_count}, transparent={transparent_count}, orange={orange}, white={white}, grey={grey}")

if __name__ == "__main__":
    main()
