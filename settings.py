"""
settings.py - Global configuration for Behind the Smile
=========================================================
Contains all constants, colors, resolution, FPS, asset paths,
enumerations, key bindings, and zone/day-schedule definitions.
Every other module imports from here so that tweaking a value
in one place propagates everywhere.
"""

import os
import pygame
from enum import Enum, auto

# ──────────────────────────────────────────────────────────────
#  DISPLAY
# ──────────────────────────────────────────────────────────────
SCREEN_WIDTH  = 1280
SCREEN_HEIGHT = 720
FPS           = 60
TITLE         = "Behind the Smile"

# ──────────────────────────────────────────────────────────────
#  TILE / GRID
# ──────────────────────────────────────────────────────────────
TILE_SIZE = 48

# ──────────────────────────────────────────────────────────────
#  ZONE RENDERING  (placeholder room sizes)
# ──────────────────────────────────────────────────────────────
ZONE_WIDTH  = 1280
ZONE_HEIGHT = 720

# ──────────────────────────────────────────────────────────────
#  PLAYER DEFAULTS
# ──────────────────────────────────────────────────────────────
PLAYER_SIZE        = 40
PLAYER_SPEED       = 4
PLAYER_SPRINT_SPEED = 7
PLAYER_MAX_HEALTH  = 100
PLAYER_MAX_STAMINA = 100
STAMINA_REGEN_RATE = 0.5
STAMINA_SPRINT_COST = 1.0
DASH_STAMINA_COST  = 25
DASH_SPEED         = 12
DASH_DURATION      = 10          # frames

# ──────────────────────────────────────────────────────────────
#  COMBAT
# ──────────────────────────────────────────────────────────────
LIGHT_ATTACK_DAMAGE     = 10
HEAVY_ATTACK_DAMAGE     = 25
COMBO_DAMAGE            = 35
LIGHT_ATTACK_STAMINA    = 10
HEAVY_ATTACK_STAMINA    = 20
COMBO_STAMINA           = 30
BLOCK_DAMAGE_REDUCTION  = 0.7
ATTACK_RANGE            = 60
ATTACK_COOLDOWN         = 20     # frames
COMBO_WINDOW            = 30     # frames to chain hits

# ──────────────────────────────────────────────────────────────
#  NPC
# ──────────────────────────────────────────────────────────────
NPC_SIZE              = 36
NPC_SPEED             = 2
NPC_INTERACTION_RANGE = 80

# ──────────────────────────────────────────────────────────────
#  XP / LEVELING
# ──────────────────────────────────────────────────────────────
XP_PER_LEVEL         = 100
SKILL_POINT_PER_LEVEL = 1

# ──────────────────────────────────────────────────────────────
#  NETWORK
# ──────────────────────────────────────────────────────────────
DEFAULT_HOST  = "127.0.0.1"
DEFAULT_PORT  = 5555
BUFFER_SIZE   = 4096
HEADER_SIZE   = 4               # bytes for length-prefix

# ──────────────────────────────────────────────────────────────
#  PATHS  (all relative to this file's directory)
# ──────────────────────────────────────────────────────────────
BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR  = os.path.join(BASE_DIR, "assets")
SPRITES_DIR = os.path.join(ASSETS_DIR, "sprites")
TILES_DIR   = os.path.join(ASSETS_DIR, "tiles")
MAPS_DIR    = os.path.join(ASSETS_DIR, "maps")
SOUNDS_DIR  = os.path.join(ASSETS_DIR, "sounds")
FONTS_DIR   = os.path.join(ASSETS_DIR, "fonts")
DATA_DIR    = os.path.join(BASE_DIR, "data")
SRC_DIR     = os.path.join(BASE_DIR, "src")

# ──────────────────────────────────────────────────────────────
#  COLOUR PALETTE
# ──────────────────────────────────────────────────────────────
# Core
BLACK       = (0,   0,   0)
WHITE       = (255, 255, 255)
DARK_GRAY   = (30,  30,  35)
MEDIUM_GRAY = (60,  60,  70)
LIGHT_GRAY  = (180, 180, 190)

# UI chrome
UI_BG       = (20,  20,  30)
UI_PANEL    = (35,  35,  50)
UI_BORDER   = (80,  80,  120)
UI_ACCENT   = (100, 200, 255)
UI_TEXT      = (240, 240, 245)
UI_TEXT_DIM  = (150, 150, 170)

