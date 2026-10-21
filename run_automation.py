"""
NemotronCoder Orchestrator
Usage: python run_automation.py --count 10
"""

import asyncio
import argparse
import os
import sys
from playwright.async_api import async_playwright, Browser, Page
from playwright_stealth import Stealth

# Engine modules
from engine.db import (
    start_session, update_session, get_total_solved, print_progress,
    upsert_module, get_all_modules, upsert_chapter, get_next_unsolved_chapter,
    record_problem_attempt, mark_problem_solved, mark_problem_failed,
    mark_chapter_completed, mark_module_completed, get_next_unsolved_module,
    get_failed_problems_count
)
from engine.navigator import (
    login, goto_levels, goto_level, goto_learn_languages, discover_modules_on_page,
    click_module_show, discover_chapters, click_chapter_view, click_first_solve,
    goto_home, detect_page_type, wait_for_page_load, click_back_to_challenges
)
from engine.selectors import LANGUAGE_INDICES
from engine.solver import solve_current_problem, click_next
from config import PORTAL_USERNAME, PORTAL_PASSWORD

async def initialize_browser(headless: bool = False) -> tuple[Browser, Page]:
    print(f"[*] Launching stealth browser (headless={headless})...")
    p = await async_playwright().start()
    browser = await p.chromium.launch(
        headless=headless,
        args=["--start-maximized", "--disable-blink-features=AutomationControlled"] if not headless else ["--disable-blink-features=AutomationControlled"]
    )
    context = await browser.new_context(
        viewport={"width": 1920, "height": 1080},
        no_viewport=True,
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        locale="en-US",
        timezone_id="Asia/Kolkata"
    )
    page = await context.new_page()
    await Stealth().apply_stealth_async(page)
    print("[+] Stealth patches applied")
    return browser, page

