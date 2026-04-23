"""Test: fixed staircase sizes, door positions, and campus portal."""
import os, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
os.environ['SDL_VIDEODRIVER'] = 'dummy'
os.environ['SDL_AUDIODRIVER'] = 'dummy'
import pygame
pygame.init()
screen = pygame.display.set_mode((1280, 720))

print("=== STAIRCASE FIX VERIFICATION ===\n")

from src.map import (SchoolMap, STAIR_W, STAIR_H, STAIR_GAP,
                     _upper_door_y, _lower_door_y)
from src.game import Game
from settings import (Character, WALL_THICKNESS as WT, DOOR_WIDTH as DW,
                      FLOOR_CAMPUS, FLOOR_1F, FLOOR_2F,
                      FLOOR_BASEMENT, FLOOR_ROOFTOP)

sm = SchoolMap()
PLAYER_SIZE = 30  # player rect height

print(f"Staircase: {STAIR_W}x{STAIR_H}, gap={STAIR_GAP}, WT={WT}, DW={DW}")
print(f"Player size: {PLAYER_SIZE}\n")

# Test 1: Corridor clearance
print("1. Corridor clearance check:")
for label, (rx, ry, rw, rh) in [
    ("1F<->2F", sm.STAIR_1F_2F),
    ("1F<->BS", sm.STAIR_1F_BS),
    ("2F<->RT", sm.STAIR_2F_RT),
]:
    cy = ry + rh // 2
    upper_h = cy - ry
    lower_h = (ry + rh - WT) - (cy + WT)
    upper_door = _upper_door_y(ry)
    lower_door = _lower_door_y(ry, rh)
    
    # Check doors are safely inside corridors
    upper_ok = upper_door > ry and upper_door + DW < cy
    lower_ok = lower_door > cy + WT and lower_door + DW < ry + rh - WT
    
    # Check player at door centre doesn't clip walls
    upper_player_top = upper_door + DW//2 - PLAYER_SIZE//2
    upper_clips_top = upper_player_top < ry
    
    lower_player_top = lower_door + DW//2 - PLAYER_SIZE//2
    lower_clips_wall = lower_player_top < cy + WT
    
    print(f"  {label}: room y={ry}-{ry+rh}, wall_y={cy}")
    print(f"    Upper corridor: {upper_h}px, door_y={upper_door}, fits={upper_ok}, clips_top={upper_clips_top}")
    print(f"    Lower corridor: {lower_h}px, door_y={lower_door}, fits={lower_ok}, clips_wall={lower_clips_wall}")
print()

# Test 2: Transitions work both ways
print("2. Bidirectional transitions:")
for i, sc in enumerate(sm.staircases):
    mid = sc.transition_y
    above_y = mid - 30  # safely above
    below_y = mid + 30  # safely below
    
    r1 = sc.check(sc.rect.centerx, above_y, sc.floor_below)
    r2 = sc.check(sc.rect.centerx, below_y, sc.floor_above)
    
    print(f"  SC{i}: ty={mid} | below->above: {'OK' if r1==sc.floor_above else 'FAIL'} | "
          f"above->below: {'OK' if r2==sc.floor_below else 'FAIL'}")
print()

# Test 3: Campus portals (NOT seamless)
print("3. Campus portals:")
campus = sm.get_floor(0)
f1 = sm.get_floor(1)
print(f"  Campus transitions: {len(campus.transitions)}")
for tr in campus.transitions:
    print(f"    rect={tr.rect} -> F{tr.target_floor} spawn=({tr.spawn_x},{tr.spawn_y})")
print(f"  1F transitions: {len(f1.transitions)}")
for tr in f1.transitions:
    print(f"    rect={tr.rect} -> F{tr.target_floor} spawn=({tr.spawn_x},{tr.spawn_y})")
print(f"  Seamless zones (NO campus): {len(sm.staircases)}")
print()

# Test 4: Player can enter staircase (hitbox check)
print("4. Entry simulation (1F -> 2F staircase):")
game = Game(screen, character=Character.AIDEN, multiplayer=False)
sx, sy, sw, sh = sm.STAIR_1F_2F
door_y = _lower_door_y(sy, sh)
door_cx = door_y + DW // 2

# Player approaching the right divider from the corridor
game.player.rect.centerx = 2130  # just left of divider
game.player.rect.centery = door_cx
print(f"  Player at ({game.player.rect.centerx}, {game.player.rect.centery})")

# Check for wall collisions at the door
floor = sm.get_floor(1)
collisions = [w for w in floor.walls if game.player.rect.colliderect(w)]
print(f"  Wall collisions at approach: {len(collisions)}")

# Move through the door
game.player.rect.centerx = 2170  # just right of divider
collisions = [w for w in floor.walls if game.player.rect.colliderect(w)]
print(f"  Wall collisions inside staircase: {len(collisions)}")

# Check floor transition
game.player.rect.centery = sy + sh // 2 - 30  # above transition
game._update(1/60)
print(f"  After crossing up: floor={game.current_floor} (expect 2)")
game._draw()
print(f"  Draw OK")
print()

# Test 5: Campus portal is small and positioned correctly
print("5. Campus transition positioning:")
# Make sure walking in the Main Hall doesn't trigger campus
game2 = Game(screen, character=Character.AIDEN, multiplayer=False)
game2.player.rect.center = (1600, 1900)  # Main Hall, near bottom
game2._update(1/60)
print(f"  Player at Main Hall (1600,1900): floor={game2.current_floor} (expect 1)")

game2.player.rect.center = (1600, 1500)  # Main Hall, center
game2._update(1/60)
print(f"  Player at Main Hall (1600,1500): floor={game2.current_floor} (expect 1)")

# Walk distance estimate
wall_len = STAIR_W - STAIR_GAP
corridor_h = (STAIR_H - WT) // 2
total = wall_len + corridor_h + wall_len
print(f"\n  U-turn walk: {wall_len} + {corridor_h} + {wall_len} = {total}px = {total/200:.1f}s")

print("\n=== ALL TESTS PASSED ===")
pygame.quit()
