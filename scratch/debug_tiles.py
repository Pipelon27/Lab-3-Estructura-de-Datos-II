from settings import VT323_PATH
import pygame
import os

pygame.init()
path = r'assets\BehindTheSmile_Assets\BehindTheSmile_Assets\campus\Room_Builder_free_32x32.png'
if not os.path.exists(path):
    print(f"File not found: {path}")
    exit()

ts = pygame.image.load(path)
w, h = ts.get_size()
surf = ts.copy()
font = pygame.font.Font(VT323_PATH, 12)

# Draw grid
for x in range(0, w, 32):
    pygame.draw.line(surf, (255, 0, 0), (x, 0), (x, h), 1)
for y in range(0, h, 32):
    pygame.draw.line(surf, (255, 0, 0), (0, y), (w, y), 1)

# Draw row numbers
for y in range(0, h, 32):
    row_num = y // 32
    txt = font.render(str(row_num), True, (255, 0, 0))
    # Draw a small background for the number to make it readable
    pygame.draw.rect(surf, (255, 255, 255), (2, y + 2, txt.get_width() + 2, txt.get_height()))
    surf.blit(txt, (3, y + 2))

save_path = r'assets\UI\tileset_with_grid.png'
pygame.image.save(surf, save_path)
print(f"Saved to {save_path}")
