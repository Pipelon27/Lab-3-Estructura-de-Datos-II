import os
from PIL import Image, ImageDraw, ImageFont

def main():
    img_path = "assets/13_School_32x32.png"
    img = Image.open(img_path)
    tile_size = 32

    # Zoom into columns 20 to 31, rows 83 to 95
    c_start, c_end = 20, 32
    r_start, r_end = 83, 96
    
    w_tiles = c_end - c_start
    h_tiles = r_end - r_start
    
    sheet_w = w_tiles * tile_size + 80
    sheet_h = h_tiles * tile_size + 80
    sheet = Image.new("RGBA", (sheet_w, sheet_h), (40, 40, 40, 255))
    draw = ImageDraw.Draw(sheet)
    
    try:
        font = ImageFont.load_default()
    except Exception:
        font = None
        
    for c_offset, c in enumerate(range(c_start, c_end)):
        x = c_offset * tile_size + 60
        draw.text((x + 8, 10), f"{c:02d}", fill=(255, 255, 255, 255), font=font)
        draw.line([(x, 30), (x, sheet_h - 40)], fill=(70, 70, 70, 255), width=1)
        
    for r_offset, r in enumerate(range(r_start, r_end)):
        y = r_offset * tile_size + 40
        draw.text((10, y + 8), f"Row {r:02d}", fill=(255, 255, 255, 255), font=font)
        draw.line([(60, y), (sheet_w - 20, y)], fill=(70, 70, 70, 255), width=1)
        
        crop_area = img.crop((c_start * tile_size, r * tile_size, c_end * tile_size, (r + 1) * tile_size))
        sheet.paste(crop_area, (60, y), crop_area)
        
    draw.line([(60, 30), (w_tiles * tile_size + 60, 30)], fill=(255, 255, 255, 255), width=2)
    draw.line([(60, 30), (60, sheet_h - 40)], fill=(255, 255, 255, 255), width=2)

    os.makedirs("artifacts", exist_ok=True)
    sheet.save("artifacts/detailed_hoops.png")
    print("Detailed hoops contact sheet saved to artifacts/detailed_hoops.png")

if __name__ == "__main__":
    main()
