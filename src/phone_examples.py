"""
src/phone_examples.py  —  Practical examples of phone system usage
==================================================================

Copy-paste ready code snippets showing how to use the phone system.
These are meant to be integrated into your Game class.
"""

import pygame
from src.phone import Phone, PhoneState, SocialPost, TextMessage, AcademicTask
from src.phone_integration import PhoneIntegrationManager


# ══════════════════════════════════════════════════════════════
#  EXAMPLE 1: BASIC GAME.PY INTEGRATION
# ══════════════════════════════════════════════════════════════

"""
INSERT IN Game.__init__:

    # Phone system
    from src.phone import Phone
    from src.phone_integration import PhoneIntegrationManager
    
    self.phone = Phone(self.screen)
    self.phone_integration = PhoneIntegrationManager(self.phone)
    
    # Control binding
    self.KEY_PHONE = pygame.K_k  # Press K to open phone
"""


# ══════════════════════════════════════════════════════════════
#  EXAMPLE 2: UPDATE LOOP
# ══════════════════════════════════════════════════════════════

"""
INSERT IN Game.update(dt):

    # Update phone animation
    self.phone.update(dt)
    
    # Sync missions to phone (every 30 frames to avoid overhead)
    if not hasattr(self, '_phone_sync_counter'):
        self._phone_sync_counter = 0
    
    self._phone_sync_counter += 1
    if self._phone_sync_counter % 30 == 0:
        if hasattr(self, 'mission_manager'):
            self.phone_integration.sync_missions_to_phone(
                self.mission_manager.missions
            )
        self._phone_sync_counter = 0
    
    # Check for phone-driven narrative events
    phone_events = self.phone_integration.check_phone_driven_events()
    for event in phone_events:
        self._handle_phone_event(event)
"""


# ══════════════════════════════════════════════════════════════
#  EXAMPLE 3: DRAW LOOP
# ══════════════════════════════════════════════════════════════

"""
INSERT IN Game.draw():

    # ... draw game world, NPCs, etc ...
    
    # Draw phone overlay
    self.phone.draw()
    
    # Draw phone HUD icon (always visible when closed)
    self.phone.draw_hud_icon()
"""


# ══════════════════════════════════════════════════════════════
#  EXAMPLE 4: INPUT HANDLING
# ══════════════════════════════════════════════════════════════

"""
INSERT IN Game.handle_input(event) or Game.process_event(event):

    # Let phone consume input first
    if self.phone.handle_input(event):
        return  # Input was handled by phone
    
    # Phone toggle (K key)
    if event.type == pygame.KEYDOWN:
        if event.key == self.KEY_PHONE:
            self.phone.toggle_phone()
            return
    
    # ... rest of game input handling ...


INSERT IN Game.handle_mouse_click(pos) or similar:

    # Check phone HUD icon click
    if self.phone.state == PhoneState.CLOSED:
        if self.phone.hud_icon_rect.collidepoint(pos):
            self.phone.toggle_phone()
            return True
    
    # ... rest of click handling ...
"""


# ══════════════════════════════════════════════════════════════
#  EXAMPLE 5: DAY START - SET SCHEDULE
# ══════════════════════════════════════════════════════════════

def setup_daily_schedule(game_instance):
    """
    Call this when a new in-game day starts.
    
    If using DAY_SCHEDULE from settings.py (list of DayPhase tuples),
    this will convert it to phone-readable schedule.
    """
    from settings import DAY_SCHEDULE
    
    game_instance.phone_integration.set_daily_schedule(DAY_SCHEDULE)


# ══════════════════════════════════════════════════════════════
#  EXAMPLE 6: POST-GAME MISSION START
# ══════════════════════════════════════════════════════════════

def create_mission_with_phone_sync(game_instance, mission_dict):
    """
    Create a mission that appears in both mission system and phone.
    
    mission_dict should include:
      {
        "id": "unique_id",
        "title": "Task name",
        "description": "What to do",
        "npc_issuer": "Teacher name or NPC",
        "visible_on_phone": True,
        "priority": 1,  # 0=side, 1+=main
      }
    """
    # Create mission in game
    mission = {
        **mission_dict,
        "visible_on_phone": mission_dict.get("visible_on_phone", True),
        "npc_issuer": mission_dict.get("npc_issuer", "Sistema"),
        "phone_progress": 0.0,
    }
    
    # Add to mission manager (pseudo-code, adjust for actual structure)
    # game_instance.mission_manager.add_mission(mission)
    
    # Sync to phone immediately
    # (This will show up the next time sync runs)


# ══════════════════════════════════════════════════════════════
#  EXAMPLE 7: BULLYING INCIDENT - CREATE SOCIAL POST
# ══════════════════════════════════════════════════════════════

