"""
NemotronCoder: Autonomous Coding Agent
Automates solving CodingPortal coding problems using Playwright + Local Llama (Ollama).

Usage:
    python main.py

Flow:
    1. Launches browser, logs into CodingPortal
    2. You navigate to any programming track/module
    3. Press Enter in terminal -> it scrapes, solves, types, runs
    4. Loops until module ends or you Ctrl+C
"""

import asyncio
import time
import re
import random
import math
import ollama
from openai import OpenAI
from playwright.async_api import async_playwright, Page, Browser

from config import (
    PORTAL_USERNAME,
    PORTAL_PASSWORD,
    PORTAL_LOGIN_URL,
    OLLAMA_MODEL,
    USE_GEMINI,
    GEMINI_API_KEY,
    GEMINI_MODEL,
    USE_NEBIUS,
    NEBIUS_API_KEY,
    NEBIUS_BASE_URL,
    USE_NVIDIA,
    NVIDIA_API_KEY,
    FAST_MODEL,
    THINKING_MODEL,
    RUN_WAIT_SECONDS,
    NEXT_WAIT_SECONDS,
    MAX_RETRIES,
)

# ─────────────────────────── SESSION MEMORY ───────────────────────────
# Stores lessons learned from errors during this session.
# Cleared when script exits.
session_memory = []

# ─────────────────────────── HUMAN-LIKE HELPERS ───────────────────────────

def human_typing_delay() -> int:
    """Return a human-like per-character delay in ms.
    Simulates variable typing speed: avg ~55 WPM (≈110ms/char) with
    random bursts (faster) and pauses (slower), following a normal
    distribution clamped to realistic bounds."""
    # Average human types ~40-60 WPM, which is roughly 100-150ms per char
    base = random.gauss(110, 35)  # mean=110ms, stdev=35ms
    # Occasional micro-pauses (thinking mid-word)
    if random.random() < 0.08:  # 8% chance of a longer pause
        base += random.randint(200, 600)
    # Occasional burst typing (fast stretch)
    if random.random() < 0.05:  # 5% chance of speed burst
        base *= 0.4
    return max(25, min(int(base), 350))  # clamp to 25-350ms


async def human_pause(page: Page, min_ms: int = 500, max_ms: int = 2000):
    """Random pause to simulate human thinking/reading."""
    delay = random.randint(min_ms, max_ms)
    await page.wait_for_timeout(delay)


async def human_mouse_jitter(page: Page):
    """Move mouse to a random spot on screen to simulate human behavior."""
    try:
        x = random.randint(100, 1400)
        y = random.randint(100, 800)
        await page.mouse.move(x, y, steps=random.randint(5, 15))
        await page.wait_for_timeout(random.randint(100, 400))
    except:
        pass


async def human_scroll(page: Page):
    """Perform a small random scroll to look natural."""
    try:
        delta = random.choice([-120, -80, 80, 120, 200])
        await page.mouse.wheel(0, delta)
        await page.wait_for_timeout(random.randint(300, 800))
    except:
        pass


async def simulate_reading(page: Page, text_length: int = 500):
    """Simulate a human reading the problem — shorter delay for speed."""
    # Reduced delay: 1-4 seconds instead of 2-12s
    read_time_ms = max(1000, min(int(text_length / 50 * 1000), 4000))
    # Add randomness
    read_time_ms = int(read_time_ms * random.uniform(0.6, 1.2))
    print(f"[*] Simulating reading for {read_time_ms/1000:.1f}s...")
    # During reading, move mouse around and scroll
    elapsed = 0
    while elapsed < read_time_ms:
        action = random.choice(['scroll', 'jitter', 'wait'])
        if action == 'scroll':
            await human_scroll(page)
        elif action == 'jitter':
            await human_mouse_jitter(page)
        else:
            await page.wait_for_timeout(random.randint(300, 800))
        elapsed += random.randint(500, 1200)

# ─────────────────────────── SCRAPE PROBLEM ───────────────────────────

