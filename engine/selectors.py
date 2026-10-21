"""
Hardcoded selectors and URLs for CodingPortal navigation.
All values extracted from page snapshots captured in Phase 1.
"""

# ─────────────────────────── BASE URLS ───────────────────────────

BASE_URL = "https://codebenchmark.internal"

URLS = {
    "login": f"{BASE_URL}/faces/candidate/tutorprogram.xhtml",
    "home": f"{BASE_URL}/faces/ui/profile.xhtml",
    "levels": f"{BASE_URL}/faces/candidate/trackshome.xhtml",
    "level_1": f"{BASE_URL}/faces/candidate/lev1.xhtml",
    # Level 2-6 use query params:  /codeprogramgroup.xhtml?gt=CODETRACK&lev=N
    "level_template": f"{BASE_URL}/faces/candidate/codeprogramgroup.xhtml?gt=CODETRACK&lev={{level}}",
    "learn_languages": f"{BASE_URL}/faces/candidate/codeprogramgroup.xhtml?gt=CODETUTOR",
}


# ─────────────────────────── LOGIN PAGE ───────────────────────────

LOGIN = {
    "username_input": 'input[name="j_username"]',
    "password_input": 'input[name="j_password"]',
    "submit_button": 'input[type="submit"][value="Login"]',
}


# ─────────────────────────── HOME / MAIN PAGE ───────────────────────────

HOME = {
    # Left sidebar navigation links
    "programming_link": 'a[href="/faces/candidate/trackshome.xhtml"]',
    "home_link": 'a[href="/faces/ui/profile.xhtml"]',
    "logout_link": 'a:has-text("Logout")',
}


# ─────────────────────────── LEVELS PAGE ───────────────────────────
# /faces/candidate/trackshome.xhtml

LEVELS = {
    # View buttons for each level — use href matching
    "level_1_view": 'a.ui.button[href="/faces/candidate/lev1.xhtml"]',
    "level_view_template": 'a.ui.button[href*="CODETRACK"][href*="lev={level}"]',
    # All level view buttons
    "all_level_views": 'a.ui.button[href*="CODETRACK"], a.ui.button[href*="lev1.xhtml"]',
}


# ─────────────────────────── LEVEL 1 (SPECIAL) ───────────────────────────
# /faces/candidate/lev1.xhtml — has Learn Languages, Daily Challenge, Daily Test

LEVEL_1 = {
    "learn_languages_view": 'a.ui.blue.button[href*="CODETUTOR"]',
    "daily_challenge_view": 'a.ui.blue.button[href*="dailychallenge"][href*="DC"]',
    "daily_test_view": 'a.ui.blue.button[href*="dailychallenge"][href*="DT"]',
}


# ─────────────────────────── LANGUAGE LIST (LEARN LANGUAGES) ───────────────────────────
# /faces/candidate/codeprogramgroup.xhtml?gt=CODETUTOR
# Shows: C Programming, Java Programming, Python, C++, SQL, Data Structures

LANGUAGE_LIST = {
    # Show buttons inside the language cards — indexed by position
    # Pattern: pkglistform:j_id_49:{index}:j_id_4b
    "show_button_template": 'button[id$=":{index}:j_id_4b"]',
    # All Show buttons on the page
    "all_show_buttons": 'button[id*="j_id_4b"]',
    # Language card container
    "card_template": '[id$=":{index}:j_id_4a"]',
}

# Language name → index mapping (from snapshot: inside_level_1_learn_language_page)
LANGUAGE_INDICES = {
    "c": 0,
    "java": 1,
    "python": 2,
    "cpp": 3,
    "sql": 4,
    "data_structures_c": 5,
    "data_structures_java": 6,
}


# ─────────────────────────── MODULES LIST ───────────────────────────
# /faces/candidate/codeprogramgroup.xhtml (after clicking Show on a language)
# Shows all modules (C-INTRO, C-STARTER, etc.) with Show buttons

