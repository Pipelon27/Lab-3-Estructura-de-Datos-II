"""
PHONE SYSTEM - README
=====================

Complete in-game smartphone for "Behind the Smile"
Designed for bullying narrative mechanics


QUICK START
===========

1. COPY FILES
   ✓ src/phone.py
   ✓ src/phone_integration.py
   ✓ src/phone_examples.py (reference)

2. INTEGRATE INTO src/game.py
   
   In Game.__init__():
   ────────────────────
   from src.phone import Phone
   from src.phone_integration import PhoneIntegrationManager
   
   self.phone = Phone(self.screen)
   self.phone_integration = PhoneIntegrationManager(self.phone)
   self.KEY_PHONE = pygame.K_k
   
   
   In Game.update(dt):
   ────────────────────
   self.phone.update(dt)
   
   if self._phone_sync_counter % 30 == 0:
       self.phone_integration.sync_missions_to_phone(
           self.mission_manager.missions
       )
   
   
   In Game.draw():
   ────────────────────
   self.phone.draw()
   self.phone.draw_hud_icon()
   
   
   In Game.handle_input(event):
   ────────────────────────────
   if self.phone.handle_input(event):
       return
   
   if event.type == pygame.KEYDOWN:
       if event.key == self.KEY_PHONE:
           self.phone.toggle_phone()
   
3. USE IN YOUR GAME
   ────────────────
   See PHONE_INTEGRATION_GUIDE.md or src/phone_examples.py


FILES
=====

Core System:
  src/phone.py
    • Phone class (UI rendering, animation, data)
    • SocialPost, TextMessage, AcademicTask, ScheduleEvent classes
    • PhoneState, PhoneApp enums
    • 650+ lines, fully documented

Integration Layer:
  src/phone_integration.py
    • PhoneIntegrationManager class
    • Converts game events → phone notifications
    • Tracks bullying incidents
    • 250+ lines, fully documented

Reference & Examples:
  src/phone_examples.py
    • 12 practical code snippets
    • Stress test utilities
    • Integration patterns

Documentation:
  PHONE_SYSTEM_DESIGN.md
    • 400+ lines of design spec
    • Game mechanics, narrative structure
    • Visual design, data persistence
    • Future expansions

  PHONE_INTEGRATION_GUIDE.md
    • Step-by-step integration
    • Copy-paste code examples
    • Complete flow scenarios

  README_PHONE.md (this file)
    • Quick start guide
    • API reference
    • Common use cases


FEATURES
========

✓ Non-invasive overlay (1/4 screen, bottom-right)
✓ Fluent open/close animation
✓ 4 integrated apps:
   • Academic Platform (task tracker)
   • Social Feed (bullying narrative hub)
   • Messages (NPC conversations)
   • Schedule (time management)
✓ Bullying mechanics:
   • Anonymous posts
   • Victim detection
   • Reputation consequences
   • Incident escalation tracking
✓ Narrative integration:
   • Affects game endings
   • Influences NPC relationships
   • Reactive to player choices
   • Non-game-breaking


API REFERENCE
=============

PHONE CLASS
──────────

Constructor:
  Phone(screen: pygame.Surface)

Main Methods:
  toggle_phone()
    • Open or close the phone
  
  update(dt: float)
    • Update animation (call every frame)
  
  draw()
    • Render phone to screen (call every frame)
  
  draw_hud_icon()
    • Render icon in HUD when closed
  
  handle_input(event: pygame.event.Event) -> bool
    • Handle keyboard/mouse input
    • Returns True if input consumed
  
  add_social_post(post: SocialPost)
    • Add post to social feed
  
  add_text_message(npc_id: str, message: TextMessage)
    • Add text message from NPC
  
  add_academic_task(task: AcademicTask)
    • Add task to academic platform
  
  update_academic_task(task_id: str, **kwargs)
    • Update task properties (status, progress)
  
  set_schedule_events(events: list[ScheduleEvent])
    • Set daily schedule
  
  get_unread_messages_count() -> int
    • Count unread messages
  
  mark_messages_read(npc_id: str)
    • Mark NPC's messages as read

Properties:
  state: PhoneState
    • CLOSED, OPENING, OPEN, CLOSING
  
  current_app: PhoneApp
    • ACADEMIC, SOCIAL, MESSAGES, SCHEDULE
  
  is_visible: bool
    • Whether phone is rendering
  
  animation_progress: float
    • 0.0 (closed) to 1.0 (open)


PHONE INTEGRATION MANAGER CLASS
────────────────────────────────

Constructor:
  PhoneIntegrationManager(phone: Phone)

Mission ↔ Academic Sync:
  sync_missions_to_phone(missions: list)
    • Convert game missions to phone tasks
    • Call periodically (every 30 frames recommended)
  
  mission_completed_callback(mission_id: str, mission_title: str)
    • Mark task complete when mission finishes

Reputation ↔ Social Feed:
  create_social_post(
      content: str,
      author_npc_id: Optional[str] = None,
      author_name: str = "Desconocido",
      is_anonymous: bool = False,
      affects_reputation: bool = False,
      reputation_target: Optional[str] = None,
      image_tag: Optional[str] = None,
  ) -> SocialPost
    • Create post in feed
    • Returns created post
  
  bullying_incident(
      bully_npc_id: str,
      victim_npc_id: str,
      incident_type: str,
      is_anonymous: bool = True,
  )
    • Log bullying incident
    • Updates feed + tracking
  
  like_post(post_id: str)
    • Like a post (affects reputation)

NPC Dialogue ↔ Messages:
  send_text_message(
      npc_id: str,
      npc_name: str,
      content: str,
      is_response: bool = False,
  ) -> TextMessage
    • Send NPC message to player
    • Returns created message
  
  get_npc_conversations() -> dict
    • Get all conversations by NPC

Schedule:
  set_daily_schedule(day_schedule: list[tuple])
    • Set schedule from game phases

Events:
  check_phone_driven_events() -> list[dict]
    • Check if phone activity triggered events
    • Bullying escalation, etc.

Reports:
  get_bullying_report() -> dict
    • Get summary of bullying for ending
    • Keys:
      - total_incidents
      - most_bullied
      - most_bullied_count
      - unique_victims
      - anonymous_posts_count


DATA STRUCTURES
───────────────

SocialPost:
  id: str
  author: str
  author_npc_id: Optional[str]  # None = anonymous
  content: str
  timestamp: str
  is_anonymous: bool
  likes: int
  mentions: list[str]
  image_tag: Optional[str]  # emoji tag
  affects_reputation: bool
  reputation_target: Optional[str]

TextMessage:
  id: str
  sender_npc_id: str
  sender_name: str
  content: str
  timestamp: str
  is_read: bool
  attachment: Optional[str]

AcademicTask:
  id: str
  title: str
  description: str
  issuer: str
  status: str  # "pending", "in_progress", "completed"
  deadline: Optional[str]
  progress: float  # 0.0 to 1.0
  is_main_mission: bool

ScheduleEvent:
  hour: int
  name: str
  location: str
  description: str


COMMON USE CASES
================

1. CREATE A BULLYING POST
   ─────────────────────

   game.phone_integration.create_social_post(
       content="Ej, mira cómo se viste Lena",
       author_npc_id=None,
       author_name="Anónimo",
       is_anonymous=True,
       affects_reputation=True,
       reputation_target="Lena",
       image_tag="📸",
   )


2. NPC SENDS MESSAGE
   ─────────────────

   game.phone_integration.send_text_message(
       npc_id="lena",
       npc_name="Lena",
       content="¿Viste lo que publicaron? No aguanto más...",
   )


3. LOG BULLYING INCIDENT
   ────────────────────

   game.phone_integration.bullying_incident(
       bully_npc_id="bully_01",
       victim_npc_id="lena",
       incident_type="post",
       is_anonymous=True,
   )


4. SYNC MISSIONS TO PHONE
   ─────────────────────

   game.phone_integration.sync_missions_to_phone(
       game.mission_manager.missions
   )


5. CHECK BULLYING REPORT
   ─────────────────────

   report = game.phone_integration.get_bullying_report()
   if report['total_incidents'] > 5:
       game.trigger_ending("bullying_escalation")


6. MARK MESSAGE READ
   ──────────────────

   game.phone.mark_messages_read("lena")


DESIGN DECISIONS
================

WHY NON-INVASIVE?
  • Game doesn't pause when phone opens
  • Represents modern teen distraction
  • Narrative consequences persist
  • Immersion maintained

WHY ANONYMOUS POSTS?
  • Mirrors real cyberbullying
  • Creates moral ambiguity
  • Player feels uncertainty
  • Drives investigation narrative

WHY 4 APPS ONLY?
  • Each serves specific narrative purpose
  • Avoids feature bloat
  • Mirrors real teenager focus
  • Easier to design/balance

WHY PHONE AFFECTS ENDING?
  • Phone is core mechanic, not decoration
  • Phone usage = moral choices
  • Creates multiple ending paths
  • Encourages replayability

WHY INTEGRATE WITH MISSIONS?
  • Synchronizes game state
  • No information duplicated
  • Tasks feel real (tracked by authority)
  • Automatic updates when missions change


PERFORMANCE NOTES
=================

Memory: ~88 objects per day
  • 20 posts
  • 50 messages
  • 10 tasks
  • 8 schedule events

CPU: Minimal overhead
  • Fonts cached, not recreated
  • Mission sync: every 30 frames
  • Animation: simple easing function
  • Rendering: only visible items drawn

Scaling:
  • Tested with 100+ posts (still fluid)
  • No performance issues expected
  • Can cache old posts if needed


TROUBLESHOOTING
===============

PROBLEM: Phone doesn't open
SOLUTION:
  • Check KEY_PHONE is set correctly in game.py
  • Verify phone.toggle_phone() is called
  • Check that phone.handle_input() is reached in event loop

PROBLEM: Phone shows no tasks
SOLUTION:
  • Ensure sync_missions_to_phone() called in update loop
  • Check missions have visible_on_phone=True
  • Missions need npc_issuer field

PROBLEM: Posts don't affect reputation
SOLUTION:
  • Check affects_reputation=True when creating post
  • Set reputation_target to NPC name
  • Integrate with your reputation system

PROBLEM: Animation jerky
SOLUTION:
  • Check phone.update(dt) called with correct dt
  • Verify draw() called every frame
  • Check frame rate isn't capped too low

PROBLEM: Messages not appearing
SOLUTION:
  • Verify send_text_message() called with correct npc_id
  • Check phone.handle_input() not consuming event
  • Mark as read: phone.mark_messages_read(npc_id)


CUSTOMIZATION
=============

Colors:
  Modify in src/phone.py constants:
  • PHONE_WIDTH, PHONE_HEIGHT
  • PHONE_X, PHONE_Y
  • PHONE_OPEN_SPEED, PHONE_CLOSE_SPEED

Fonts:
  In Phone.__init__():
  • font_app_title
  • font_content_sm, font_content_md
  • font_hint

Behavior:
  In PhoneIntegrationManager:
  • Threshold for bullying escalation (line ~190)
  • Reputation modifiers (line ~240)
  • Post decay/aging (future feature)


ROADMAP
=======

Phase 1 (Current):
  ✓ Core phone system
  ✓ 4 main apps
  ✓ Bullying tracking
  ✓ Basic integration

Phase 2 (Recommended):
  □ Comment threads on posts
  □ Block/report functionality
  □ Group chats
  □ Photo capture (evidence gathering)

Phase 3 (Advanced):
  □ Phone mini-games
  □ Achievement badges
  □ Settings app
  □ Notification center


SUPPORT
=======

For detailed implementation:
  • See PHONE_INTEGRATION_GUIDE.md
  • Reference PHONE_SYSTEM_DESIGN.md
  • Study src/phone_examples.py
  • Check source code comments

Questions or issues:
  • Review the 12 examples in phone_examples.py
  • Cross-reference with PHONE_SYSTEM_DESIGN.md
  • Debug with print_phone_status() utility


VERSION
=======

Phone System v1.0
Compatible with: Pygame 2.5.0+
Last Updated: 2026-05-03


LICENSE
=======

This phone system is part of "Behind the Smile"
[Your project license here]


CREDITS
=======

Design: Inspired by GTA V phone system, adapted for school narrative
Implementation: Fully custom for bullying-focused mechanics
"""