def simulate_bullying_incident(game_instance, victim_npc_name: str):
    """
    Simulate a bullying incident:
    1. Anonymous post appears in social feed
    2. Victim sends distress text message
    3. Investigation task appears
    
    This demonstrates the integrated flow.
    """
    
    # 1. Create anonymous post
    game_instance.phone_integration.create_social_post(
        content=f"Ej, miren a {victim_npc_name}... no sé cómo se atreve a venir",
        author_name="Anónimo",
        author_npc_id=None,
        is_anonymous=True,
        affects_reputation=True,
        reputation_target=victim_npc_name,
        image_tag="⚠️",  # Warning emoji
    )
    
    # 2. Victim sends text
    game_instance.phone_integration.send_text_message(
        npc_id=f"npc_{victim_npc_name.lower()}",
        npc_name=victim_npc_name,
        content=f"¿Viste? Ya está circulando de nuevo... No aguanto más 😞",
    )
    
    # 3. Create investigation mission (in actual game)
    # game_instance.mission_manager.add_mission({
    #     "id": f"investigate_{victim_npc_name}",
    #     "title": f"Investigar los rumores sobre {victim_npc_name}",
    #     "description": "Habla con NPCs para averiguar quién está acosando",
    #     "visible_on_phone": True,
    #     "npc_issuer": victim_npc_name,
    #     "priority": 2,
    # })
    
    # 4. Log incident (for ending calculation)
    game_instance.phone_integration.bullying_incident(
        bully_npc_id="npc_bully_01",  # Should be actual NPC ID
        victim_npc_id=f"npc_{victim_npc_name.lower()}",
        incident_type="post",
        is_anonymous=True,
    )


# ══════════════════════════════════════════════════════════════
#  EXAMPLE 8: NPC SENDS MESSAGE (AFTER PLAYER ACTION)
# ══════════════════════════════════════════════════════════════

def npc_reaction_text(game_instance, npc_name: str, action_type: str):
    """
    Send reactive text message from NPC based on player action.
    
    action_type: "defended", "bullied", "helped", "ignored", etc.
    """
    
    messages_map = {
        "defended": f"Gracias por defenderme. De verdad... significa mucho 💙",
        "bullied": f"¿Cómo pudiste? Creía que eras diferente...",
        "helped": f"No lo olvidaré. Eres genuinamente una buena persona.",
        "ignored": f"Pensé que te importaba... Supongo que estaba equivocado.",
        "reported": f"¡Lo reportaste! Gracias... finalmente alguien hace algo.",
    }
    
    text = messages_map.get(action_type, "...")
    
    game_instance.phone_integration.send_text_message(
        npc_id=f"npc_{npc_name.lower()}",
        npc_name=npc_name,
        content=text,
    )


# ══════════════════════════════════════════════════════════════
#  EXAMPLE 9: MISSION COMPLETION CALLBACK
# ══════════════════════════════════════════════════════════════

def on_mission_completed(game_instance, mission_id: str, mission_title: str):
    """
    Call this when a mission completes in the game.
    Updates phone and triggers consequences.
    """
    
    # Update phone's academic app
    game_instance.phone_integration.mission_completed_callback(
        mission_id, mission_title
    )
    
    # Create celebration post (optional)
    if "investigate" in mission_id.lower():
        # Investigation completed → show outcome
        game_instance.phone_integration.create_social_post(
            content=f"¡{mission_title} completada! 🎉",
            author_name="📌 Sistema",
            is_anonymous=False,
            image_tag="🎉",
        )


# ══════════════════════════════════════════════════════════════
#  EXAMPLE 10: CHECK BULLYING REPORT (FOR ENDING)
# ══════════════════════════════════════════════════════════════

def determine_game_ending(game_instance) -> str:
    """
    Use phone bullying report to determine game ending.
    
    This is called at game end to calculate which ending plays.
    """
    
    report = game_instance.phone_integration.get_bullying_report()
    
    # Get player reputation (pseudo-code, adjust for your system)
    player_reputation = {}
    # player_reputation = game_instance.reputation_system.player_stats
    
    # Simple ending logic (expand as needed)
    total_incidents = report["total_incidents"]
    anonymous_count = report["anonymous_posts_count"]
    
    if total_incidents == 0:
        return "peaceful_school"  # No bullying happened
    elif anonymous_count > total_incidents * 0.7:
        return "toxic_culture"  # Mostly anonymous posts (toxic)
    elif report["most_bullied_count"] > 5:
        return "victim_isolated"  # Someone heavily bullied
    else:
        return "managed_conflicts"  # Mixed outcomes
    
    # This should integrate with your actual Ending system


# ══════════════════════════════════════════════════════════════
#  EXAMPLE 11: LIKE A POST (PLAYER INTERACTION)
# ══════════════════════════════════════════════════════════════