async def scrape_problem(page: Page) -> dict:
    """
    Scrape the problem. The editor is fill-in-the-blank:
      - Top <pre> = locked skeleton code above the blank
      - Ace Editor (#ctutortxtCode) = the editable blank
      - Bottom <pre> = locked skeleton code below the blank
    """
    await page.wait_for_timeout(1000)
    
    # DEBUG: Dump the page HTML so we can analyze its structure
    try:
        html_content = await page.content()
        with open("page_dump.html", "w", encoding="utf-8") as f:
            f.write(html_content)
        print("[DEBUG] Written page_dump.html")
    except Exception as e:
        print(f"[DEBUG] Failed to write page dump: {e}")

    problem_info = {}

    # 1. Get question text from left panel
    try:
        question_text = await page.evaluate("""() => {
            // Target the question card inside #programgrid (left column)
            // NOT the "Back To Challenges List" button area above it
            const programGrid = document.getElementById('programgrid');
            if (programGrid) {
                const leftCell = programGrid.querySelector('.ui-panelgrid-cell.ui-g-12.ui-md-6');
                if (leftCell) {
                    const card = leftCell.querySelector('.ui-card-content');
                    if (card) return card.innerText.trim();
                    return leftCell.innerText.trim();
                }
            }
            // Fallback: try any card content on the page
            const cards = Array.from(document.querySelectorAll('.ui-card-content'));
            for (const card of cards) {
                const text = card.innerText.trim();
                // The question card typically has 'ProgramID' or problem description keywords
                if (text.includes('ProgramID') || text.includes('Example') || text.includes('Input') || text.includes('Output') || text.length > 200) {
                    return text;
                }
            }
            return document.body.innerText.substring(0, 3000);
        }""")
        problem_info["question"] = question_text
    except Exception as e:
        problem_info["question"] = ""

    # 2. Get skeleton code from right panel (top pre, ace editor, bottom pre)
    try:
        skeleton = await page.evaluate("""() => {
            // Try #codediv first (standard layout), then #multifibpanel (MFIB layout)
            let codediv = document.getElementById('codediv');
            let is_mfib = false;
            if (!codediv) {
                codediv = document.getElementById('multifibpanel');
                if (codediv) is_mfib = true;
            }
            if (!codediv) {
                // Broader fallback: any panel with pre+input
                codediv = document.querySelector('[id*="multifib"], [id*="codeeditor"], #programgrid');
            }
            if (!codediv) return { top: '', bottom: '', ace_content: '', has_ace: false, skeletons: [], gaps: [], is_mfib: false, layout: [] };
            
            let skeletons = [];
            let gaps = [];
            let layout = [];
            let skeleton_count = 0;
            let gap_count = 0;
            let allInputs = Array.from(codediv.querySelectorAll('pre, .ace_editor, input, textarea'));
            
            let focusable = allInputs.filter(e => {
                let tag = e.tagName.toLowerCase();
                if (tag === 'input' && (e.type === 'hidden' || e.type === 'submit' || e.type === 'button' || e.type === 'radio' || e.type === 'checkbox')) return false;
                if (e.offsetHeight === 0 && tag !== 'pre') return false;
                if (e.closest('.ace_editor') && !e.classList.contains('ace_editor')) return false;
                
                // Exclude PrimeFaces dropdowns, selectors, and readonly labels
                if (e.classList && (e.classList.contains('ui-selectonemenu-label') || e.classList.contains('ui-selectonemenu-focus'))) return false;
                if (e.closest('.ui-selectonemenu')) return false;
                if (tag === 'input' && e.readOnly) return false;
                
                return true;
            });
            
            focusable.sort((a,b) => a.getBoundingClientRect().top - b.getBoundingClientRect().top);
            
            let has_ace = false;
            for (let el of focusable) {
                if (el.tagName.toLowerCase() === 'pre') {
                    skeletons.push(el.innerText);
                    layout.push({ type: 'skeleton', index: skeleton_count++, text: el.innerText });
                } else if (el.classList.contains('ace_editor')) {
                    has_ace = true;
                    let val = '';
                    try { val = ace.edit(el).getValue(); } catch(e) {}
                    if (!el.id) el.id = 'editor_gap_ace_' + Math.floor(Math.random()*1000000);
                    gaps.push({ id: el.id, content: val, is_input: false, size: 0 });
                    layout.push({ type: 'gap', index: gap_count++, id: el.id, content: val, is_input: false, size: 0 });
                } else if (el.tagName.toLowerCase() === 'input' || el.tagName.toLowerCase() === 'textarea') {
                    if (!el.id) el.id = 'editor_gap_input_' + Math.floor(Math.random()*1000000);
                    let size_attr = parseInt(el.getAttribute('size') || '30');
                    gaps.push({ id: el.id, class: el.className || '', content: el.value, is_input: true, size: size_attr });
                    layout.push({ type: 'gap', index: gap_count++, id: el.id, class: el.className || '', content: el.value, is_input: true, size: size_attr });
                }
            }
            
            const top_code = skeletons.length > 0 ? skeletons[0] : '';
            const bottom_code = skeletons.length > 1 ? skeletons[skeletons.length - 1] : '';
            const ace_content = gaps.length > 0 ? gaps[0].content : '';
            
            return { top: top_code, bottom: bottom_code, ace_content, has_ace, skeletons, gaps, is_mfib, layout };
        }""")
        problem_info["skeleton_top"] = skeleton.get("top", "")
        problem_info["skeleton_bottom"] = skeleton.get("bottom", "")
        problem_info["existing_code"] = skeleton.get("ace_content", "")
        problem_info["has_ace"] = skeleton.get("has_ace", False)
        problem_info["skeletons"] = skeleton.get("skeletons", [])
        problem_info["gaps"] = skeleton.get("gaps", [])
        problem_info["is_mfib"] = skeleton.get("is_mfib", False)
        problem_info["layout"] = skeleton.get("layout", [])
    except:
        problem_info["skeleton_top"] = ""
        problem_info["skeleton_bottom"] = ""
        problem_info["existing_code"] = ""
        problem_info["has_ace"] = False
        problem_info["skeletons"] = []
        problem_info["gaps"] = []
        problem_info["is_mfib"] = False

    # 3. Get language
    try:
        language = await page.evaluate(r"""() => {
            // Check primefaces dropdown labels (can be <span> or <label>)
            const labels = Array.from(document.querySelectorAll('.ui-selectonemenu-label, label.ui-selectonemenu-label'));
            for (let l of labels) {
                let t = l.innerText.toLowerCase().trim();
                if (t.includes('python')) return 'python';
                if (t.includes('java')) return 'java';
                if (t.includes('c++') || t.includes('cpp')) return 'cpp';
                if (t.match(/^c\s*\(/) || t === 'c') return 'c';
            }
            
            // Fallback to select tags (hidden <select> behind PrimeFaces)
            const selects = Array.from(document.querySelectorAll('select'));
            for (let s of selects) {
                if (s.options && s.selectedIndex >= 0) {
                    let t = s.options[s.selectedIndex].text.toLowerCase().trim();
                    if (t.includes('python')) return 'python';
                    if (t.includes('java')) return 'java';
                    if (t.includes('c++') || t.includes('cpp')) return 'cpp';
                    if (t.match(/^c\s*\(/) || t === 'c') return 'c';
                }
            }
            
            // Fallback to breadcrumb trail (e.g. "Java Programming" or "C Programming")
            const breadcrumbs = Array.from(document.querySelectorAll('.ui-breadcrumb .ui-menuitem-text'));
            for (let bc of breadcrumbs) {
                let t = bc.innerText.toLowerCase().trim();
                if (t.includes('python')) return 'python';
                if (t.includes('java')) return 'java';
                if (t.includes('c++') || t.includes('cpp')) return 'cpp';
                if (t.match(/^c\s+prog/) || t === 'c programming') return 'c';
            }
            
            // Fallback to pre tags with language class
            const pre = document.querySelector('pre[class*="language-"]');
            if (pre) { 
                const m = pre.className.match(/language-(\w+)/); 
                if (m) {
                    let c = m[1].toLowerCase();
                    if (c === 'csharp' || c === 'java') return 'java';
                    if (c === 'c') return 'c';
                    if (c === 'cpp' || c === 'c++') return 'cpp';
                    if (c === 'python' || c === 'py') return 'python';
                }
            }
            
            // Last resort: check page body for language hints
            const bodyText = document.body.innerText.substring(0, 2000).toLowerCase();
            if (bodyText.includes('java programming') || bodyText.includes('java -')) return 'java';
            if (bodyText.includes('python programming') || bodyText.includes('python -')) return 'python';
            if (bodyText.includes('c++ programming') || bodyText.includes('cpp -')) return 'cpp';
            if (bodyText.includes('c programming') || bodyText.match(/\bc - /)) return 'c';
            
            return 'java'; // default fallback — most common on CodingPortal
        }""")
        problem_info["language"] = language.strip()
    except:
        problem_info["language"] = "python"

    # 4. Problem ID
    try:
        pid_text = await page.inner_text("body")
        import re
        pid_match = re.search(r'ProgramID[:\-\s]*(\d+)', pid_text)
        problem_info["problem_id"] = pid_match.group(1) if pid_match else "unknown"
    except:
        problem_info["problem_id"] = "unknown"

    # 5. Fill-in-blank detection
    has_skeleton = bool(problem_info["skeleton_top"].strip() or problem_info["skeleton_bottom"].strip())
    problem_info["is_fill_blank"] = has_skeleton

    print(f"[*] Skeleton top: {len(problem_info['skeleton_top'])} chars | bottom: {len(problem_info['skeleton_bottom'])} chars")
    print(f"[*] Fill-in-blank: {has_skeleton} | MFIB: {problem_info.get('is_mfib', False)} | Language: {problem_info['language']} | PID: {problem_info['problem_id']}")
    print(f"[*] Gaps found: {len(problem_info.get('gaps', []))} | Has Ace: {problem_info.get('has_ace', False)}")
    for i, gap in enumerate(problem_info.get('gaps', [])):
        print(f"    Gap {i+1}: id={gap.get('id','')} is_input={gap.get('is_input',False)} size={gap.get('size',0)}")

    return problem_info


