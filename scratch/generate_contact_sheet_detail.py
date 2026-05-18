import os
from PIL import Image, ImageDraw, ImageFont

def main():
    img_path = "assets/13_School_32x32.png"
    img = Image.open(img_path)
    w, h = img.size
    tile_size = 32

    # We want rows 60 to 95. That's 36 rows.
    start_row = 60
    end_row = 95
    rows_to_crop = end_row - start_row
    
    # Create a nice contact sheet with labels
    sheet_w = 32 * tile_size + 100
    sheet_h = rows_to_crop * tile_size + 100
    sheet = Image.new("RGBA", (sheet_w, sheet_h), (30, 30, 30, 255))
    draw = ImageDraw.Draw(sheet)
    
    try:
        font = ImageFont.load_default()
    except Exception:
        font = None
        
    # Draw top labels (column numbers)
    for c in range(32):
        x = c * tile_size + 60
        draw.text((x + 8, 10), f"{c:02d}", fill=(255, 255, 255, 255), font=font)
        draw.line([(x, 30), (x, sheet_h - 30)], fill=(60, 60, 60, 100), width=1)
    
    # Draw left labels (row numbers) and paste tiles
    for r_offset, r in enumerate(range(start_row, end_row)):
        y = r_offset * tile_size + 40
        draw.text((10, y + 8), f"Row {r:03d}", fill=(255, 255, 255, 255), font=font)
        draw.line([(60, y), (sheet_w - 30, y)], fill=(60, 60, 60, 100), width=1)
        
        # Crop and paste row
        row_crop = img.crop((0, r * tile_size, w, (r + 1) * tile_size))
        sheet.paste(row_crop, (60, y), row_crop)
        
    # Draw final border lines
    draw.line([(60, 30), (32 * tile_size + 60, 30)], fill=(255, 255, 255, 255), width=2)
    draw.line([(60, 30), (60, sheet_h - 60)], fill=(255, 255, 255, 255), width=2)

    os.makedirs("artifacts", exist_ok=True)
    sheet.save("artifacts/basketball_contact_sheet.png")
    print("Detailed contact sheet saved to artifacts/basketball_contact_sheet.png")

if __name__ == "__main__":
    main()
