"""
PHONE SYSTEM ARCHITECTURE OVERVIEW
==================================

Visual guide to how all components connect and interact.
"""

# ══════════════════════════════════════════════════════════════
#  SYSTEM ARCHITECTURE DIAGRAM
# ══════════════════════════════════════════════════════════════

"""
                          ┌─────────────────┐
                          │  GAME SYSTEMS   │
                          └────────┬────────┘
                                   │
                ┌──────────────────┼──────────────────┐
                │                  │                  │
          ┌─────▼────┐      ┌──────▼─────┐    ┌──────▼──────┐
          │ Missions │      │Reputation  │    │   NPCs      │
          │ Manager  │      │ System     │    │ Dialogue    │
          └─────┬────┘      └──────┬─────┘    └──────┬──────┘
                │                  │                  │
                │                  └──────────┬───────┘
                │                             │
                │   ┌───────────────────────────────────┐
                │   │ PHONE INTEGRATION MANAGER         │
                │   │ (Bidirectional Bridge)            │
                │   │ • Converts missions → tasks      │
                │   │ • Tracks bullying incidents      │
                │   │ • Routes NPC messages            │
                │   │ • Syncs reputation effects       │
                └──►├──────────────────────────────────┤
                    │ Creates:                          │
                    │ • SocialPost                       │
                    │ • TextMessage                      │
                    │ • AcademicTask                    │
                    │ • ScheduleEvent                    │
                    └──────────┬─────────────────────────┘
                               │
                    ┌──────────▼──────────┐
                    │   PHONE SYSTEM      │
                    │  (UI + Data Layer)  │
                    │                     │
                    │ ┌─────────────────┐ │
                    │ │ PhoneState      │ │
                    │ │ • CLOSED        │ │
                    │ │ • OPENING       │ │
                    │ │ • OPEN          │ │
                    │ │ • CLOSING       │ │
                    │ └─────────────────┘ │
                    │                     │
                    │ ┌─────────────────┐ │
                    │ │ 4 Apps:         │ │
                    │ │ • Academic      │ │
                    │ │ • Social Feed   │ │
                    │ │ • Messages      │ │
                    │ │ • Schedule      │ │
                    │ └─────────────────┘ │
                    │                     │
                    │ ┌─────────────────┐ │
                    │ │ Rendering:      │ │
                    │ │ • Phone bezel   │ │
                    │ │ • Animation     │ │
                    │ │ • HUD icon      │ │
                    │ │ • Content       │ │
                    │ └─────────────────┘ │
                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐
                    │  PLAYER SCREEN      │
                    │  (Overlay Display)  │
                    │                     │
                    │ 1/4 Bottom-Right    │
                    │ • Smooth animation  │
                    │ • Non-intrusive     │
                    │ • Always clickable  │
                    └─────────────────────┘


# ══════════════════════════════════════════════════════════════
#  DATA FLOW EXAMPLE: BULLYING INCIDENT
# ══════════════════════════════════════════════════════════════

"""
SCENARIO: An NPC gets bullied by another NPC

STEP 1 - GAME EVENT
─────────────────

In Game.update():
  │
  ├─ NPC_A makes fun of NPC_B
  │  (dialogue choice, in-game encounter)
  │
  └─► Game calls:
      phone_integration.bullying_incident(
          bully_npc_id="npc_a",
          victim_npc_id="npc_b",
          incident_type="post",
          is_anonymous=True,
      )


STEP 2 - INTEGRATION PROCESSING
────────────────────────────────

PhoneIntegrationManager processes:
  │
  ├─ Creates SocialPost object
  │  author_npc_id: None (anonymous)
  │  author: "Anónimo"
  │  content: "[bullying content]"
  │  is_anonymous: True
  │
  ├─ Adds to phone.social_posts list
  │
  ├─ Logs incident in bullying_incidents tracker
  │  → Used for ending calculation
  │
  └─► Creates NPC message:
      phone_integration.send_text_message(
          npc_id="npc_b",
          npc_name="[Victim name]",
          content="Did you see what they posted? 😞"
      )


STEP 3 - PHONE UI UPDATE
────────────────────────