# Bars
HEALTH_RED   = (220, 50,  50)
HEALTH_BG    = (80,  20,  20)
STAMINA_YELLOW = (230, 200, 50)
STAMINA_BG   = (80,  70,  20)
XP_BLUE      = (50,  120, 220)
XP_BG        = (20,  40,  80)

# Characters (placeholder)
AIDEN_COLOR   = (70,  130, 230)
AIDEN_OUTLINE = (50,  100, 200)
LENA_COLOR    = (180, 70,  220)
LENA_OUTLINE  = (150, 50,  190)

# Social groups
GROUP_COLORS = {
    "athletes":  (230, 120, 50),
    "tech_club": (50,  200, 150),
    "populars":  (230, 60,  120),
    "academics": (80,  150, 230),
    "rebels":    (200, 50,  50),
    "outsiders": (130, 130, 140),
}

# Zone backgrounds
ZONE_MAIN_HALL     = (45, 45, 65)
ZONE_SPORTS_ARENA  = (40, 60, 40)
ZONE_COMPUTER_LAB  = (30, 40, 60)
ZONE_CAFETERIA     = (60, 50, 35)
ZONE_LIBRARY       = (50, 40, 45)
ZONE_ROOFTOP       = (35, 45, 55)
ZONE_BASEMENT      = (25, 25, 30)

# Notification colours
NOTIF_SUCCESS = (50,  200, 100)
NOTIF_WARNING = (230, 180, 50)
NOTIF_ERROR   = (220, 60,  60)
NOTIF_INFO    = (80,  160, 240)

# ──────────────────────────────────────────────────────────────
#  ENUMERATIONS
# ──────────────────────────────────────────────────────────────

class GameState(Enum):
    """All possible high-level game states."""
    MENU             = auto()
    CHARACTER_SELECT = auto()
    PLAYING          = auto()
    PAUSED           = auto()
    DIALOGUE         = auto()
    COMBAT           = auto()
    HACKING          = auto()
    PINGPONG         = auto()
    TRADING          = auto()
    INVENTORY_SCREEN = auto()
    SKILL_TREE_SCREEN = auto()
    HELP             = auto()
    GAME_OVER        = auto()
    VICTORY          = auto()
    MAP              = auto()
    WALLET           = auto()


class Character(Enum):
    """Playable characters."""
    AIDEN = "aiden"
    LENA  = "lena"


class SocialGroup(Enum):
    """Social groups at Ravenside High."""
    ATHLETES  = "athletes"
    TECH_CLUB = "tech_club"
    POPULARS  = "populars"
    ACADEMICS = "academics"
    REBELS    = "rebels"
    OUTSIDERS = "outsiders"


class Direction(Enum):
    """Cardinal movement directions."""
    UP    = "up"
    DOWN  = "down"
    LEFT  = "left"
    RIGHT = "right"


class ItemCategory(Enum):
    """Inventory item categories."""
    SNACK   = "snack"
    MONEY   = "money"
    KEY     = "key"
    USB     = "usb"
    SPECIAL = "special"
    WEAPON  = "weapon"


class MissionStatus(Enum):
    """Mission progress states."""
    LOCKED     = "locked"
    AVAILABLE  = "available"
    ACTIVE     = "active"
    COMPLETED  = "completed"
    FAILED     = "failed"


class DayPhase(Enum):
    """Phases of the school day."""
    ARRIVAL    = "arrival"
    CLASS_1    = "class_1"
    BREAK_1    = "break_1"
    CLASS_2    = "class_2"
    LUNCH      = "lunch"
    ACTIVITIES = "activities"
    DEPARTURE  = "departure"
    NIGHT      = "night"


class Ending(Enum):
    """Possible game endings."""
    GOOD    = "good"
    NEUTRAL = "neutral"
    DARK    = "dark"

# ──────────────────────────────────────────────────────────────
#  KEY BINDINGS
# ──────────────────────────────────────────────────────────────
KEY_UP           = pygame.K_w
KEY_DOWN         = pygame.K_s
KEY_LEFT         = pygame.K_a
KEY_RIGHT        = pygame.K_d

KEY_INTERACT     = pygame.K_SPACE
KEY_USE          = pygame.K_e
KEY_INVENTORY    = pygame.K_i
KEY_SKILL_TREE   = pygame.K_k
KEY_HELP         = pygame.K_h
KEY_PAUSE        = pygame.K_ESCAPE

