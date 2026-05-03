"""
PHONE SYSTEM INTEGRATION GUIDE
==============================

Quick reference for integrating the phone system into your game loop.

FILE STRUCTURE:
  src/phone.py                  — Core phone UI and data structures
  src/phone_integration.py      — Integration layer with game systems
  [This file]                   — Integration examples

SETUP IN GAME.PY
================
"""

# ══════════════════════════════════════════════════════════════
#  1. INITIALIZATION (in Game.__init__)
# ══════════════════════════════════════════════════════════════

# Add to Game.__init__:
"""
from src.phone import Phone
from src.phone_integration import PhoneIntegrationManager

class Game:
    def __init__(self, ...):
        # ... existing code ...
        
        # Initialize phone system
        self.phone = Phone(self.screen)
        self.phone_integration = PhoneIntegrationManager(self.phone)
        
        # Bind KEY_PHONE to toggle phone
        self.KEY_PHONE = pygame.K_k  # can be customized in settings.py
"""


# ══════════════════════════════════════════════════════════════
#  2. MAIN LOOP INTEGRATION (in Game.update() and Game.draw())
# ══════════════════════════════════════════════════════════════

# Add to Game.update():
"""
def update(self, dt: float):
    # ... existing code ...
    
    # Update phone animation
    self.phone.update(dt)
    
    # Sync missions to phone every few frames (not every frame for performance)
    if self.frame_count % 30 == 0:  # Every ~0.5 seconds at 60 FPS
        self.phone_integration.sync_missions_to_phone(self.mission_manager.missions)
    
    # Check for phone-driven narrative events
    phone_events = self.phone_integration.check_phone_driven_events()
    for event in phone_events:
        self._handle_phone_event(event)
"""

# Add to Game.draw():
"""
def draw(self):
    # ... draw game world ...
    
    # Draw phone (overlay)
    self.phone.draw()
    
    # Draw phone HUD icon (if phone is closed)
    self.phone.draw_hud_icon()
"""


# ══════════════════════════════════════════════════════════════
#  3. INPUT HANDLING (in Game.handle_input())
# ══════════════════════════════════════════════════════════════

# Add to Game.handle_input():
"""
def handle_input(self, event: pygame.event.Event):
    # ... existing input code ...
    
    # Handle phone toggle
    if event.type == pygame.KEYDOWN:
        if event.key == self.KEY_PHONE:
            self.phone.toggle_phone()
            return  # consume input
    
    # Let phone handle its own input (clicks, scrolling, etc.)
    if self.phone.handle_input(event):
        return  # input consumed by phone
    
    # ... rest of input handling ...
"""

# Add to Game.handle_mouse_click():
"""
def handle_mouse_click(self, pos):
    # Check if clicking on phone HUD icon
    if self.phone.state == PhoneState.CLOSED:
        if self.phone.hud_icon_rect.collidepoint(pos):
            self.phone.toggle_phone()
            return True
    
    return False
"""


# ══════════════════════════════════════════════════════════════
#  4. MISSION → ACADEMIC TASK SYNC
# ══════════════════════════════════════════════════════════════

"""
When creating missions, add these metadata fields:

from src.mission import Mission, MissionStatus

new_mission = Mission(
    id="stop_bullying_01",
    title="Investigar los rumores",
    description="Habla con los NPCs para averiguar quién está acosando a Lena",
    
    # PHONE FIELDS:
    visible_on_phone=True,        # Show in academic app
    npc_issuer="Profesor García",  # Who issued the task
    phone_progress=0.0,           # 0.0 to 1.0 progress indicator
    
    priority=1,  # 0 = side quest, 1+ = main quest (shown prominently)
)

mission_manager.add_mission(new_mission)
"""


# ══════════════════════════════════════════════════════════════
#  5. BULLYING MECHANICS → SOCIAL FEED
# ══════════════════════════════════════════════════════════════

"""
When bullying occurs in-game, log it to the phone social feed:

# Example: NPC posts anonymous content about player
self.phone_integration.create_social_post(
    content="Ej, mira a Aiden, ni siquiera puede defenderse",
    author_name="Anónimo",
    author_npc_id=None,  # anonymous
    is_anonymous=True,
    affects_reputation=True,
    reputation_target="Aiden",
    image_tag="📸",  # optional visual tag
)

# Example: Bullying incident escalation
self.phone_integration.bullying_incident(
    bully_npc_id="bully_01",
    victim_npc_id="Lena",
    incident_type="post",  # "post", "rumor", "taunt", "exclusion"
    is_anonymous=True,
)

# Then check consequences:
report = self.phone_integration.get_bullying_report()
print(f"Total bullying incidents: {report['total_incidents']}")
if report['total_incidents'] >= 5:
    # Trigger an ending or major event
    self.trigger_ending("bullying_escalation")
"""


# ══════════════════════════════════════════════════════════════
#  6. NPC MESSAGING → TEXT SYSTEM
# ══════════════════════════════════════════════════════════════