# ─────────────────────────── LLM SOLVER ───────────────────────────

def build_prompt(problem_info: dict, previous_code: str = None, error_message: str = None) -> str:
    """Build the prompt — fill-in-blank aware + error feedback aware."""
    language = problem_info.get("language", "python")
    question = problem_info.get("question", "")
    gaps = problem_info.get("gaps", [])
    layout = problem_info.get("layout", [])

    lang_names = {"python": "Python 3", "java": "Java", "c": "C", "cpp": "C++"}
    lang_display = lang_names.get(language, language)

    # Reconstruct code with [GAP_N] inline placeholders
    reconstructed = ""
    for item in layout:
        if item["type"] == "skeleton":
            reconstructed += item["text"]
        elif item["type"] == "gap":
            reconstructed += f"[GAP_{item['index'] + 1}]"

    is_fill_blank = problem_info.get("is_fill_blank", False)

    # If it is a fill-in-the-blank (or multi-gap) problem
    if is_fill_blank or len(gaps) > 1:
        if len(gaps) == 1:
            # Single Gap
            prompt = f"""You are solving a {lang_display} fill-in-the-blank problem on CodingPortal.

PROBLEM DESCRIPTION:
{question}

COMPLETE CODE WITH PLACEHOLDER:
{reconstructed}

YOUR TASK:
Find the exact expression, code snippet, or characters that replace the placeholder [GAP_1] to make the code compile and run successfully.
CRITICAL: Do NOT rewrite or repeat any surrounding skeleton code. Output ONLY the exact code/value that goes into [GAP_1].

Wrap your replacement in a markdown code block (e.g., ```{language} ... ```).
Return ONLY the markdown code block. No explanations, apologies, or extra text.
"""
        else:
            # Multi-gap or inline inputs (Type C)
            blank_context = ""
            for gi, gap in enumerate(gaps):
                gap_type = "small input box (short expression/value)" if gap.get("is_input") else "code editor (logic block/statements)"
                blank_context += f"  GAP_{gi+1} placeholder is a {gap_type}.\n"

            prompt = f"""You are solving a {lang_display} multi-fill-in-the-blanks problem on CodingPortal.

PROBLEM DESCRIPTION:
{question}

COMPLETE CODE WITH PLACEHOLDERS:
{reconstructed}

IMPORTANT: There are EXACTLY {len(gaps)} blanks indicated by [GAP_1], [GAP_2], ..., [GAP_{len(gaps)}]. Everything else is LOCKED skeleton code.

Placeholders description:
{blank_context}

YOUR TASK:
Provide the exact code/expression that replaces each [GAP_N] placeholder.
Output your answers in sections separated EXACTLY by "--- GAP X ---" on its own line.
Wrap the entire response in a markdown code block (e.g., ```{language} ... ```).
For example:
```{language}
--- GAP 1 ---
int a = 5;
--- GAP 2 ---
return a;
```

CRITICAL: Output EXACTLY {len(gaps)} gaps. Do not include any explanations, apologies, or markdown code fences inside the gaps. Return ONLY the markdown code block.
"""
    else:
        existing_code = problem_info.get("existing_code", "").strip()
        boilerplate = ""
        if existing_code:
            boilerplate = f"\nBOILERPLATE CODE IN EDITOR:\n```\n{existing_code}\n```\nEnsure your final code includes necessary headers/imports and builds upon or completes this boilerplate.\n"

        # Full code problem (Type A)
        prompt = f"""You are solving a {lang_display} coding problem on CodingPortal.

PROBLEM DESCRIPTION:
{question}
{boilerplate}
INSTRUCTIONS:
Write the COMPLETE {lang_display} program from scratch.
- Read input EXACTLY as described in the examples (e.g. scanf for C, input() for Python, Scanner for Java).
- Print output EXACTLY matching the expected format — same text, spacing, newlines, capitalization.
- Pay close attention to the Example Input/Output section for the exact format.
Wrap your code in a markdown code block (e.g., ```{language} ... ```).
Return ONLY the markdown code block. No explanations, apologies, or extra text.
"""

    if error_message and previous_code:
        prompt += f"""
=========================================
CRITICAL: PREVIOUS ATTEMPT FAILED!

Your previous code was:
{previous_code}

The compiler/system returned the following error or output mismatch:
{error_message}

INSTRUCTIONS TO FIX:
1. Identify the mistake in your previous code based on the error.
2. If it's a compiler error like 'expected declaration specifiers' or 'implicit declaration of function', you likely forgot to include standard headers (like #include <stdio.h>, #include <string.h>) or a proper main() function.
3. FIX THE ERROR without completely rewriting the core logic if it was already correct.
4. Output ONLY the corrected code inside a markdown block. No explanations!
"""

    # Append session memory learnings if available
    if session_memory:
        memory_text = "\n".join(f"- {m}" for m in session_memory[-10:])  # last 10 learnings
        prompt += f"""

LEARNINGS FROM THIS SESSION (apply these rules):
{memory_text}
"""

    return prompt