Phone automatically updates:
  │
  ├─ Social Feed App:
  │  • New post appears at top
  │  • Dark background (anonymous)
  │  • ❤️ counter: 0 (no likes yet)
  │
  ├─ Messages App:
  │  • New conversation from victim
  │  • Message marked unread
  │  • Badge updates: "1"
  │
  ├─ HUD Icon:
  │  • Unread badge shows "1"
  │  • Color changes (alert)
  │
  └─► Next update() call:
      Phone renders everything


STEP 4 - PLAYER INTERACTION
───────────────────────────

Player opens phone (K key), sees:

  A) SOCIAL FEED:
     "Anónimo: [bullying content]"
     ❤️ 0
     
     Player can:
     • Like post (reputation impact)
     • Ignore
     • Report (future feature)

  B) MESSAGES:
     Victim: "Did you see what they posted? 😞"
     
     Player can:
     • Read (marks unread=False)
     • Message back (creates new message)
     • Ignore

  C) ACADEMIC APP:
     Investigation task appears:
     "Investigate [victim] bullying"
     de: [Victim] | pendiente | 0%


STEP 5 - CONSEQUENCES
─────────────────────

Based on player action:

  If LIKE POST:
  ─────────────
  • phone.like_post(post_id)
  • post.likes: 0 → 1
  • reputation_system.add(victim_npc_id, -10)
  • reputation_system.add("bullies", +5)
  • Social feed shows 1 like
  • Next similar posts get more likes (mob effect)
  • Victim sees player liked post → trusts player less

  If MESSAGE VICTIM:
  ──────────────────
  • New message added to victim's history
  • victim_npc.relationship += 5
  • social_posts get positive responses
  • Victim may like supportive posts
  • System shows community support

  If IGNORE:
  ──────────
  • No immediate change
  • Phone records player saw post but did nothing
  • Victim isolation increases (next incident)
  • Another post appears within hours
  • Cycle repeats with more likes
  • Eventually victim disappears (ending: victim_isolated)


STEP 6 - ENDING IMPACT
──────────────────────

At game end:

  bullying_report = phone_integration.get_bullying_report()
  
  report contains:
  {
    'total_incidents': 1,
    'most_bullied': 'npc_b',
    'most_bullied_count': 1,
    'unique_victims': 1,
    'anonymous_posts_count': 1,
  }
  
  Combined with reputation system:
  • If victim reputation > 0: hero ending
  • If victim reputation < 0: complicit ending
  • If bullying_report.total_incidents > 5: escalation
  
  Ending narrative reflects player's choices


# ══════════════════════════════════════════════════════════════
#  UI STATE MACHINE
# ══════════════════════════════════════════════════════════════

"""
                    ┌─────────────┐
                    │   CLOSED    │◄────────┐
                    │   (0.0)     │         │
                    └──────┬──────┘         │
                           │               │
                    toggle_phone()    animation done
                           │               │
                    ┌──────▼──────┐        │
                    │  OPENING    │────────┤
                    │ (0.0→1.0)   │        │
                    └──────┬──────┘        │
                           │               │
                    animation done         │
                           │               │
                    ┌──────▼──────┐        │
                    │    OPEN     │        │
                    │   (1.0)     │        │
                    └──────┬──────┘        │
                           │               │
                    toggle_phone()    toggle_phone()
                           │               │
                    ┌──────▼──────┐        │
                    │  CLOSING    │────────┘
                    │ (1.0→0.0)   │
                    └──────┬──────┘
                           │
                    animation done
                           │
                           ◄───────────┘

Properties managed during transitions:
  • animation_progress: float (0.0 to 1.0)
  • is_visible: bool (renders only if True)
  • Easing function: ease_out_cubic (smooth animation)
  • Position: Moves from bottom-right corner
  • Scale: Grows/shrinks as animation progresses


# ══════════════════════════════════════════════════════════════
#  APP NAVIGATION
# ══════════════════════════════════════════════════════════════

"""
            ┌──────────────────────────────┐
            │  PHONE CONTENT AREA          │
            │                              │
            │  ┌────────────────────────┐  │
            │  │ Current App Content    │  │
            │  │ (scrollable if needed) │  │
            │  └────────────────────────┘  │
            │                              │
            │  ┌──────────────────────────┐│
            │  │📚│📢│💬│🕐│                ││ ← App bar
            │  │ 1 │ 2 │ 3 │ 4 │           ││
            │  └──────────────────────────┘│
            └──────────────────────────────┘
             ▲            ▲            ▲     ▲
             │            │            │     │
          Academic      Social       Messages Schedule
          Platform      Feed         

