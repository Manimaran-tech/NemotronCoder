"""
Hardcoded deterministic navigator for CodingPortal.
All navigation is done via known selectors — no AI/LLM needed.
"""

import asyncio
import re
from playwright.async_api import Page
from engine.selectors import URLS, LOGIN, HOME, LEVELS, LEVEL_1, LANGUAGE_LIST, MODULES, CHAPTERS, PROBLEM_LIST, NAV


# ─────────────────────────── HELPERS ───────────────────────────

async def safe_click(page: Page, selector: str, timeout: int = 5000, wait_after: int = 2000) -> bool:
    """Click an element safely, return True if clicked."""
    try:
        el = page.locator(selector).first
        await el.scroll_into_view_if_needed(timeout=timeout)
        await page.wait_for_timeout(300)
        await el.click(timeout=timeout)
        await page.wait_for_timeout(wait_after)
        return True
    except Exception as e:
        print(f"  [!] Could not click '{selector}': {e}")
        return False


async def wait_for_page_load(page: Page, timeout: int = 10000):
    """Wait for page to finish loading."""
    try:
        await page.wait_for_load_state("networkidle", timeout=timeout)
    except:
        pass
    await page.wait_for_timeout(1000)


async def get_page_text(page: Page) -> str:
    """Get all visible text on page."""
    try:
        return await page.inner_text("body")
    except:
        return ""


# ─────────────────────────── LOGIN ───────────────────────────

async def login(page: Page, username: str, password: str) -> bool:
    """Log into CodingPortal."""
    print("[*] Navigating to CodingPortal...")
    await page.goto(URLS["login"], wait_until="networkidle")
    await page.wait_for_timeout(2000)

    # Check if already logged in
    text = await get_page_text(page)
    if "Logout" in text or "logout" in text.lower():
        print("[+] Already logged in!")
        return True

    # Fill login form
    try:
        await page.locator(LOGIN["username_input"]).click()
        await page.wait_for_timeout(300)
        await page.keyboard.type(username, delay=20)

        await page.locator(LOGIN["password_input"]).click()
        await page.wait_for_timeout(300)
        await page.keyboard.type(password, delay=20)

        await page.wait_for_timeout(500)
        await page.locator(LOGIN["submit_button"]).click()

        print("[*] Waiting for login...")
        await wait_for_page_load(page, 15000)
        await page.wait_for_timeout(3000)

        text = await get_page_text(page)
        if "Logout" in text or "logout" in text.lower():
            print("[+] Login successful!")
            return True

        current_url = page.url.lower()
        if "login" not in current_url and "candidate" in current_url:
            print("[+] Login successful!")
            return True

        print("[-] Login may have failed.")
        return False
    except Exception as e:
        print(f"[-] Login error: {e}")
        return False


# ─────────────────────────── NAVIGATION ───────────────────────────

async def goto_home(page: Page) -> bool:
    """Navigate to main home page."""
    print("[NAV] Going to Home...")
    await page.goto(URLS["home"], wait_until="networkidle")
    await page.wait_for_timeout(2000)
    return True


async def goto_levels(page: Page) -> bool:
    """Navigate to the Levels/Programming page."""
    print("[NAV] Going to Levels page...")
    await page.goto(URLS["levels"], wait_until="networkidle")
    await page.wait_for_timeout(2000)
    return True


async def goto_level(page: Page, level_num: int) -> bool:
    """Navigate to a specific level page."""
    print(f"[NAV] Going to Level {level_num}...")

    if level_num == 1:
        await page.goto(URLS["level_1"], wait_until="networkidle")
    else:
        url = URLS["level_template"].format(level=level_num)
        await page.goto(url, wait_until="networkidle")

    await page.wait_for_timeout(2000)
    return True


async def goto_learn_languages(page: Page) -> bool:
    """Navigate to the Learn Languages page (from Level 1)."""
    print("[NAV] Going to Learn Languages...")
    await page.goto(URLS["learn_languages"], wait_until="networkidle")
    await page.wait_for_timeout(2000)
    return True


# ─────────────────────────── MODULE DISCOVERY ───────────────────────────