def get_solution(problem_info: dict, previous_code: str = None, error_message: str = None, retry_count: int = 0) -> str:
    """Call NVIDIA API or local Ollama with the problem and get the solution code.
    retry_count is used to escalate temperature on retries for diverse outputs."""
    prompt = build_prompt(problem_info, previous_code, error_message)
    language = problem_info.get("language", "python")
    gaps = problem_info.get("gaps", [])
    is_fill_blank = problem_info.get("is_fill_blank", False)

    # Select target system prompt depending on problem structure
    if not is_fill_blank or not gaps:
        # Full program
        system_prompt = (
            "You are an expert competitive programmer. "
            "You solve coding problems perfectly with 100% accuracy. "
            "You MUST write the COMPLETE, standalone program from scratch. "
            "The code MUST read input using scanf/input()/Scanner as shown in examples. "
            "The code MUST produce the EXACT expected output — same text, same case, same spacing, same newlines. "
        )
        if language in ["c", "cpp"]:
            system_prompt += (
                "CRITICAL: Because this is C/C++, you MUST include all necessary standard headers (like #include <stdio.h>) "
                "and wrap your logic in a proper 'int main()' function. Do not just output the logic alone! "
            )
        system_prompt += (
            f"You MUST wrap your final code in a markdown code block (e.g., ```{language} ... ```). "
            "Return ONLY the markdown code block. No explanation."
        )
    elif len(gaps) == 1:
        # Single gap / blank
        system_prompt = (
            "You are an expert competitive programmer. "
            "You solve coding problems perfectly with 100% accuracy. "
            "You are solving a fill-in-the-blank coding problem. You are provided with locked skeleton code and exactly ONE missing gap.\n"
            "CRITICAL: You must write ONLY the missing code or expression that fits into the gap. "
            "Do NOT rewrite or include any code from the locked top or bottom sections. "
            "The combined code (top + your_gap_code + bottom) must compile and run correctly.\n"
            f"You MUST wrap your missing gap code in a markdown code block (e.g., ```{language} ... ```).\n"
            "Return ONLY the markdown code block containing ONLY the gap code. No explanations, apologies, or extra text."
        )
    else:
        # Multi gap (MFIB)
        system_prompt = (
            "You are an expert competitive programmer. "
            "You solve coding problems perfectly with 100% accuracy. "
            "You are solving a multi-fill-in-the-blank coding problem with multiple distinct missing code segments or input fields.\n"
            "CRITICAL: You must provide ONLY the code or expression for each missing gap. Do NOT write a complete program. "
            "You MUST format your output by specifying each gap's content separated by GAP markers, like this:\n"
            "--- GAP 1 ---\n"
            "<code for gap 1>\n"
            "--- GAP 2 ---\n"
            "<code for gap 2>\n"
            "Wrap this entire formatted response inside a markdown code block.\n"
            "Return ONLY this markdown code block. No explanations, apologies, or extra text."
        )

    # Escalate temperature on retries to get different answers
    temp = min(0.1 + retry_count * 0.2, 0.9)
    if retry_count > 0:
        print(f"[*] Retry #{retry_count} — using temperature {temp:.1f}")

    print(f"[*] Language: {problem_info.get('language', 'unknown')}")
    print(f"[*] Problem ID: {problem_info.get('problem_id', 'unknown')}")

    try:
        # Dynamic routing: if both are true, NVIDIA is try 0, Gemini is try > 0
        active_gemini = USE_GEMINI
        active_nvidia = USE_NVIDIA
        
        if USE_GEMINI and USE_NVIDIA:
            if retry_count == 0:
                active_gemini = False
            else:
                active_nvidia = False

        if active_gemini:
            print(f"[*] Sending problem to Gemini ({GEMINI_MODEL})...")
            client = OpenAI(
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                api_key=GEMINI_API_KEY
            )
            # Retry logic for Gemini 503 (high demand) errors
            gemini_retries = 3
            for attempt in range(gemini_retries):
                try:
                    response = client.chat.completions.create(
                        model=GEMINI_MODEL,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": prompt}
                        ],
                        temperature=temp,
                        max_tokens=8192,
                    )
                    solution = response.choices[0].message.content.strip()
                    break
                except Exception as gemini_err:
                    err_str = str(gemini_err)
                    if ("503" in err_str or "429" in err_str or "UNAVAILABLE" in err_str) and attempt < gemini_retries - 1:
                        wait_secs = 3 * (2 ** attempt)  # 3s, 6s, 12s
                        print(f"[!] Gemini busy (attempt {attempt+1}/{gemini_retries}), retrying in {wait_secs}s...")
                        time.sleep(wait_secs)
                    else:
                        raise  # Re-raise for outer handler
        elif USE_NEBIUS and NEBIUS_API_KEY:
            model_to_use = FAST_MODEL if retry_count == 0 else THINKING_MODEL
            print(f"[*] Sending problem to Nebius Token Factory (NVIDIA {model_to_use})...")
            client = OpenAI(
                base_url=NEBIUS_BASE_URL,
                api_key=NEBIUS_API_KEY
            )
            response = client.chat.completions.create(
                model=model_to_use,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                temperature=temp,
                max_tokens=8192,
            )
            solution = response.choices[0].message.content.strip()
        elif active_nvidia:
            model_to_use = FAST_MODEL if retry_count == 0 else THINKING_MODEL
            print(f"[*] Sending problem to NVIDIA NIM ({model_to_use})...")
            client = OpenAI(
                base_url="https://integrate.api.nvidia.com/v1",
                api_key=NVIDIA_API_KEY
            )
            response = client.chat.completions.create(
                model=model_to_use,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                temperature=temp,
                max_tokens=8192,
            )
            solution = response.choices[0].message.content.strip()
        else:
            print(f"[*] Sending problem to local Ollama ({OLLAMA_MODEL})...")
            response = ollama.chat(
                model=OLLAMA_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                options={"temperature": temp, "num_predict": 2048, "num_ctx": 4096},
            )
            solution = response["message"]["content"].strip()

        # Clean up any markdown/code fences the model might have added
        solution = clean_code_output(solution)

        print(f"[+] Got solution ({len(solution)} chars)")
        return solution

    except Exception as e:
        print(f"[-] Error calling LLM: {e}")
        return ""


