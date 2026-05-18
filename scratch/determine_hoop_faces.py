import pygame
import sys

def main():
    pygame.init()
    # Create a headless screen
    screen = pygame.display.set_mode((1800, 1300), pygame.HIDDEN)
    
    # Load sheet
    sheet = pygame.image.load("assets/Baloncesto.png").convert_alpha()
    
    # Slices
    left_hoop_orig = sheet.subsurface(pygame.Rect(4, 163, 88, 127))
    right_hoop_orig = sheet.subsurface(pygame.Rect(4, 3, 88, 127))
    
    # Scale to 1.5x: 88 * 1.5 = 132, 127 * 1.5 = 190
    left_hoop = pygame.transform.scale(left_hoop_orig, (132, 190))
    right_hoop = pygame.transform.scale(right_hoop_orig, (132, 190))
    
    court_orig = sheet.subsurface(pygame.Rect(108, 3, 424, 347))
    court = pygame.transform.scale(court_orig, (848, 694))
    
    # Draw onto a test surface
    surf = pygame.Surface((1800, 1300))
    surf.fill((62, 56, 50)) # wood/background
    
    court_x = 476
    court_y = 258
    surf.blit(court, (court_x, court_y))
    surf.blit(left_hoop, (court_x - 45, court_y + 252))
    surf.blit(right_hoop, (court_x + 761, court_y + 252))
    
    # Save
    pygame.image.save(surf, "artifacts/coliseum_horizontal_court_render.png")
    print("Headless 1.5x render saved successfully!")
    
    # Count pixels
    import numpy as np
    from PIL import Image
    
    img = Image.open("artifacts/coliseum_horizontal_court_render.png")
    arr = np.array(img)
    bg_color = np.array([62, 56, 50])
    
    # Left hoop area: x = 476 - 45 = 431..563, y = 258 + 252 = 510..700
    left_hoop_region = arr[510:700, 431:563, :3]
    left_hoop_opaque = np.sum(np.any(left_hoop_region != bg_color, axis=2))
    print(f"Left hoop opaque pixels at 1.5x: {left_hoop_opaque}")
    
    # Right hoop area: x = 476 + 761 = 1237..1369, y = 510..700
    right_hoop_region = arr[510:700, 1237:1369, :3]
    right_hoop_opaque = np.sum(np.any(right_hoop_region != bg_color, axis=2))
    print(f"Right hoop opaque pixels at 1.5x: {right_hoop_opaque}")

if __name__ == "__main__":
    main()