# Combat (Aiden)
KEY_LIGHT_ATTACK = pygame.K_j
KEY_HEAVY_ATTACK = pygame.K_u
KEY_BLOCK        = pygame.K_l
# Dash is bound to Space only (disable Shift/Ctrl dash aliases)
KEY_DASH         = pygame.K_SPACE
KEY_DASH_ALT     = KEY_DASH
KEY_DASH_ALT2    = KEY_DASH

# Hacking (Lena)
KEY_HACK         = pygame.K_v
KEY_MAP          = pygame.K_m

# ──────────────────────────────────────────────────────────────
#  FLOOR / MAP SYSTEM
# ──────────────────────────────────────────────────────────────
WALL_THICKNESS = 16
DOOR_WIDTH     = 80

FLOOR_CAMPUS   = 0
FLOOR_1F       = 1
FLOOR_2F       = 2
FLOOR_BASEMENT = 3
FLOOR_ROOFTOP  = 4

FLOOR_NAMES = ["Campus", "1st Floor", "2nd Floor", "Basement", "Rooftop"]
FLOOR_SIZES = {
    0: (4000, 3000),
    1: (3200, 2400),
    2: (3200, 2400),
    3: (3200, 2400),     # same size as 1F for seamless stairs
    4: (3200, 2400),     # same size for seamless stairs
}
FLOOR_BG_COLORS = {
    0: (35, 50, 35),
    1: (42, 42, 58),
    2: (48, 44, 52),
    3: (22, 22, 28),
    4: (25, 40, 58),     # dark sky
}

# Maps old NPC-schedule zone IDs → (floor_id, spawn_x, spawn_y)
ZONE_TO_FLOOR = {
    0: (1, 1600, 1000),    # Main Hall  → 1F
    1: (0, 3200, 650),     # Sports     → Campus coliseum
    2: (1, 530, 300),      # Comp Lab   → 1F
    3: (1, 2600, 850),     # Cafeteria  → 1F
    4: (1, 2600, 350),     # Library    → 1F
    5: (4, 1600, 1000),    # Rooftop    → Rooftop floor
    6: (3, 700, 500),      # Basement   → Basement
}

# ── legacy (kept for backward-compat with missions/objectives) ──
ZONE_NAMES = [
    "Main Hall", "Sports Arena", "Computer Lab",
    "Cafeteria", "Library", "Rooftop", "Basement",
]
ZONE_CONNECTIONS = {
    0: [1, 2, 3, 4], 1: [0, 5], 2: [0, 6],
    3: [0, 4], 4: [0, 3, 5], 5: [1, 4], 6: [2],
}
ZONE_COLORS_LIST = [
    ZONE_MAIN_HALL, ZONE_SPORTS_ARENA, ZONE_COMPUTER_LAB,
    ZONE_CAFETERIA, ZONE_LIBRARY, ZONE_ROOFTOP, ZONE_BASEMENT,
]
ZONE_DESCRIPTIONS = [
    "The central hub of Ravenside High",
    "Where athletes train and compete",
    "Rows of computers and humming servers",
    "Bustling with trays, rumours, and lunch money",
    "Quiet study hall hiding old secrets",
    "Open sky — secret meetings happen here at night",
    "Dark and restricted — the Smile Club server room",
]

# ──────────────────────────────────────────────────────────────
#  DAY SCHEDULE  (phase, duration in game-seconds)
# ──────────────────────────────────────────────────────────────
DAY_SCHEDULE = [
    (DayPhase.ARRIVAL,    60),
    (DayPhase.CLASS_1,    120),
    (DayPhase.BREAK_1,    90),
    (DayPhase.CLASS_2,    120),
    (DayPhase.LUNCH,      120),
    (DayPhase.ACTIVITIES, 150),
    (DayPhase.DEPARTURE,  60),
    (DayPhase.NIGHT,      90),
]

# ──────────────────────────────────────────────────────────────
#  MOTIVATIONAL MESSAGES
# ──────────────────────────────────────────────────────────────
MOTIVATIONAL_MESSAGES = [
    "Every voice matters. You made a difference!",
    "Standing up takes courage — and you have it!",
    "True strength is protecting others.",
    "You're changing this school, one step at a time.",
    "Kindness is the ultimate power.",
    "Behind every smile is a story worth hearing.",
    "You chose to listen. That changes everything.",
    "Real friends stand up, not stand by.",
]