def clean_code_output(code: str) -> str:
    """Remove thinking tags, markdown code fences, and conversational text."""
    # 1. Remove <think>...</think> blocks (often used by reasoning models)
    code = re.sub(r'<think>.*?</think>', '', code, flags=re.DOTALL | re.IGNORECASE)
    
    # 2. Extract code from markdown fences if present
    # This ensures conversational text outside the code blocks is ignored.
    if '```' in code:
        blocks = []
        parts = code.split('```')
        # Even indices (0, 2, 4...) are text outside code blocks.
        # Odd indices (1, 3, 5...) are text inside code blocks.
        for i in range(1, len(parts), 2):
            block = parts[i]
            # Remove the language identifier (e.g., 'python\n' or 'c\n')
            block = re.sub(r'^[a-zA-Z0-9\+\-]*\s*\n', '', block)
            blocks.append(block.strip())
        
        if blocks:
            code = "\n".join(blocks)
            
    # 3. Safety net: If no code blocks are found, but the output is suspiciously long,
    # it's likely a truncated thought process that hit the token limit.
    if '```' not in code and len(code) > 2500:
        print("[-] Output is very long and has no code fences. Likely truncated reasoning. Rejecting.")
        return ""

    # 4. Clean up any remaining markdown just in case (fallback)
    code = re.sub(r'^```\w*\s*\n?', '', code, flags=re.MULTILINE)
    code = re.sub(r'\n?```\s*$', '', code, flags=re.MULTILINE)
    code = code.replace("```", "")
    
    return code.strip()


# ─────────────────────────── TYPE SOLUTION ───────────────────────────

async def type_solution(page: Page, code: str, problem_info: dict):
    """
    Type the solution into the editor physically.
    CodingPortal blocks JS injection (setValue/insert), so we must physically type.
    For Ace editors: type line-by-line with careful indentation clearing.
    For <input> fields: type inline.
    """
    print("[*] Typing solution into editor(s)...")

    gaps = problem_info.get("gaps", [])
    is_multi_gap = len(gaps) > 1

    import re
    gap_texts = {}
    
    # Always try to parse --- GAP N --- markers from LLM output first
    current_gap = -1
    lines = code.split('\n')
    
    for line in lines:
        m = re.match(r'^---\s*GAP\s*(\d+)\s*---(.*)', line.strip())
        if m:
            current_gap = int(m.group(1)) - 1
            gap_texts[current_gap] = []
            # Capture answer text on the same line as the marker
            # e.g. "--- GAP 1 --- sc.nextInt()" → captures "sc.nextInt()"
            inline_answer = m.group(2).strip()
            if inline_answer:
                gap_texts[current_gap].append(inline_answer)
        elif current_gap >= 0:
            gap_texts[current_gap].append(line)
    
    # Also try BLANK markers if no GAP markers found
    if not gap_texts:
        blank_answers = re.findall(r'BLANK_?\d*\s*[:=]\s*(.+)', code)
        for idx, answer in enumerate(blank_answers):
            gap_texts[idx] = [answer.strip()]
    
    # If no markers found at all, distribute lines across gaps
    if not gap_texts:
        lines_clean = [l.strip() for l in code.split('\n') if l.strip()]
        if len(gaps) > 1 and len(lines_clean) >= len(gaps):
            # One line per gap (for input-box blanks that expect short expressions)
            for idx in range(len(gaps)):
                gap_texts[idx] = [lines_clean[idx]]
            print(f"[*] Distributed {len(gaps)} lines across {len(gaps)} gaps (no markers found)")
        elif len(gaps) > 1 and len(lines_clean) > 0:
            # Fewer lines than gaps — assign what we have, leave rest empty
            for idx, line in enumerate(lines_clean):
                gap_texts[idx] = [line]
            print(f"[!] Only {len(lines_clean)} lines for {len(gaps)} gaps")
        else:
            # Single gap or single line — put everything in gap 0
            gap_texts[0] = code.split('\n')

    # Disable Ace Editor's auto-bracket and auto-indent via JS
    await page.evaluate("""() => {
        let editors = document.querySelectorAll('.ace_editor');
        for (const el of editors) {
            try {
                let ed = ace.edit(el);
                ed.setBehavioursEnabled(false);   // Disables auto-brackets
                ed.setOption("enableAutoIndent", false); // Disables auto-indent staircase effect
                ed.setOption("autoIndent", false);
                ed.session.setUseWorker(false);   // Disables background syntax worker
            } catch(e) {}
        }
    }""")

    for i in range(max(1, len(gaps))):
        gap_code = "\n".join(gap_texts.get(i, [])).strip()
        if not gap_code and is_multi_gap: 
            print(f"[-] No code parsed for GAP {i+1}")
            continue
        
        print(f"[*] Typing into GAP {i+1}...")
        
        is_input = gaps[i].get("is_input", False) if i < len(gaps) else False
        gap_id = gaps[i].get("id", "") if i < len(gaps) else ""

        if is_input:
            # ── Handle plain <input> / <textarea> fields ──
            if gap_id:
                try:
                    selector = f"[id='{gap_id}']"
                    await page.locator(selector).click(timeout=3000, force=True)
                    await page.wait_for_timeout(200)
                    await page.keyboard.press("Control+a")
                    await page.keyboard.press("Delete")
                    await page.wait_for_timeout(100)
                    # For input fields, type inline (no newlines) with human-like delay
                    clean_val = gap_code.replace('\n', ' ').strip()
                    # Type the whole value fast but visibly (20ms delay per char)
                    await page.keyboard.type(clean_val, delay=20)
                    print(f"[+] Filled input #{gap_id} with: {clean_val}")
                except Exception as e:
                    print(f"[-] Could not fill input #{gap_id}: {e}")
        else:
            # ── Handle Ace Editor gaps ── Physical typing ──
            clicked = False
            if gap_id:
                try:
                    await page.locator(f"[id='{gap_id}']").click(timeout=3000, force=True)
                    clicked = True
                except Exception as e:
                    print(f"[-] Could not click #{gap_id}: {e}")
            
            if not clicked:
                try:
                    ace_el = page.locator("#ctutortxtCode, #ctracktxtCode, #txtEditor, .ace_editor").first
                    await ace_el.click(timeout=5000, force=True)
                    clicked = True
                except:
                    print(f"[-] Could not find editor for GAP {i+1}")
                    continue

            await page.wait_for_timeout(300)

            # Select all and delete existing content
            await page.keyboard.press("Control+a")
            await page.keyboard.press("Delete")
            await page.wait_for_timeout(200)

            # Type the code fast, but not instantly, to look somewhat human (15ms delay)
            await page.keyboard.type(gap_code, delay=15)

        await page.wait_for_timeout(300)

    print(f"[+] Successfully typed {len(code)} characters")
    await page.wait_for_timeout(500)