async def run_automation(target_count: int, username: str = None, password: str = None, headless: bool = False, lang: str = "c"):
    already_solved = get_total_solved()
    print(f"[*] Absolute Target: {target_count} solved problems (Already solved in database: {already_solved})")
    
    session_target = target_count - already_solved
    if session_target <= 0:
        print(f"[+] Absolute target of {target_count} already achieved! Exiting.")
        return
        
    print(f"[*] Starting automation to solve {session_target} more problems in this session...")
    session_id = start_session(target_count)
    problems_solved_this_session = 0
    problems_attempted = 0

    browser, page = await initialize_browser(headless)
    
    # Fallback to config if arguments not provided
    user = username or PORTAL_USERNAME
    pwd = password or PORTAL_PASSWORD
    print(f"[*] Attempting login for student: {user}")
    logged_in = await login(page, user, pwd)
    if not logged_in:
        print("[-] Login failed. Exiting.")
        await browser.close()
        return

    # To keep it simple, we will just orchestrate solving problems sequentially
    # based on user being on the problem solve page or we find an unsolved module.

    # 1. Start by checking if we have modules in DB for this language
    modules_in_db = get_next_unsolved_module(level=1, language=lang)
    lang_idx = LANGUAGE_INDICES.get(lang, 0)
    
    if not modules_in_db:
        print(f"[*] No modules in DB for {lang}. Discovering Level 1 Learn Languages modules...")
        await goto_levels(page)
        await goto_level(page, 1)
        await goto_learn_languages(page)
        await page.wait_for_timeout(2000)
        # Click Language Show (index based on lang)
        await click_module_show(page, lang_idx)
        await wait_for_page_load(page)
        
        # Now on Language Modules page
        c_modules = await discover_modules_on_page(page)
        for m in c_modules:
            upsert_module(level=1, language=lang, module_index=m["index"], module_name=m["name"])
        print(f"[+] Discovered {len(c_modules)} modules.")

    while problems_solved_this_session < session_target:
        # Get next unsolved module
        module = get_next_unsolved_module(level=1, language=lang)
        if not module:
            print("[+] All modules completed!")
            break

        print(f"\n[*] Processing Module: {module['module_name']}")
        
        # Navigate to this module
        await goto_levels(page)
        await goto_level(page, 1)
        await goto_learn_languages(page)
        await click_module_show(page, lang_idx) # Open language
        await click_module_show(page, module["module_index"]) # Open specific module
        
        # Discover chapters
        chapters = await discover_chapters(page)
        for c in chapters:
            upsert_chapter(module["id"], c["index"], c["name"], c["units"])
            if c["is_completed"]:
                # Mark it completed if UI says so
                c_id = upsert_chapter(module["id"], c["index"], c["name"], c["units"])
                mark_chapter_completed(c_id)

        # Process chapters
        while problems_solved_this_session < session_target:
            chapter = get_next_unsolved_chapter(module["id"])
            if not chapter:
                print(f"[+] Module {module['module_name']} completed!")
                mark_module_completed(module["id"])
                # MUST go home after module
                await goto_home(page)
                break
                
            print(f"\n[*] Processing Chapter: {chapter['chapter_name']}")
            await click_chapter_view(page, chapter["chapter_index"])
            
            # Now we should be on the problem listing page
            skip_count = get_failed_problems_count(chapter["id"])
            entered = await click_first_solve(page, skip_count)
            if not entered:
                print("[-] No unsolved problems found in this chapter. Marking completed.")
                mark_chapter_completed(chapter["id"])
                if module:
                    # We fell back to challenges list unexpectedly?
                    await goto_levels(page)
                    await goto_level(page, 1)
                    await goto_learn_languages(page)
                    await click_module_show(page, lang_idx)
                    await click_module_show(page, module["module_index"])
                else:continue

            # Solve loop within the chapter
            while problems_solved_this_session < session_target:
                ptype = await detect_page_type(page)
                if ptype in ["captcha", "problem_solve"]:
                    result = await solve_current_problem(page)
                    
                    if result == "skipped":
                        # Already solved or tutorial slide. Go to next problem.
                        has_next = await click_next(page)
                        if not has_next:
                            print("[*] Chapter complete (no next button).")
                            mark_chapter_completed(chapter["id"])
                            break
                    elif result == "solved":
                        problems_attempted += 1
                        prob_id = record_problem_attempt(chapter["id"], "unknown", "c")
                        problems_solved_this_session += 1
                        mark_problem_solved(prob_id)
                        update_session(session_id, problems_attempted, problems_solved_this_session)
                        print(f"[+] Solved ({already_solved + problems_solved_this_session}/{target_count})")
                        
                        if problems_solved_this_session >= session_target:
                            break
                            
                        # Click Next to go to next problem
                        has_next = await click_next(page)
                        if not has_next:
                            print("[*] Chapter complete (no next button).")
                            mark_chapter_completed(chapter["id"])
                            break
                    else:  # failed
                        problems_attempted += 1
                        prob_id = record_problem_attempt(chapter["id"], "unknown", "c")
                        print("[-] Failed to solve. Skipping to next problem...")
                        mark_problem_failed(prob_id, "Failed during solve loop")
                        skip_count += 1
                        await click_back_to_challenges(page)
                elif ptype in ["problem_list", "chapter_list"]:
                    entered = await click_first_solve(page, skip_count)
                    if not entered:
                        print("[-] No more unsolved/unskipped problems in chapter.")
                        break
                else:
                    # We might be back on a listing page or somewhere else
                    print(f"[*] Unexpected page type: {ptype}. Breaking chapter loop.")
                    break

            # Go back to module chapters listing
            await goto_home(page)
            if problems_solved_this_session < session_target:
                await goto_levels(page)
                await goto_level(page, 1)
                await goto_learn_languages(page)
                await click_module_show(page, 0)
                await click_module_show(page, module["module_index"])

    print("\n[*] Automation completed!")
    update_session(session_id, problems_attempted, problems_solved_this_session)
    print_progress()
    await browser.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NemotronCoder Orchestrator")
    parser.add_argument("--count", type=int, default=1, help="Number of problems to solve")
    parser.add_argument("--username", type=str, default=None, help="CodingPortal Username")
    parser.add_argument("--password", type=str, default=None, help="CodingPortal Password")
    parser.add_argument("--headless", action="store_true", help="Run browser in headless mode")
    parser.add_argument("--lang", type=str, default="c", choices=["c", "java", "python", "cpp", "sql", "data_structures_c", "data_structures_java"], help="Language module to solve")
    
    args = parser.parse_args()
    
    if args.username and "AGENT_DB_PATH" not in os.environ:
        from pathlib import Path
        db_dir = Path(__file__).parent / "db"
        db_dir.mkdir(parents=True, exist_ok=True)
        isolated_db = db_dir / f"{args.username}_progress.db"
        os.environ["AGENT_DB_PATH"] = str(isolated_db)
        print(f"[*] Using isolated progress database: {isolated_db.name}")

    asyncio.run(run_automation(
        target_count=args.count,
        username=args.username,
        password=args.password,
        headless=args.headless,
        lang=args.lang
    ))