Click app icon → update current_app → content instantly changes


# ══════════════════════════════════════════════════════════════
#  CONTENT STRUCTURE BY APP
# ══════════════════════════════════════════════════════════════

"""
ACADEMIC PLATFORM
─────────────────

Header: "Académico"
Content list:
  ├─ ● Title
  │  de: Teacher
  │  Progress bar: 0%
  │
  ├─ ◆ Title
  │  de: NPC
  │  Progress bar: 40%
  │
  └─ ✓ Title
     de: Teacher
     Progress bar: 100%

Color coding:
  ● = pending (yellow dot)
  ◆ = in_progress (blue dot)
  ✓ = completed (green dot)


SOCIAL FEED
──────────

Header: "Red Social"
Feed list (newest first):
  ├─ [Light] User: "Post content..." ❤️ 5
  │
  ├─ [Dark] Anónimo: "Anonymous post..." ❤️ 12
  │
  ├─ [Light] User: "Normal post..." ❤️ 3
  │
  └─ [Dark] Anónimo: "Bullying post..." ❤️ 8

Color:
  Light = normal post
  Dark = anonymous post (bullying indicator)


MESSAGES
────────

Header: "Mensajes"
Conversations:
  ├─ [Highlighted] NPC_1: "Last message..." (unread)
  │  
  ├─ [ Normal  ] NPC_2: "Last message..."
  │
  └─ [ Normal  ] NPC_3: "Last message..."

Click to open thread → full message history


SCHEDULE
─────────

Header: "Horario"
Events:
  ├─ 08:00 Llegada (Entrada)
  │
  ├─ 09:00 Clase (Aula 202)
  │
  ├─ 11:00 Descanso (Patio)
  │
  └─ ...next events...

Color:
  Blue = current class
  Normal = future
  Faded = past


# ══════════════════════════════════════════════════════════════
#  RENDERING HIERARCHY
# ══════════════════════════════════════════════════════════════

"""
Game.draw():
  │
  ├─► Draw game world
  │   (background, map, NPCs, etc.)
  │
  ├─► Draw game UI
  │   (HUD, player stats, etc.)
  │
  ├─► phone.draw_hud_icon()
  │   │
  │   └─► If phone.state == CLOSED:
  │       Draw icon + badge
  │       Position: SCREEN_WIDTH - 50, SCREEN_HEIGHT - 50
  │
  ├─► phone.draw()
  │   │
  │   └─► If animation_progress > 0:
  │       │
  │       ├─ Calculate eased progress
  │       │  (smooth animation curve)
  │       │
  │       ├─► _draw_phone_body()
  │       │   • Bezel
  │       │   • Notch
  │       │   • Screen background
  │       │   • Time display
  │       │
  │       └─► _draw_phone_content() [if progress > 0.3]
  │           │
  │           ├─► _draw_app_bar()
  │           │   • 4 app icons
  │           │   • Active indicator
  │           │
  │           └─► _draw_[app_type]_app()
  │               • Academic: task list
  │               • Social: feed
  │               • Messages: conversations
  │               • Schedule: events


# ══════════════════════════════════════════════════════════════
#  DATA STRUCTURE RELATIONSHIPS
# ══════════════════════════════════════════════════════════════