# ─────────────────────────── RUN & CHECK ───────────────────────────

async def click_run(page: Page) -> tuple[bool, str]:
    """Click the Run button and check if the solution passes."""
    print("[*] Clicking Run...")

    try:
        # Find the Run button — scroll into view and force-click to handle offscreen cases
        run_btn = page.locator("button:has-text('Run'), input[value='Run'], a:has-text('Run')").first
        await run_btn.scroll_into_view_if_needed(timeout=3000)
        await page.wait_for_timeout(300)
        await run_btn.click(timeout=5000, force=True)
    except:
        # Fallback: try to find by specific button selector and force-click
        try:
            run_fallback = page.locator("button span.ui-button-text:has-text('Run')").first
            await run_fallback.scroll_into_view_if_needed(timeout=3000)
            await run_fallback.click(timeout=5000, force=True)
        except Exception as e:
            print(f"[-] Could not find Run button: {e}")
            return False, "Could not find Run button."

    # Wait for execution dynamically (up to 20 seconds)
    print("[*] Waiting dynamically for execution results...")
    await page.wait_for_timeout(2000) # baseline wait for older execution blocks to physically clear
    
    passed = False
    for _ in range(20):
        try:
            if await page.locator("text=/Congratulations! Your Code has passed|Great! Your code has passed|SUCCESS/i").first.is_visible():
                passed = True
                break
            if await page.locator("text=Code did not pass the execution").first.is_visible():
                passed = False
                break
        except:
            pass
        await page.wait_for_timeout(1000)

    # Scrape string details if we failed
    error_details = ""
    if not passed:
        error_details = await page.evaluate("""() => {
            let errorDetails = "";
            const bodyTextRefined = document.body.innerText;
            const errStart = bodyTextRefined.indexOf('Code did not pass the execution');
            
            if (errStart !== -1) {
                errorDetails = bodyTextRefined.substring(errStart, errStart + 3000);
            } else {
                const outIndex = bodyTextRefined.indexOf('Your Program Output:');
                const expIndex = bodyTextRefined.indexOf('Expected Output:');
                
                if (outIndex !== -1) {
                    const startIndex = Math.min(
                        expIndex !== -1 ? expIndex : outIndex,
                        outIndex
                    );
                    errorDetails = bodyTextRefined.substring(startIndex, startIndex + 3000);
                }
            }
            
            if (!errorDetails || errorDetails.length < 20) {
                const errNodes = document.querySelectorAll('.ui-messages-error, .ui-message-error, .errormsg');
                for (let el of errNodes) {
                    if (el.innerText && el.innerText.trim().length > 0) {
                        errorDetails += el.innerText.trim() + "\\n\\n";
                    }
                }
            }
            return errorDetails.trim().substring(0, 3000);
        }""")
        
    print(f"[*] Result: {'PASSED' if passed else 'FAILED'}")
    if not passed:
        print(f"[*] Error details preview: {error_details[:200]}...")
    return passed, error_details


async def click_next(page: Page) -> bool:
    """Click the Next button to go to the next problem. Returns False if no Next button found (module ended)."""
    print("[*] Looking for Next button...")
    await page.wait_for_timeout(NEXT_WAIT_SECONDS * 1000)

    try:
        # Look for Next/Next Program button
        next_btn = page.locator(
            "button:has-text('Next'), "
            "input[value='Next'], "
            "a:has-text('Next'), "
            "button:has-text('next'), "
            "a:has-text('next program'), "
            "button:has-text('Next Program')"
        ).first

        if await next_btn.is_visible(timeout=5000):
            await next_btn.click()
            print("[+] Clicked Next, loading next problem...")
            await page.wait_for_timeout(3000)
            return True
        else:
            print("[!] Next button not visible")
            return False
    except Exception as e:
        print(f"[!] No Next button found: {e}")
        return False