async def discover_modules_on_page(page: Page) -> list[dict]:
    """Discover all modules/courses on the current page.
    Returns list of {index, name, has_show_button}."""
    modules = await page.evaluate("""() => {
        const results = [];
        // Find all Show buttons with the known ID pattern
        const buttons = Array.from(document.querySelectorAll('button, a.ui-button, input[type="button"], input[type="submit"]')).filter(el => (el.innerText || el.value || "").trim() === 'Show');
        buttons.forEach((btn, i) => {
            let card = btn.closest('.ui-card, .ui-panel, [class*="card"], tr');
            let name = '';
            if (card) {
                let titleEl = card.querySelector('b, strong, h3, h4, .ui-card-title');
                if (titleEl) {
                    name = titleEl.innerText.trim();
                } else {
                    name = card.innerText.split('\\n')[0].trim();
                }
            }
            let idx = i;

            results.push({
                index: idx,
                name: name.substring(0, 100),
                button_id: btn.id,
                visible: btn.offsetHeight > 0
            });
        });
        return results;
    }""")
    return [m for m in modules if m.get("visible", True)]


async def click_module_show(page: Page, module_index: int) -> bool:
    """Click the Show button for a module at given index."""
    print(f"[NAV] Clicking Show on module index {module_index}...")
    buttons = page.locator("button:has-text('Show'), a.ui-button:has-text('Show'), input[value='Show']")
    count = await buttons.count()
    if module_index < count:
        target = buttons.nth(module_index)
        await target.scroll_into_view_if_needed(timeout=3000)
        await page.wait_for_timeout(300)
        await target.click(force=True)
        await wait_for_page_load(page)
        return True
    else:
        print(f"[-] Could not find Show button at index {module_index}. Found {count} buttons.")
        return False


# ─────────────────────────── CHAPTER DISCOVERY ───────────────────────────

async def discover_chapters(page: Page) -> list[dict]:
    """Discover all chapters inside a module (the ones with View buttons).
    Returns list of {index, name, units, has_view_button, is_completed}."""
    chapters = await page.evaluate("""() => {
        const results = [];
        // Find all View buttons with the chapter ID pattern
        const buttons = document.querySelectorAll('button[id*="j_id_4u"]');
        buttons.forEach((btn, i) => {
            let card = btn.closest('.ui-card, .ui-panel, [class*="card"], tr');
            let name = '';
            let units = 0;
            let isCompleted = false;

            if (card) {
                let text = card.innerText;
                // Extract chapter name (first line or bold text)
                let nameMatch = text.match(/([A-Z][-\\w\\s]+(?:Exercise|Sorting|String|Pointer|Structure|Storage|Bitwise|Pre-?Processor|Introduction|Advanced|Unions|Classes)\\S*)/i);
                if (nameMatch) {
                    name = nameMatch[1].trim();
                } else {
                    name = text.split('\\n')[0].trim();
                }
                // Extract units count
                let unitsMatch = text.match(/Units:\\s*(\\d+)/i);
                if (unitsMatch) units = parseInt(unitsMatch[1]);

                isCompleted = text.includes('Completed');
            }

            // Extract index from button ID
            let idMatch = btn.id.match(/cttbl:(\\d+):j_id_4u/);
            let idx = idMatch ? parseInt(idMatch[1]) : i;

            results.push({
                index: idx,
                name: name.substring(0, 100),
                units: units,
                button_id: btn.id,
                is_completed: isCompleted,
                visible: btn.offsetHeight > 0
            });
        });
        return results;
    }""")
    return [c for c in chapters if c.get("visible", True)]


async def click_chapter_view(page: Page, chapter_index: int) -> bool:
    """Click the View button for a chapter at given index."""
    print(f"[NAV] Clicking View on chapter index {chapter_index}...")
    buttons = page.locator("button:has-text('View'), a.ui-button:has-text('View'), input[value='View']")
    count = await buttons.count()
    if chapter_index < count:
        target = buttons.nth(chapter_index)
        await target.scroll_into_view_if_needed(timeout=3000)
        await page.wait_for_timeout(300)
        await target.click(force=True)
        await wait_for_page_load(page)
        return True
    else:
        print(f"[-] Could not find View button at index {chapter_index}. Found {count} buttons.")
        return False


# ─────────────────────────── PROBLEM LIST HANDLING ───────────────────────────