def player_likes_post(game_instance, post_id: str):
    """
    Handle player liking a post (affects reputation).
    
    This would be called from phone.handle_input() when player
    clicks heart on a post.
    """
    
    # Find post
    post = None
    for p in game_instance.phone.social_posts:
        if p.id == post_id:
            post = p
            break
    
    if not post:
        return
    
    # Like the post
    game_instance.phone.like_post(post_id)
    
    # Reputation consequences
    if post.affects_reputation and post.reputation_target:
        # Liking a bullying post hurts the victim
        if post.is_anonymous:
            reputation_change = -5  # Subtle: you're endorsing bullying
        else:
            reputation_change = -15  # More obvious
        
        # Apply reputation change (pseudo-code)
        # game_instance.reputation_system.add_reputation(
        #     post.reputation_target,
        #     reputation_change
        # )


# ══════════════════════════════════════════════════════════════
#  EXAMPLE 12: FULL FLOW - DAY START TO END
# ══════════════════════════════════════════════════════════════

def example_game_day_flow(game_instance):
    """
    Complete example of a day's worth of phone interactions.
    
    This shows how everything connects narratively.
    """
    
    # MORNING - Day starts
    print("═ DAY STARTS ═")
    setup_daily_schedule(game_instance)
    print("✓ Schedule set")
    
    # MORNING - Bullying happens
    print("═ FIRST CLASS ═")
    simulate_bullying_incident(game_instance, "Maya")
    print("✓ Bullying incident reported on phone")
    print("✓ Maya sent distress text")
    print("✓ Investigation task created")
    
    # MID-DAY - Player checks phone
    print("═ LUNCH - PLAYER CHECKS PHONE ═")
    print("Phone has:")
    print(f"  • {len(game_instance.phone.social_posts)} posts in feed")
    print(f"  • {game_instance.phone.get_unread_messages_count()} unread messages")
    print(f"  • {len(game_instance.phone.academic_tasks)} academic tasks")
    
    # AFTERNOON - Player helps
    print("═ AFTER CLASS - PLAYER ACTION ═")
    npc_reaction_text(game_instance, "Maya", "helped")
    print("✓ Maya sent grateful text")
    
    # EVENING - Investigate and complete mission
    print("═ INVESTIGATION ═")
    on_mission_completed(game_instance, "investigate_maya", "Investigación completada")
    print("✓ Investigation completed")
    print("✓ System posted celebration")
    
    # NIGHT - Check ending
    print("═ END OF DAY - ENDING CHECK ═")
    ending = determine_game_ending(game_instance)
    print(f"✓ Calculated ending: {ending}")
    
    report = game_instance.phone_integration.get_bullying_report()
    print(f"  Total incidents: {report['total_incidents']}")
    print(f"  Anonymous posts: {report['anonymous_posts_count']}")
    print(f"  Most bullied: {report['most_bullied']}")


# ══════════════════════════════════════════════════════════════
#  UTILITY FUNCTIONS
# ══════════════════════════════════════════════════════════════

def print_phone_status(game_instance):
    """Debug: Print current phone state."""
    print(f"Phone state: {game_instance.phone.state}")
    print(f"Current app: {game_instance.phone.current_app}")
    print(f"Posts: {len(game_instance.phone.social_posts)}")
    print(f"Messages: {sum(len(m) for m in game_instance.phone.messages.values())}")
    print(f"Tasks: {len(game_instance.phone.academic_tasks)}")
    print(f"Unread: {game_instance.phone.get_unread_messages_count()}")


def print_bullying_report(game_instance):
    """Debug: Print bullying analysis."""
    report = game_instance.phone_integration.get_bullying_report()
    print("\n═ BULLYING REPORT ═")
    print(f"Total incidents: {report['total_incidents']}")
    print(f"Anonymous posts: {report['anonymous_posts_count']}")
    print(f"Unique victims: {report['unique_victims']}")
    print(f"Most bullied: {report['most_bullied']} ({report['most_bullied_count']} times)")


def simulate_day_stress_test(game_instance, post_count: int = 50):
    """Debug: Stress test with many posts."""
    for i in range(post_count):
        game_instance.phone_integration.create_social_post(
            content=f"Spam post {i}",
            author_name=f"User{i % 10}",
            is_anonymous=i % 2 == 0,
        )
    print(f"✓ Created {post_count} posts")
    print(f"Total posts in feed: {len(game_instance.phone.social_posts)}")


# ══════════════════════════════════════════════════════════════
#  FOR TESTING IN ISOLATION
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    """
    Quick test without full game (requires pygame):
    
    python src/phone_examples.py
    """
    pygame.init()
    screen = pygame.display.set_mode((1280, 720))
    
    # Create phone and integration
    phone = Phone(screen)
    integration = PhoneIntegrationManager(phone)
    
    # Test create posts
    for i in range(5):
        integration.create_social_post(
            content=f"Test post {i}",
            author_name=f"User{i}",
            is_anonymous=i % 2 == 0,
        )
    
    # Test messages
    integration.send_text_message(
        npc_id="test_npc",
        npc_name="Test NPC",
        content="Hello from test",
    )
    
    print("✓ Phone system initialized successfully")
    print(f"✓ Posts: {len(phone.social_posts)}")
    print(f"✓ Messages: {len(phone.messages)}")