# ─────────────────────────── CAPTCHA HANDLER ───────────────────────────

async def handle_captcha(page: Page) -> bool:
    """
    Handle the captcha/proceed page that appears before each problem.
    The captcha is a base64 PNG image (id='j_id_5s') containing a simple
    math expression like '34+4='. We use pytesseract OCR to read it.
    Answer field is input#capval. Proceed button is #proceedbtn.
    """
    try:
        page_text = await page.inner_text("body")

        # Check if a "Proceed to Solve" button exists
        if "Proceed to Solve" not in page_text:
            return False

        print("[*] Captcha page detected!")

        # Check if capval input exists
        capval = page.locator("input#capval")
        if await capval.count() == 0:
            # No captcha input — just click Proceed
            print("[*] No captcha input found, clicking Proceed...")
            try:
                await page.locator("#proceedbtn").click()
                await page.wait_for_timeout(3000)
            except:
                pass
            return True

        # Extract the base64 captcha image from the <img> tag
        captcha_b64 = await page.evaluate("""() => {
            // The captcha image is typically an <img> with a data:image/png;base64 src
            // near the capval input
            const imgs = document.querySelectorAll('img[src^="data:image"]');
            for (const img of imgs) {
                const rect = img.getBoundingClientRect();
                // The captcha image is in the right-side panel (x > 400)
                if (rect.x > 400 && rect.width > 100) {
                    return img.src;  // Returns the full data URI
                }
            }
            return null;
        }""")

        if not captcha_b64:
            print("[!] No captcha image found. Trying to click Proceed anyway...")
            try:
                await page.locator("#proceedbtn").click()
                await page.wait_for_timeout(3000)
            except:
                pass
            return True

        # Decode the base64 image and run OCR
        import base64
        import io
        import numpy as np
        from PIL import Image, ImageOps
        import easyocr

        print("[*] Running OCR on captcha image...")

        # Strip the data URI prefix and fix padding
        b64_data = captcha_b64.split(",", 1)[1]
        b64_data += "=" * (4 - len(b64_data) % 4)  # Fix padding
        img_bytes = base64.b64decode(b64_data)
        img = Image.open(io.BytesIO(img_bytes))

        # Preprocess for better OCR
        img = img.convert("L")  # Grayscale
        img = ImageOps.invert(img)  # Invert (white text on black → black on white)
        img = img.point(lambda x: 255 if x > 100 else 0)  # Binary threshold
        img = img.resize((img.width * 3, img.height * 3), Image.LANCZOS)  # Scale up

        # Convert to numpy array for easyocr
        img_array = np.array(img)

        # Run easyocr on CPU
        reader = easyocr.Reader(['en'], gpu=False)
        results = reader.readtext(img_array, allowlist='0123456789+-*=x ')

        # CRITICAL: Free ALL easyocr/PyTorch memory (CPU + GPU) immediately
        # so Ollama can use the GPU VRAM for LLM inference
        del reader
        del img_array
        del img
        import gc
        gc.collect()
        try:
            import torch
            torch.cuda.empty_cache()
        except:
            pass

        captcha_text = ""
        for (bbox, text, conf) in results:
            captcha_text += text + " "
        captcha_text = captcha_text.strip()

        print(f"[*] OCR raw results: {[(t, round(c,2)) for (_, t, c) in results]}")

        # Parse the math expression — check each OCR result individually
        # to avoid matching digits from the username (2117240080075)
        import re as _re
        match = None
        # First: check each OCR result separately for a math expression
        for (bbox, text, conf) in results:
            # Match 1-3 digit numbers with an operator and optional =
            m = _re.search(r'(\d{1,3})\s*([+\-*x])\s*(\d{1,3})\s*=?', text)
            if m:
                match = m
                print(f"[*] Found math in OCR segment: '{text}'")
                break
        # Fallback: try the full concatenated text
        if not match:
            match = _re.search(r'(\d{1,3})\s*([+\-*x])\s*(\d{1,3})\s*=?', captcha_text)
        if match:
            num1 = int(match.group(1))
            op = match.group(2)
            num2 = int(match.group(3))

            if op == "+":
                answer = num1 + num2
            elif op == "-":
                answer = num1 - num2
            elif op in ["*", "x"]:
                answer = num1 * num2
            else:
                answer = num1 + num2

            print(f"[+] Captcha: {num1}{op}{num2} = {answer}")

            # Type answer into capval input
            await capval.click()
            await page.wait_for_timeout(200)
            await page.keyboard.press("Control+a")
            await page.keyboard.press("Delete")
            await page.keyboard.type(str(answer), delay=30)
            await page.wait_for_timeout(300)
        else:
            print(f"[!] Could not parse math from OCR result: '{captcha_text}'")
            print("[*] Please solve captcha manually, then press Enter...")
            await asyncio.get_event_loop().run_in_executor(None, input)

        # Click "Proceed to Solve the Program"
        await page.wait_for_timeout(500)
        try:
            await page.locator("#proceedbtn").click()
            print("[+] Clicked Proceed! Waiting for problem to load...")
            await page.wait_for_timeout(3000)
            return True
        except:
            try:
                await page.locator("text=Proceed to Solve the Program").first.click()
                await page.wait_for_timeout(3000)
                return True
            except:
                return False

    except Exception as e:
        print(f"[!] Captcha error: {e}")
        import traceback
        traceback.print_exc()
        return False


# ─────────────────────────── MAIN LOOP ───────────────────────────