MODULES = {
    # Show button pattern: pkglistform:j_id_49:{index}:j_id_4b
    "show_button_template": 'button[id$=":{index}:j_id_4b"]',
    "all_show_buttons": 'button[id*="j_id_4b"]',
    # Module card pattern for reading module names
    "card_template": '[id$=":{index}:j_id_4a"]',
    "all_cards": '[id*="j_id_4a"]',
    # Breadcrumb home link (goes back to language list)
    "breadcrumb_home": 'a.ui-menuitem-link.ui-corner-all.ui-breadcrumb-home-icon',
}


# ─────────────────────────── INSIDE MODULE (CHAPTERS) ───────────────────────────
# /faces/candidate/codeprogramgroup.xhtml (after Show on a module)
# Shows chapters with View buttons, tabs for Currently Learning / Completed

CHAPTERS = {
    # View button pattern: cttbl:{index}:j_id_4u
    "view_button_template": 'button[id$="cttbl:{index}:j_id_4u"]',
    "all_view_buttons": 'button[id*="j_id_4u"]',
    # Tabs
    "currently_learning_tab": 'a:has-text("Currently Learning")',
    "completed_tab": 'a:has-text("Completed")',
    # Breadcrumb home (goes back to module list root)
    "breadcrumb_home": 'a.ui-menuitem-link.ui-corner-all.ui-breadcrumb-home-icon',
    # Main home link
    "home_link": 'a.ui-menuitem-link.ui-corner-all[href="/faces/ui/profile.xhtml"]',
    # Chapter card content (for reading chapter names)
    "card_template": '[id$="cttbl:{index}:j_id_4s"]',
}


# ─────────────────────────── PROBLEM LIST ───────────────────────────
# Shows individual problems with Solve buttons

PROBLEM_LIST = {
    "all_solve_buttons": 'button:has-text("Solve"), a:has-text("Solve"), input[value="Solve"]',
    "back_to_challenges": 'a:has-text("Back To Challenges List"), button:has-text("Back To Challenges List")',
}


# ─────────────────────────── PROBLEM PAGE (SOLVE) ───────────────────────────
# The actual problem-solving page with code editor

PROBLEM = {
    # Captcha elements
    "captcha_input": "input#capval",
    "captcha_image": 'img[src^="data:image"]',
    "proceed_button": "#proceedbtn",
    # Code editor
    "ace_editor": "#ctutortxtCode, #ctracktxtCode, #txtEditor, .ace_editor",
    # Run button
    "run_button": "button:has-text('Run'), input[value='Run']",
    "run_button_span": "button span.ui-button-text:has-text('Run')",
    # Results
    "pass_text": "text=/Congratulations! Your Code has passed|Great! Your code has passed|SUCCESS/i",
    "fail_text": "text=Code did not pass the execution",
    # Next/Proceed
    "next_button": "a:has-text('Proceed Next'), button:has-text('Proceed Next'), a:has-text('Next'), button:has-text('Next')",
    # Solution fallback
    "solution_button": "a:has-text('Solution'), button:has-text('Solution'), span:has-text('Solution')",
    # Problem content
    "program_grid": "#programgrid",
    "code_div": "#codediv",
    "multifib_panel": "#multifibpanel",
    # MFIB input boxes (fill-in-blank inline inputs)
    "fib_inputs": "#codediv input:not([type='hidden']):not([type='submit']):not([type='button'])",
    "mfib_inputs": "#multifibpanel input:not([type='hidden']):not([type='submit']):not([type='button'])",
}


# ─────────────────────────── COMMON NAV ───────────────────────────

NAV = {
    "home_link": 'a.ui-menuitem-link.ui-corner-all[href="/faces/ui/profile.xhtml"]',
    "breadcrumb_home": 'a.ui-menuitem-link.ui-corner-all.ui-breadcrumb-home-icon',
    "programming_link": 'a[href="/faces/candidate/trackshome.xhtml"]',
}