async def count_problems_on_page(page: Page) -> dict:
    """Count total and unsolved problems on a problem listing page."""
    info = await page.evaluate("""() => {
        const solveButtons = document.querySelectorAll('button, a, input[value="Solve"]');
        let solveCount = 0;
        let solvedCount = 0;
        let totalCount = 0;

        // Count Solve buttons
        for (let btn of solveButtons) {
            let text = btn.innerText || btn.value || '';
            if (text.trim() === 'Solve') solveCount++;
        }

        // Count Solved By entries (indicates total problem cards)
        let body = document.body.innerText;
        let solvedByMatches = body.match(/Solved By/gi);
        totalCount = solvedByMatches ? solvedByMatches.length : 0;

        // Count already-solved indicators
        let passedMatches = body.match(/passed|Solved ✓|Already Solved/gi);
        solvedCount = passedMatches ? passedMatches.length : 0;

        return {
            total: totalCount,
            unsolved: solveCount,
            solved: Math.max(0, totalCount - solveCount)
        };
    }""")
    return info


async def click_first_solve(page: Page, skip_count: int = 0) -> bool:
    """Click the Nth visible Solve button on a problem listing page."""
    print(f"[NAV] Clicking Solve button (skipping {skip_count})...")
    try:
        solve_buttons = page.locator("button:has-text('Solve'), a:has-text('Solve'), input[value='Solve']")
        count = await solve_buttons.count()
        if count > skip_count:
            solve_btn = solve_buttons.nth(skip_count)
            if await solve_btn.is_visible(timeout=3000):
                await solve_btn.click()
                await page.wait_for_timeout(3000)
                return True
    except:
        pass
    return False


async def click_back_to_challenges(page: Page) -> bool:
    """Click 'Back To Challenges List' button."""
    print("[NAV] Going back to challenges list...")
    try:
        btn = page.locator("a:has-text('Back To Challenges List'), button:has-text('Back To Challenges List')").first
        if await btn.is_visible(timeout=3000):
            await btn.click()
            await page.wait_for_timeout(3000)
            await wait_for_page_load(page)
            return True
    except:
        pass
    return False


# ─────────────────────────── BREADCRUMB NAV ───────────────────────────

async def click_breadcrumb_home(page: Page) -> bool:
    """Click the breadcrumb home icon to go back to module root."""
    print("[NAV] Clicking breadcrumb home...")
    return await safe_click(page, CHAPTERS["breadcrumb_home"], timeout=3000, wait_after=3000)


async def goto_main_home(page: Page) -> bool:
    """Navigate to main home via direct URL (most reliable)."""
    print("[NAV] Navigating to main home...")
    await page.goto(URLS["home"], wait_until="networkidle")
    await page.wait_for_timeout(2000)
    return True


# ─────────────────────────── PAGE DETECTION ───────────────────────────

async def detect_page_type(page: Page) -> str:
    """Detect what type of CodingPortal page we're currently on.
    Returns: 'home', 'levels', 'module_list', 'chapter_list',
             'problem_list', 'problem_solve', 'captcha', 'unknown'"""
    url = page.url.lower()
    text = await get_page_text(page)
    text_lower = text.lower() if text else ""

    # Check URL patterns first
    if "profile.xhtml" in url:
        return "home"
    if "trackshome.xhtml" in url:
        return "levels"
    if "lev1.xhtml" in url:
        return "level_1"

    # Check for captcha/proceed page
    if "proceed to solve" in text_lower:
        return "captcha"

    # Check for problem solving page (has Run button + code editor)
    if "programid" in text_lower and ("run" in text_lower):
        return "problem_solve"

    # Check for problem listing (has Solve buttons + Problem IDs)
    solve_count = await page.locator("button:has-text('Solve'), a:has-text('Solve')").count()
    if solve_count > 0 and "solved by" in text_lower:
        return "problem_list"

    # Check for chapter listing (has View buttons with cttbl pattern)
    view_count = await page.locator('button[id*="j_id_4u"]').count()
    if view_count > 0:
        return "chapter_list"

    # Check for module/course listing (has Show buttons)
    show_count = await page.locator('button[id*="j_id_4b"]').count()
    if show_count > 0:
        return "module_list"

    # codeprogramgroup with CODETRACK or CODETUTOR
    if "codeprogramgroup" in url:
        if "codetutor" in url or "codetrack" in url:
            return "module_list"
        return "chapter_list"

    return "unknown"