async def solve_current_problem(page: Page) -> bool:
    """Solve the current problem on the page. Returns True if solved and ready for next."""

    # Check if this is a tutorial or already passed page BEFORE doing anything
    try:
        page_text = await page.inner_text("body")
        page_lower = page_text.lower() if page_text else ""
        if "congratulations! your code has passed" in page_lower or "great! your code has passed" in page_lower:
            print("[+] Page is already marked as passed (or is a tutorial slide)!")
            return "skipped"
            
        next_btn = page.locator("a:has-text('Proceed Next'), button:has-text('Proceed Next')").first
        if await next_btn.is_visible(timeout=2000):
            print("[+] Found 'Proceed Next' button before solving! This is likely a tutorial slide or already solved page.")
            return "skipped"
    except:
        pass

    # Check for captcha first
    await handle_captcha(page)

    # Step 1: Scrape the problem
    print("\n" + "=" * 60)
    print("[STEP 1] Scraping problem...")
    problem_info = await scrape_problem(page)

    if not problem_info.get("question"):
        print("[-] Could not scrape problem. Skipping.")
        return "failed"

    print(f"[+] Problem scraped (Language: {problem_info['language']}, ID: {problem_info['problem_id']})")

    # Show a preview of the question
    question_preview = problem_info["question"][:200].replace("\n", " ")
    print(f"[+] Question preview: {question_preview}...")

    # Simulate human reading the problem before solving
    await simulate_reading(page, len(problem_info.get('question', '')))
    await human_mouse_jitter(page)

    # Step 2: Get solution from LLM
    print("\n[STEP 2] Getting solution from LLM...")
    solution = get_solution(problem_info)

    if not solution:
        print("[-] No solution generated. Skipping.")
        return "failed"

    print(f"[+] Solution preview:\n{solution[:300]}...")

    # Step 3: Type the solution (with human-like pause before starting)
    print("\n[STEP 3] Typing solution into editor...")
    await human_pause(page, 800, 2500)  # Brief think before typing
    await human_mouse_jitter(page)
    await type_solution(page, solution, problem_info)

    # Step 4: Click Run (with a human pause — review before running)
    print("\n[STEP 4] Running solution...")
    await human_pause(page, 1000, 3000)  # Brief review before clicking Run
    await human_mouse_jitter(page)
    passed, error_details = await click_run(page)

    retry_count = 0
    max_retries = MAX_RETRIES
    
    while not passed and retry_count < max_retries:
        retry_count += 1
        print(f"\n[!] Solution failed! Error details extracted. Attempt {retry_count}/{max_retries} to fix with LLM...")
        
        # Learn from the error for this session
        if error_details and problem_info.get('gaps'):
            if "';' expected" in error_details:
                lesson = f"For {problem_info.get('language', 'java').upper()} MFIB: When the skeleton code after a blank does NOT start with ';', include the semicolon in your answer (e.g. 'sc.nextInt();' not 'sc.nextInt()')."
                if lesson not in session_memory:
                    session_memory.append(lesson)
                    print(f"[MEMORY] Learned: {lesson[:80]}...")
            if "illegal start of expression" in error_details:
                lesson = f"For {problem_info.get('language', 'java').upper()} MFIB: Do NOT output more GAPs than blanks. Check the blank count carefully."
                if lesson not in session_memory:
                    session_memory.append(lesson)
                    print(f"[MEMORY] Learned: {lesson[:80]}...")
        
        # Get solution fixing the problem (with escalating temperature)
        solution = get_solution(problem_info, previous_code=solution, error_message=error_details, retry_count=retry_count)
        if not solution:
            print("[-] Could not get fixed solution. Proceeding to fallback.")
            break
            
        print(f"\n[STEP 3 - FIX ATTEMPT {retry_count}] Typing solution into editor...")
        await type_solution(page, solution, problem_info)
        
        print(f"\n[STEP 4 - FIX ATTEMPT {retry_count}] Running solution...")
        passed, error_details = await click_run(page)

    # Fallback: if it fails, try clicking Run again to force the Solution button to appear (if user has enabled it via failing twice)
    # Fallback: if it fails, the Solution button should be available naturally. Fetch it!
    if not passed:
        print("[!] Max retries reached with LLM. Looking for official Solution button...")
        try:
            sol_btn = page.locator("a:has-text('Solution'), button:has-text('Solution'), span:has-text('Solution')").filter(has_text="Solution").first
            if await sol_btn.is_visible(timeout=3000):
                print("[*] Found CodingPortal 'Solution' button! Clicking it...")
                await sol_btn.click()
                await page.wait_for_timeout(1500)

                # Scrape the official solution from the modal/page
                print("[*] Extracting official solution...")
                official_code = await page.evaluate('''() => {
                    let preTags = Array.from(document.querySelectorAll('pre, code, .modal-body pre, .modal-body code'));
                    preTags = preTags.filter(el => !el.closest('#tdprobcode') && el.offsetHeight > 0);
                    if (preTags.length > 0) {
                        return preTags[preTags.length - 1].innerText;
                    }
                    return "";
                }''')

                if official_code:
                    official_code = official_code.strip()
                    
                    if problem_info.get("is_fill_blank"):
                        # CodingPortal's Solution modal provides the full program. We must slice out the skeleton.
                        top_lines = [line.strip() for line in problem_info.get("skeleton_top", "").split('\\n') if line.strip()]
                        if top_lines:
                            last_top_line = top_lines[-1]
                            idx = official_code.find(last_top_line)
                            if idx != -1:
                                official_code = official_code[idx + len(last_top_line):]

                        bottom_lines = [line.strip() for line in problem_info.get("skeleton_bottom", "").split('\\n') if line.strip()]
                        if bottom_lines:
                            first_bottom_line = bottom_lines[0]
                            idx = official_code.rfind(first_bottom_line)
                            if idx != -1:
                                official_code = official_code[:idx]
                                
                        official_code = official_code.strip()

                    print(f"[+] Extracted official solution ({len(official_code)} chars). Typing it now...")
                    await type_solution(page, official_code, problem_info)
                    print("[*] Running official solution...")
                    passed, _ = await click_run(page)
        except Exception as e:
            print(f"[-] Could not use Solution fallback: {e}")

    if not passed:
        print("[!] Ultimately Failed. Moving to next question.")
        return "failed"

    return "solved"



