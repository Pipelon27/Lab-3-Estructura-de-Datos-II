import os
import pygame
from PIL import Image, ImageDraw, ImageFont

def main():
    img_path = "assets/13_School_32x32.png"
    if not os.path.exists(img_path):
        print(f"Error: {img_path} not found!")
        return

    img = Image.open(img_path)
    w, h = img.size
    print(f"Loaded image {img_path} with size: {w}x{h}")

    tile_size = 32
    cols = w // tile_size
    rows = h // tile_size
    print(f"Tileset grid: {cols} cols x {rows} rows")

    # Let's save slices of 10 rows each to see them clearly
    output_dir = "artifacts/tileset_slices"
    os.makedirs(output_dir, exist_ok=True)

    # Use a basic font or default
    try:
        font = ImageFont.load_default()
    except Exception:
        font = None

    # Let's search for interesting rows. Basketball stuff is usually in the outdoor/gym section.
    # Gym equipment might be in a specific section.
    # Let's save 12 slice images, each containing 10 rows of the sheet, with grid lines and labels.
    for slice_idx in range((rows + 9) // 10):
        start_row = slice_idx * 10
        end_row = min(start_row + 10, rows)
        slice_h = (end_row - start_row) * tile_size

        # Create a new image to draw the slice with labels
        slice_img = Image.new("RGBA", (w + 64, slice_h + 32), (50, 50, 50, 255))
        draw = ImageDraw.Draw(slice_img)

        # Draw columns labels at top
        for c in range(cols):
            x = c * tile_size + 48
            draw.text((x + 8, 8), str(c), fill=(255, 255, 255, 255), font=font)

        # Draw the actual tiles
        cropped = img.crop((0, start_row * tile_size, w, end_row * tile_size))
        slice_img.paste(cropped, (48, 24), cropped)

        # Draw row labels and grid lines
        for r_offset, r in enumerate(range(start_row, end_row)):
            y = r_offset * tile_size + 24
            # Draw row label
            draw.text((8, y + 10), str(r), fill=(255, 255, 255, 255), font=font)
            # Draw horizontal line
            draw.line([(48, y), (w + 48, y)], fill=(100, 100, 100, 100), width=1)

        for c in range(cols + 1):
            x = c * tile_size + 48
            draw.line([(x, 24), (x, slice_h + 24)], fill=(100, 100, 100, 100), width=1)

        # Save slice
        slice_img.save(os.path.join(output_dir, f"slice_rows_{start_row}_to_{end_row-1}.png"))
    
    print("Slices saved successfully to artifacts/tileset_slices/")

if __name__ == "__main__":
    main()