"""
When NPCs want to send the player a message:

# Example: Reaction to player's action
if player_defended_npc:
    self.phone_integration.send_text_message(
        npc_id="lena",
        npc_name="Lena",
        content="Gracias por defenderme. Significa mucho. 💙",
    )

# Example: NPC asking for help
self.phone_integration.send_text_message(
    npc_id="maya",
    npc_name="Maya",
    content="Ey, ¿vas a llegar a clase? Los bullies están aquí de nuevo...",
)

# Get all conversations:
conversations = self.phone_integration.get_npc_conversations()
for npc_id, messages in conversations.items():
    print(f"Conversation with {npc_id}: {len(messages)} messages")

# Mark messages as read:
self.phone.mark_messages_read("lena")
"""


# ══════════════════════════════════════════════════════════════
#  7. DAILY SCHEDULE
# ══════════════════════════════════════════════════════════════

"""
Set the daily schedule when the day starts:

# In Game.new_day() or similar:
def new_day(self):
    # ... existing code ...
    
    # Update phone schedule
    self.phone_integration.set_daily_schedule(self.day_schedule)

# The phone will automatically convert game time phases to readable schedule
"""


# ══════════════════════════════════════════════════════════════
#  8. REPUTATION CONSEQUENCES ON PHONE
# ══════════════════════════════════════════════════════════════

"""
When reputation changes, reflect it on the phone:

# Example: Player defended someone
self.reputation_system.add_reputation("Lena", 20)
self.phone_integration.send_text_message(
    npc_id="lena",
    npc_name="Lena",
    content="Viste? Todavía hay gente decente en este lugar 🙏",
)

# Example: Player did something unpopular
self.reputation_system.add_reputation("Popular Group", -30)
self.phone_integration.create_social_post(
    content="Aiden es un soplón. No lo confíen.",
    author_npc_id=None,
    is_anonymous=True,
    affects_reputation=True,
    reputation_target="Aiden",
)
"""


# ══════════════════════════════════════════════════════════════
#  9. EVENT CALLBACKS
# ══════════════════════════════════════════════════════════════

"""
Hook into game events to update phone:

# When mission completes:
def on_mission_completed(self, mission_id, mission_title):
    self.phone_integration.mission_completed_callback(mission_id, mission_title)

# When a key dialogue choice is made:
def on_dialogue_choice(self, choice_id, npc_id):
    # Update missions/tasks
    self.phone_integration.sync_missions_to_phone(self.mission_manager.missions)
    
    # Optionally send follow-up text
    if choice_id == "defended_npc":
        self.phone_integration.send_text_message(
            npc_id=npc_id,
            npc_name=self.npc_manager.get_npc(npc_id).name,
            content="No lo olvidaré, en serio.",
        )
"""


# ══════════════════════════════════════════════════════════════
#  10. SETTINGS.PY ADDITIONS
# ══════════════════════════════════════════════════════════════

"""
Add these to settings.py:

# Phone controls
KEY_PHONE = pygame.K_k  # Press K to open phone

# Phone UI colors (already exist but can be customized)
# UI_BG, UI_PANEL, UI_BORDER, UI_ACCENT, UI_TEXT, UI_TEXT_DIM
"""


# ══════════════════════════════════════════════════════════════
#  COMPLETE EXAMPLE: Mini Tutorial Flow
# ══════════════════════════════════════════════════════════════

"""
Scenario: Player starts day, receives first bullying post, then must investigate.

# 1. Day starts
def start_day(self):
    self.phone_integration.set_daily_schedule(self.day_schedule)

# 2. Bullying incident happens
def on_npc_bullied(self, bully_npc, victim_npc):
    self.phone_integration.bullying_incident(
        bully_npc_id=bully_npc.id,
        victim_npc_id=victim_npc.id,
        incident_type="post",
        is_anonymous=True,
    )
    
    # NPC asks for help via text
    self.phone_integration.send_text_message(
        npc_id=victim_npc.id,
        npc_name=victim_npc.name,
        content="¿Viste lo que compartieron de mí? Por favor... ayuda.",
    )
    
    # Add investigation task
    new_mission = Mission(
        id="investigate_bully_" + bully_npc.id,
        title="Investigar el acoso",
        description="Descubre quién está acosando a " + victim_npc.name,
        visible_on_phone=True,
        npc_issuer=victim_npc.name,
        priority=2,
    )
    self.mission_manager.add_mission(new_mission)
    self.phone_integration.sync_missions_to_phone(self.mission_manager.missions)

# 3. Player can check phone to see:
#    - New message from victim
#    - Anonymous post in social feed
#    - New academic task (investigation)
#    - Updated schedule
#
# 4. Player talks to NPCs, gathers evidence
# 5. When evidence found, investigation task progresses
self.phone_integration.phone.update_academic_task(
    f"task_investigate_bully_{bully_npc.id}",
    progress=0.5,
)

# 6. When player confronts bully or reports, task completes
self.phone_integration.mission_completed_callback(
    f"investigate_bully_{bully_npc.id}",
    "Investigación completada"
)

# 7. Reputation changes reflect on feed and messages
self.reputation_system.add_reputation(victim_npc.name, 50)
self.phone_integration.send_text_message(
    npc_id=victim_npc.id,
    npc_name=victim_npc.name,
    content="Eres increíble. Hace tiempo nadie me ayudaba 💙",
)
"""
