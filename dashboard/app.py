import os
import sys
import sqlite3
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional, List
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import psutil

# Ensure app-level import paths work
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.append(str(PROJECT_ROOT))

# Paths
DB_DIR = PROJECT_ROOT / "db"
LOG_DIR = PROJECT_ROOT / "logs"
CENTRAL_DB_PATH = DB_DIR / "students.db"

DB_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

# Lifespan events
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_central_db()
    yield

# FastAPI initialization
app = FastAPI(title="NemotronCoder Multi-Agent Orchestrator", lifespan=lifespan)

# Jinja2 Templates setup
templates = Jinja2Templates(directory=str(PROJECT_ROOT / "dashboard" / "templates"))

# Pydantic Schemas
class StudentCreate(BaseModel):
    username: str
    password: str
    target_count: int = 10
    headless: bool = True

class StudentUpdate(BaseModel):
    password: Optional[str] = None
    target_count: Optional[int] = None
    headless: Optional[bool] = None

class CaptchaSolve(BaseModel):
    captcha_id: int
    answer: str


# Database helpers
def init_central_db():
    conn = sqlite3.connect(str(CENTRAL_DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS students (
            username TEXT PRIMARY KEY,
            password TEXT NOT NULL,
            target_count INTEGER DEFAULT 10,
            headless INTEGER DEFAULT 1,
            pid INTEGER,
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

def get_students_db_connection():
    conn = sqlite3.connect(str(CENTRAL_DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

# Helper functions for cross-database access
def get_student_solved_count(username: str) -> int:
    progress_db = DB_DIR / f"{username}_progress.db"
    if not progress_db.exists():
        return 0
    try:
        conn = sqlite3.connect(str(progress_db))
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM problems WHERE status='solved'")
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else 0
    except Exception:
        return 0

def get_student_captcha_request(username: str) -> Optional[dict]:
    progress_db = DB_DIR / f"{username}_progress.db"
    if not progress_db.exists():
        return None
    try:
        conn = sqlite3.connect(str(progress_db))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT id, image_b64 FROM captcha_pending WHERE status='pending' LIMIT 1").fetchone()
        conn.close()
        return dict(row) if row else None
    except Exception:
        return None

def write_student_captcha_solution(username: str, captcha_id: int, answer: str) -> bool:
    progress_db = DB_DIR / f"{username}_progress.db"
    if not progress_db.exists():
        return False
    try:
        conn = sqlite3.connect(str(progress_db))
        conn.execute("UPDATE captcha_pending SET answer=?, status='solved' WHERE id=?", (answer, captcha_id))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"[-] Error solving captcha in DB for {username}: {e}")
        return False

def clear_student_captcha(username: str):
    progress_db = DB_DIR / f"{username}_progress.db"
    if not progress_db.exists():
        return
    try:
        conn = sqlite3.connect(str(progress_db))
        conn.execute("DELETE FROM captcha_pending")
        conn.commit()
        conn.close()
    except Exception:
        pass

# Process management
def is_process_running(pid: int) -> bool:
    if not pid:
        return False
    try:
        proc = psutil.Process(pid)
        if proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE:
            # Verify command line has run_automation
            cmdline = proc.cmdline()
            return any("run_automation.py" in arg for arg in cmdline)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass
    return False

def clean_zombie_pids():
    conn = get_students_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT username, pid FROM students WHERE pid IS NOT NULL")
    rows = cursor.fetchall()
    for row in rows:
        if not is_process_running(row["pid"]):
            cursor.execute("UPDATE students SET pid=NULL WHERE username=?", (row["username"],))
    conn.commit()
    conn.close()


# ─────────────────────────── HTML PAGES ───────────────────────────

@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


# ─────────────────────────── JSON REST API ───────────────────────────

@app.get("/api/students")
def get_students():
    # Sync database with active OS processes first
    clean_zombie_pids()
    
    conn = get_students_db_connection()
    students = conn.execute("SELECT * FROM students ORDER BY created_at DESC").fetchall()
    conn.close()
    
    result = []
    for s in students:
        s_dict = dict(s)
        username = s_dict["username"]
        pid = s_dict["pid"]
        
        # Calculate status
        is_running = is_process_running(pid)
        captcha_req = get_student_captcha_request(username)
        solved_count = get_student_solved_count(username)
        target_count = s_dict["target_count"]
        
        if is_running:
            status = "Captcha Pending" if captcha_req else "Running"
        else:
            status = "Completed" if (solved_count >= target_count and target_count > 0) else "Idle"
            
        result.append({
            "username": username,
            "target_count": target_count,
            "headless": bool(s_dict["headless"]),
            "solved_count": solved_count,
            "status": status,
            "pid": pid,
            "captcha_pending": captcha_req is not None
        })
        
    return result

@app.post("/api/students")
def add_student(student: StudentCreate):
    conn = get_students_db_connection()
    try:
        conn.execute(
            "INSERT INTO students (username, password, target_count, headless, created_at) VALUES (?, ?, ?, ?, ?)",
            (student.username, student.password, student.target_count, 1 if student.headless else 0, datetime.now().isoformat())
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(status_code=400, detail="Student profile already exists.")
    finally:
        conn.close()
    return {"status": "success", "message": "Student profile added."}

@app.put("/api/students/{username}")
def update_student(username: str, data: StudentUpdate):
    conn = get_students_db_connection()
    student = conn.execute("SELECT * FROM students WHERE username=?", (username,)).fetchone()
    if not student:
        conn.close()
        raise HTTPException(status_code=404, detail="Student not found.")
    
    # Check if running
    if is_process_running(student["pid"]):
        conn.close()
        raise HTTPException(status_code=400, detail="Cannot edit student while automation is running.")
        
    updates = []
    params = []
    
    if data.password is not None:
        updates.append("password = ?")
        params.append(data.password)
    if data.target_count is not None:
        updates.append("target_count = ?")
        params.append(data.target_count)
    if data.headless is not None:
        updates.append("headless = ?")
        params.append(1 if data.headless else 0)
        
    if updates:
        params.append(username)
        conn.execute(f"UPDATE students SET {', '.join(updates)} WHERE username=?", params)
        conn.commit()
        
    conn.close()
    return {"status": "success", "message": "Student profile updated."}

@app.delete("/api/students/{username}")
def delete_student(username: str):
    conn = get_students_db_connection()
    student = conn.execute("SELECT * FROM students WHERE username=?", (username,)).fetchone()
    if not student:
        conn.close()
        raise HTTPException(status_code=404, detail="Student not found.")
        
    # Stop process if running
    pid = student["pid"]
    if is_process_running(pid):
        try:
            parent = psutil.Process(pid)
            for child in parent.children(recursive=True):
                child.kill()
            parent.kill()
        except Exception:
            pass
            
    conn.execute("DELETE FROM students WHERE username=?", (username,))
    conn.commit()
    conn.close()
    
    # Delete progress database if exists
    progress_db = DB_DIR / f"{username}_progress.db"
    if progress_db.exists():
        try:
            os.remove(str(progress_db))
        except Exception:
            pass
            
    return {"status": "success", "message": "Student profile deleted."}

@app.post("/api/students/{username}/start")
def start_runner(username: str):
    conn = get_students_db_connection()
    student = conn.execute("SELECT * FROM students WHERE username=?", (username,)).fetchone()
    if not student:
        conn.close()
        raise HTTPException(status_code=404, detail="Student not found.")
        
    if is_process_running(student["pid"]):
        conn.close()
        raise HTTPException(status_code=400, detail="Automation is already running for this student.")

    # Reset any stale captcha from DB first
    clear_student_captcha(username)

    # Use virtual environment python if available, fallback to sys.executable
    venv_python = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
    python_exe = str(venv_python) if venv_python.exists() else sys.executable

    # Launch subprocess
    cmd = [
        python_exe,
        str(PROJECT_ROOT / "run_automation.py"),
        "--username", student["username"],
        "--password", student["password"],
        "--count", str(student["target_count"])
    ]
    if student["headless"]:
        cmd.append("--headless")
        
    # Open log file (append mode)
    log_file_path = LOG_DIR / f"{username}.log"
    log_file = open(str(log_file_path), "a", encoding="utf-8")
    log_file.write(f"\n\n--- Automation Started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---\n")
    log_file.flush()
    
    # Environment with isolated DB path
    env = os.environ.copy()
    env["AGENT_DB_PATH"] = str(DB_DIR / f"{username}_progress.db")
    
    try:
        process = subprocess.Popen(
            cmd,
            cwd=str(PROJECT_ROOT),
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True
        )
        
        # Save PID to DB
        conn.execute("UPDATE students SET pid=? WHERE username=?", (process.pid, username))
        conn.commit()
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=500, detail=f"Failed to start process: {str(e)}")
    finally:
        conn.close()
        
    return {"status": "success", "message": "Automation runner launched.", "pid": process.pid}

@app.post("/api/students/{username}/stop")
def stop_runner(username: str):
    conn = get_students_db_connection()
    student = conn.execute("SELECT * FROM students WHERE username=?", (username,)).fetchone()
    if not student:
        conn.close()
        raise HTTPException(status_code=404, detail="Student not found.")
        
    pid = student["pid"]
    if not is_process_running(pid):
        conn.execute("UPDATE students SET pid=NULL WHERE username=?", (username,))
        conn.commit()
        conn.close()
        return {"status": "success", "message": "Automation was not running."}
        
    try:
        parent = psutil.Process(pid)
        # Terminate all sub-browsers spawned by playwright
        for child in parent.children(recursive=True):
            try:
                child.kill()
            except Exception:
                pass
        parent.kill()
        
        # Append termination log
        log_file_path = LOG_DIR / f"{username}.log"
        if log_file_path.exists():
            with open(str(log_file_path), "a", encoding="utf-8") as f:
                f.write(f"\n--- Automation Stopped Manually at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---\n")
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=500, detail=f"Error stopping runner: {str(e)}")
        
    # Reset PID in DB
    conn.execute("UPDATE students SET pid=NULL WHERE username=?", (username,))
    conn.commit()
    conn.close()
    
    # Clear any active captcha block
    clear_student_captcha(username)
    
    return {"status": "success", "message": "Automation runner stopped successfully."}

@app.get("/api/students/{username}/logs")
def get_logs(username: str):
    log_file_path = LOG_DIR / f"{username}.log"
    if not log_file_path.exists():
        return {"logs": "No logs recorded yet."}
        
    try:
        with open(str(log_file_path), "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
            tail = "".join(lines[-150:]) # Return last 150 lines
            return {"logs": tail}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read logs: {str(e)}")

@app.get("/api/students/{username}/captcha")
def get_captcha(username: str):
    captcha_req = get_student_captcha_request(username)
    if not captcha_req:
        raise HTTPException(status_code=404, detail="No pending captcha found for this student.")
    return captcha_req

@app.post("/api/students/{username}/captcha/solve")
def solve_captcha(username: str, data: CaptchaSolve):
    success = write_student_captcha_solution(username, data.captcha_id, data.answer)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to write captcha answer.")
    return {"status": "success", "message": "Captcha solved! Resuming runner..."}


if __name__ == "__main__":
    import uvicorn
    # Make sure we run on 0.0.0.0 so external devices (like phone via Tailscale) can connect!
    uvicorn.run("dashboard.app:app", host="0.0.0.0", port=8000, reload=True)
