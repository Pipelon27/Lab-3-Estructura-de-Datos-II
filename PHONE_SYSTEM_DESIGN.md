"""
PHONE SYSTEM DESIGN DOCUMENT
============================

Comprehensive design spec for the school-bullying narrative phone system.
"""

# ══════════════════════════════════════════════════════════════
#  1. SYSTEM OVERVIEW
# ══════════════════════════════════════════════════════════════

"""
The phone is the PRIMARY INTERFACE for school social dynamics.
It's not decorative—it's a narrative engine for bullying mechanics.

CORE DESIGN PRINCIPLES
━━━━━━━━━━━━━━━━━━━━━━

1. NON-INVASIVE
   • Appears as overlay, doesn't pause game
   • Player can ignore it but suffers narrative consequences
   • Optional but encouraged to check

2. REAL-TIME NARRATIVE
   • Reflects story events immediately
   • Anonymous posts create paranoia and moral weight
   • Messages from bullying victims create urgency
   • Academic app tracks NPC opinion on player's choices

3. CONSEQUENCE-DRIVEN
   • Every phone interaction matters
   • Liking/dismissing posts affects reputation
   • Reading/ignoring messages changes NPC relationships
   • Task progress influences ending

4. SCHOOL-AUTHENTIC
   • Looks like Instagram/TikTok but adapted
   • Anonymous posting mirrors real cyberbullying
   • Reputation decay mirrors social dynamics
   • Schedule mirrors actual school day


INTEGRATION LAYERS
━━━━━━━━━━━━━━━━━

[Game Events]
     ↓
[PhoneIntegrationManager]  ← translates game→phone
     ↓
[Phone UI]  ← displays to player
     ↓
[Player Actions]
     ↓
[Reputation + Mission Systems]  ← consequences


# ══════════════════════════════════════════════════════════════
#  2. APP SPECIFICATIONS
# ══════════════════════════════════════════════════════════════

█ ACADEMIC PLATFORM ("Académico")
  
  Purpose: Task tracker that mirrors mission system
  
  Display:
    • List of active tasks (newest first, main missions highlighted)
    • Status indicator (dot color: yellow=pending, blue=progress, green=done)
    • Issuer name (teacher or NPC)
    • Progress bar (only for in-progress tasks)
    • Deadline (if applicable)
  
  Interaction:
    • Tap to expand → shows full description
    • Tasks auto-mark as complete when game mission completes
    • Color coding mirrors mission importance
  
  Narrative Purpose:
    • Shows that player's actions are documented
    • Creates accountability (teachers "see" what you do)
    • Some tasks are actually disguised reputation checks
    
  Example:
    ✓ Hablar con Maya sobre los rumores
      de: Prof. García | completado | 100%
    
    ◆ Encontrar evidencia del acosador
      de: Maya | en progreso | 60%
    
    ◆ Reportar el incidente
      de: Dirección | pendiente | 0%


█ SOCIAL FEED ("Red Social")

  Purpose: Primary vehicle for bullying narrative
  
  Display:
    • Chronological feed (newest first)
    • Author name OR "Anónimo" (anonymous posts appear darker)
    • Post content (max 50 chars on preview)
    • Like counter
    • Emoji tags (📸 photo, 🎥 video, ⚠️ rumor, etc.)
  
  Post Types:
    
    1. ANONYMOUS BULLYING POSTS (narrative critical)
       • Posted about player: "Ej, ¿viste a Aiden? No va al gimnasio"
       • Posted about NPCs: "Maya es patética, no tiene amigos"
       • Posted by NPC bullies OR systemic (represent peer pressure)
       • Dark background to distinguish from normal posts
       
    2. NPC REACTIONS TO PLAYER
       • "Gracias a Aiden por defender a Maya" (positive)
       • "Aiden se fue con los acosadores" (negative)
       • Reflect reputation changes
       
    3. SYSTEMIC POSTS
       • "[Icon] Prof. García: Próxima reunión de clase es importante"
       • "[Icon] Cafetería: Hoy hay pizza en la comida"
       • No reputation impact, worldbuilding
       
    4. PLAYER IMPACT POSTS
       • Posts mentioning player's choices
       • Change based on game events
       • Feedback mechanism for player actions
  
  Interaction:
    • Heart to like (affects NPC opinion)
    • Tap to see full post + comment threads (future expansion)
    • Mentions of player trigger notifications
  
  Narrative Mechanics:
    • Anonymous posts create moral ambiguity
      "Who is bullying who? Should I care?"
    • Post density reflects bullying severity
      (3 anon posts in 1 hour = escalation)
    • Never show bullying you CAUSED (unless discovered)
      Reason: Player should feel impact through NPCs, not read it directly
    • Negative posts about bullying victims attract sympathy action


█ MESSAGES ("Mensajes")

  Purpose: Intimate 1:1 conversations with NPCs
  
  Display:
    • List of conversations (active NPCs only)
    • NPC name
    • Last message preview
    • Unread indicator (highlighted background)
  
  Interaction:
    • Tap to open conversation thread
    • See full message history with timestamps
    • NPC name shows their current emotional state via emoji
      (🙁 sad, 😟 worried, 😊 happy, 😒 angry, 😐 neutral)
  
  Message Types:
    • Bullying victims reaching out (urgent tone)
    • NPC reactions to player choices ("Thanks for..." / "Why did you...")
    • Hints for solving problems
    • Dialogue alternatives that don't require face-to-face
    • Romantic subplots (if applicable)
  
  Narrative Purpose:
    • Creates parasocial relationships with NPCs
    • Direct feedback loop (player action → NPC text)
    • Can trigger missions or events
    • Represents modern teen social life
  
  Important Distinction:
    • Texts are REACTION-BASED, not initiative-based
    • NPCs don't text the player to ask for help initially
    • They text AFTER player shows care or involvement
    • Exception: Bullying victims may reach out desperately


█ SCHEDULE ("Horario")

  Purpose: Time management and immersion
  
  Display:
    • Time (24-hour format): 08:00, 09:00, etc.
    • Event name: "Clase de Matemáticas"
    • Location: "Aula 202"
    • Short description if applicable
  
  Sync with Game Time:
    • Updates in real-time as game day progresses
    • Current class highlighted (different color)
    • Completed classes fade out
  
  Narrative Purpose:
    • Grounds player in school routine
    • Justifies why player is in certain zones
    • Creates time pressure (if you're not in class, what are you doing?)
    • Optional: certain events happen at specific times


# ══════════════════════════════════════════════════════════════
#  3. BULLYING MECHANICS FRAMEWORK
# ══════════════════════════════════════════════════════════════

ANATOMY OF A BULLYING INCIDENT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. INCIDENT OCCURS (game event)
   └─ NPC A bullies NPC B
   
2. MANIFESTATION (phone updates)
   ├─ Anonymous post appears (social feed)
   ├─ Victim sends distress text (messages)
   └─ Task appears (academic platform)
   
3. PLAYER DECISION
   ├─ Ignore (reputation: all NPCs drop, especially victim)
   ├─ Like post (reputation: victim -20, bullies +10, others mixed)
   ├─ Like post + text victim "hang in there" (reputation: victim +5)
   ├─ Confront in-game (direct action, complex outcomes)
   └─ Investigate/report (academic task, long-term consequences)
   
4. ESCALATION OR RESOLUTION
   ├─ If ignored: 2-3 similar posts within 24h, victim becomes isolated
   ├─ If supported: victim gains confidence, other NPCs rally
   └─ If reported: authority action (may backfire with certain NPCs)
   
5. NARRATIVE BRANCH
   ├─ Victim ending (positive if helped, tragic if ignored)
   ├─ Bully ending (redemption or escalation)
   └─ Player ending (hero, complicit, or active bully)


REPUTATION FORMULA FOR PHONE ACTIONS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

When player likes an anonymous bullying post:
  Victim reputation: -20
  Bully (if known) reputation: +5
  Other bullies: +3 (social proof)
  Victims of other bullies: -2 (fear)
  
When player messages bullying victim:
  Victim reputation: +10
  Close friends of victim: +5
  
When player completes bullying investigation:
  Victim: +30
  Bully: -40
  Bullies' friends: -15
  Students who liked bully posts: -5 (diminishing social currency)


ENDING DETERMINATION
━━━━━━━━━━━━━━━━━

Ending is influenced by:
  • Total bullying incidents witnessed
  • Player response to each incident
  • Reputation with bullies vs victims
  • Phone behavior (what posts did player like?)
  • Tasks completed
  
Possible endings (examples):
  • "Hero": Defended multiple victims, high reputation with outcasts
  • "Complicit": Liked bullying posts, ignored victims
  • "Indifferent": Neutral reputation, no strong ties
  • "Victim": Became target of bullying yourself
  • "Bully": Actively posted anonymous bullying content
  • "Redeemed": Started as bully/neutral, became ally of victims
  • "Tragic": Bullying escalated despite efforts
  • "Changed": Atmosphere shifted from bullying-heavy to inclusive


# ══════════════════════════════════════════════════════════════
#  4. UI/UX SPECIFICATIONS
# ══════════════════════════════════════════════════════════════

VISUAL DESIGN
━━━━━━━━━━━━

Phone appearance:
  • Modern smartphone shape (rounded corners, notch at top)
  • Size: 1/4 screen width + margin (exact: PHONE_WIDTH = SCREEN_WIDTH // 4 + 40)
  • Position: Bottom-right corner, fixed
  • Colors:
    ├─ Bezel: Dark (#141414)
    ├─ Screen BG: UI_BG color
    ├─ App bar: UI_PANEL color
    ├─ Text: UI_TEXT color (white)
    ├─ Highlights: UI_ACCENT color (blue)
    └─ Dimmed: UI_TEXT_DIM color (gray)
  
  • Animation:
    ├─ Open: 0.15s easing (cubic out)
    ├─ Close: 0.10s easing
    └─ Scale from 0→1 while moving from corner inward

Post styling:
  • Normal post: Light background
  • Anonymous post: Dark background (#503C3C or similar)
  • System post: Dimmed, with icon indicator
  • Post affecting player: Highlighted border

Text styling:
  • Title: 18pt, bold
  • Content: 12-14pt
  • Metadata: 10pt, dimmed
  • Timestamps: "ahora" (now), "hace 5 min", "hace 2 horas"


INTERACTION MODEL
━━━━━━━━━━━━━━━

Open phone:
  • Press K key OR click HUD icon
  • Smooth animation (0.15s)
  
Close phone:
  • Press ESC key OR click outside
  • Smooth animation (0.10s)
  
Switch apps:
  • Click app icon in bar (bottom of phone)
  • Instant switch
  • Content scrolls to top
  
Scroll content:
  • Mouse wheel OR UP/DOWN arrows
  • Smooth scroll within app
  • Boundaries checked (no over-scroll)
  
Click post (future):
  • Expands to full view
  • Shows comments thread
  • Option to like, unlike, block author (if not anonymous)
  
Click message:
  • Opens conversation thread
  • Shows full history with sender
  • Mark as read automatically
  
Click task:
  • Expands description
  • Shows deadline if applicable
  • No interaction needed (auto-syncs with missions)


HUD ICON
━━━━━━

Position: 20px from bottom-right, above phone when closed
Display:
  • Circle with phone emoji (📱)
  • White border
  • Unread badge (red dot with count) if messages waiting
  • Color: UI_ACCENT

Behavior:
  • Always visible when phone is closed
  • Clickable to toggle open
  • Badge disappears when all messages read
  • Pulsing animation if urgent messages (optional)


# ══════════════════════════════════════════════════════════════
#  5. DATA PERSISTENCE & PROGRESSION
# ══════════════════════════════════════════════════════════════

DATA STRUCTURES
━━━━━━━━━━━━━━

SocialPost:
  id: str
  author: str
  author_npc_id: Optional[str]  # None if anonymous
  content: str
  timestamp: str
  is_anonymous: bool
  likes: int
  mentions: list[str]
  image_tag: Optional[str]  # emoji category
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
  status: "pending" | "in_progress" | "completed"
  deadline: Optional[str]
  progress: float  # 0.0 to 1.0
  is_main_mission: bool

ScheduleEvent:
  hour: int  # 0-23
  name: str
  location: str
  description: str


SAVE/LOAD
━━━━━━━━

Phone data saved in main game save file:
  • All posts (for consistency on reload)
  • All messages (conversation history preserved)
  • All tasks (sync with missions)
  • Schedule (per-day)
  • Bullying report (for ending calculation)

Recovery:
  • If mission system changes, resync phone automatically
  • If NPC deleted, remove from messaging history
  • If post author NPC deleted, mark as anonymous


# ══════════════════════════════════════════════════════════════
#  6. PERFORMANCE CONSIDERATIONS
# ══════════════════════════════════════════════════════════════

OPTIMIZATION
━━━━━━━━━━━

• Phone.draw() uses cached fonts (not recreated every frame)
• Mission sync runs every 30 frames, not every frame
• Social feed truncated to visible area only
• Message history rendered on-demand (full thread when opened)
• Scroll offset checked before rendering each item
• Animation uses easing function (calculated once per frame)


MEMORY
━━━━

Typical usage per day:
  • ~20 social posts (total)
  • ~50 messages (across all NPCs)
  • ~10 tasks (active missions)
  • ~8 schedule events

Total: ~88 objects = negligible memory impact


# ══════════════════════════════════════════════════════════════
#  7. FUTURE EXPANSIONS
# ══════════════════════════════════════════════════════════════

POTENTIAL FEATURES
━━━━━━━━━━━━━━━━━

1. CAMERA APP
   • Player can take photos of incidents
   • Photos appear as posts (evidence)
   • Can be used to report bullying

2. CAMERA ROLL
   • Photos taken during gameplay
   • Review as evidence
   • Show to authorities

3. COMMENT THREADS
   • Click post → expand to see comments
   • Player can comment (future mechanics)
   • Comments affect reputation differently

4. GROUPS/CHATS
   • Group text conversations
   • Drama escalation mechanic
   • Mob dynamics

5. NOTIFICATION CENTER
   • Push notifications for urgent messages
   • System alerts (class starting, etc.)
   • Timeline of events

6. SETTINGS
   • Mute notifications
   • Block users (hides their posts)
   • Privacy settings (affects posting visibility)

7. ACHIEVEMENTS/BADGES
   • "Peace Keeper" - resolved 3 bullying incidents
   • "Social Butterfly" - 100 likes from NPCs
   • "Truth Seeker" - found all evidence
   • "Outcasts' Friend" - high reputation with isolated NPCs

8. CUSTOM CONTENT FILTER
   • Player chooses what to see
   • Some posts only visible if close to certain NPCs
   • Private posts from bullies (need hacking skills to see)

9. PHONE MINIGAME
   • Text-based mini-quests on phone
   • Unlock by helping NPCs
   • Rewards (reputation, money, items)


# ══════════════════════════════════════════════════════════════
#  8. NARRATIVE CASE STUDIES
# ══════════════════════════════════════════════════════════════

CASE 1: DEFENDING THE VICTIM
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Day 1 - Morning:
  • Player starts, sees schedule
  • Academic app has intro tasks

Day 1 - 11:00:
  • Bullying incident: Bully posts anonymous post about Maya
  • Social feed updates with dark post
  • Maya sends text: "Did you see what they posted about me? 😞"

Player Option A (HELP):
  • Responds to Maya: "I saw it, ignore them"
  • Maya reputation: +5
  • Player checks social feed, likes post (wait, wrong action)
  
Player Option B (INVESTIGATE):
  • Doesn't respond immediately
  • Continues playing, discovers bully's identity through dialogue
  • Reports to teacher through in-game interaction
  • Teacher creates new academic task: "Evidence gathering"
  • Player finds evidence (hacking/dialogue)
  • Task completes → academic app updates
  • Phone shows post disappears (if removed) or changes to system post

Ending:
  • If fully supported: Maya reaches out, positive reputation growth
  • If partially: Mixed feelings
  • If ignored: Maya isolates, becomes NPC death/ending


CASE 2: BECOMING COMPLICIT
━━━━━━━━━━━━━━━━━━━━━━━━

Day 1-5:
  • Multiple anonymous bullying posts about various NPCs
  • Player likes several of them (testing limits)
  • Bullies notice → send private messages: "You get it, right?"

Day 6:
  • Same bullies propose joint posting
  • Academic tasks start including "Don't post bullying content"
  • If player ignores warning, tasks fail
  • Reputation with victims crashes
  • Reputation with bullies rises

Ending:
  • Player becomes known as complicit
  • Victims refuse to work with player
  • Ending: "Complicit" - higher reputation with bullies, lower with everyone else
  • Alternate content: Bullies eventually discard player, friendships shallow


CASE 3: THE REDEMPTION ARC
━━━━━━━━━━━━━━━━━━━━━━

Early game:
  • Player is neutral, sees posts, doesn't engage deeply
  • Minor reputation with bullies (liked a few posts)

Mid-game:
  • Incident awakens player's conscience
  • One NPC victim reaches out personally (dialogue trigger)
  • Player chooses to help (mission branch)
  • Starts gathering evidence, supporting victims

Late game:
  • Bullies notice reputation shift
  • Attempt to isolate player (negative posts appear)
  • But victims and allies support player back
  • Major choice: Public confrontation or quiet support?

Ending:
  • "Redeemed" - reputation shift from bullies to victims
  • Bullies try to make amends or double down
  • Player's choice determines if redemption is real or superficial


# ══════════════════════════════════════════════════════════════
#  END DOCUMENT
# ══════════════════════════════════════════════════════════════
"""