"""
┌──────────────┐
│    PHONE     │
├──────────────┤
│ • state      │
│ • animation  │
│ • current_app├──┐
│              │  │
│ Collections: │  │
│ • posts[]    │  ├─── Contains instances of:
│ • messages{} │  │
│ • tasks[]    │  │
│ • events[]   │  │
└──────────────┘  │
                  │
    ┌─────────────┴─────────────────┬──────────────┬─────────────┐
    │                               │              │             │
    ▼                               ▼              ▼             ▼
┌─────────────┐           ┌──────────────────┐┌─────────┐┌──────────────┐
│ SocialPost  │           │ TextMessage      ││Academic │║ ScheduleEvent║
├─────────────┤           ├──────────────────┤│ Task    │╠══════════════╣
│ id: str     │           │ id: str          ││ Task    │║ hour: int    ║
│ author      │           │ sender_npc_id    │├─────────┤║ name: str    ║
│ author_npc  │           │ sender_name      ││ id: str ║║ location     ║
│ content     │           │ content          ││ title   ║║ description  ║
│ timestamp   │           │ timestamp        ││ issuer  ║╚══════════════╝
│ is_anonymous│           │ is_read: bool    ││ status  ║
│ likes: int  │           │ attachment       ││ deadline║
│ mentions[]  │           └──────────────────┘│ progress║
│ image_tag   │                               └─────────┘
│ affects_rep │
│ rep_target  │
└─────────────┘

Linking:
  • author_npc_id links SocialPost to NPC in reputation system
  • sender_npc_id links TextMessage to NPC
  • id fields link to mission IDs and NPC IDs
  • Phone uses these to update game systems


# ══════════════════════════════════════════════════════════════
#  INTEGRATION TOUCHPOINTS
# ══════════════════════════════════════════════════════════════

"""
Where phone connects to game systems:

MISSION SYSTEM
──────────────
Mission → AcademicTask (display)
Mission update → Phone update
Mission complete → Phone update + text from NPC

REPUTATION SYSTEM
─────────────────
Player likes post → reputation change
Player messages NPC → reputation change
Bullying incident → reputation impact on victim

NPC SYSTEM
──────────
NPC reacts to game event → text message
NPC opinion shifts → affects posts about them
NPC isolation → affects game ending

ENDING SYSTEM
─────────────
Bullying report → ending calculation
Phone usage → reputation modifiers
Moral choices reflected in ending


# ══════════════════════════════════════════════════════════════
#  ANIMATION EASING VISUALIZATION
# ══════════════════════════════════════════════════════════════

"""
ease_out_cubic(t):
  • Returns smooth animation curve
  • 0.0 (start) → 1.0 (end)
  • Used for both scale and alpha
  
Visual:
  ^
  │      ╱╱
  │    ╱╱
  │  ╱
  │╱
  └─────────────►
  
Phone opens:
  • Starts small in corner
  • Scales up smoothly
  • Eases to final size
  • Feels natural (not linear)

Phone closes:
  • Reverse animation
  • Scales down
  • Returns to corner
  • Faster close than open


# ══════════════════════════════════════════════════════════════
#  COMPLETE GAME LOOP FLOW
# ══════════════════════════════════════════════════════════════

"""
MAIN GAME LOOP:
───────────────

while game_running:
    
    [1] EVENT HANDLING
    ──────────────────
    for event in pygame.event.get():
        │
        ├─ phone.handle_input(event)  ← Phone consumes input first
        │
        ├─ If K key: phone.toggle_phone()
        │
        └─ Rest of game input
    
    
    [2] UPDATE
    ──────────
    dt = clock.tick(60) / 1000.0
    
    game.update(dt):
        │
        ├─ Update world state
        │
        ├─ phone.update(dt)  ← Update animation
        │
        ├─ Every 30 frames:
        │  phone_integration.sync_missions_to_phone(...)
        │
        ├─ Check phone events
        │  → Handle bullying escalation, etc.
        │
        └─ Update game systems
    
    
    [3] RENDERING
    ──────────────
    game.draw():
        │
        ├─ screen.fill(black)
        │
        ├─ Draw world
        │
        ├─ Draw game UI
        │
        ├─ phone.draw()  ← Renders on top
        │
        ├─ phone.draw_hud_icon()
        │
        └─ pygame.display.flip()
    
    
    [4] REPEAT


# ══════════════════════════════════════════════════════════════
#  SUMMARY
# ══════════════════════════════════════════════════════════════

The phone system is a complete, integrated subsystem that:

✓ Sits on top of game UI (overlay, non-intrusive)
✓ Displays information from all game systems
✓ Allows player interaction (likes, messages, etc.)
✓ Reports consequences back to game systems
✓ Influences game ending through accumulated choices
✓ Renders smoothly with easing animations
✓ Requires minimal integration (few hook points)

The key design principle: Phone is REACTIVE, not ACTIVE.
  • Game events create phone content
  • Player interacts with content
  • Interactions have consequences
  • Phone is feedback system, not controller

This makes it feel natural (part of game world) rather than
mechanical (artificial interface).
"""
