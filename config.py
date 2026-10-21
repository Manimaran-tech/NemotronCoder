# NemotronCoder: Autonomous Coding Agent Configuration
import os
from dotenv import load_dotenv

load_dotenv()

# CodingPortal Credentials
PORTAL_USERNAME = os.getenv("PORTAL_USERNAME", "your_username_here")
PORTAL_PASSWORD = os.getenv("PORTAL_PASSWORD", "your_password_here")
PORTAL_LOGIN_URL = "https://codebenchmark.internal/faces/candidate/codeprogram.xhtml"
PORTAL_TUTOR_URL = "https://codebenchmark.internal/faces/candidate/tutorprogram.xhtml"

# Ollama Configuration
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

# Nebius Token Factory / NVIDIA NIM Configuration
USE_NEBIUS = os.getenv("USE_NEBIUS", "true").lower() in ("true", "1", "yes")
NEBIUS_API_KEY = os.getenv("NEBIUS_API_KEY", "")
NEBIUS_BASE_URL = os.getenv("NEBIUS_BASE_URL", "https://api.tokenfactory.nebius.com/v1/")

# NVIDIA NIM / OpenAI Configuration (Primary/Fallback)
USE_NVIDIA = os.getenv("USE_NVIDIA", "true").lower() in ("true", "1", "yes")
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "your_nvidia_api_key_here")
FAST_MODEL = os.getenv("FAST_MODEL", "nvidia/nemotron-3-super-120b-a12b")
THINKING_MODEL = os.getenv("THINKING_MODEL", "nvidia/nemotron-3-super-120b-a12b")

# Gemini Configuration (Fallback/Retry Model)
USE_GEMINI = os.getenv("USE_GEMINI", "false").lower() in ("true", "1", "yes")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "your_gemini_api_key_here")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")

# Automation Settings
TYPING_DELAY_MS = int(os.getenv("TYPING_DELAY_MS", "5"))          # ms between each character typed
RUN_WAIT_SECONDS = int(os.getenv("RUN_WAIT_SECONDS", "8"))        # seconds to wait after clicking Run
NEXT_WAIT_SECONDS = int(os.getenv("NEXT_WAIT_SECONDS", "3"))      # seconds to wait after clicking Next
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "4"))                  # max retries if Run fails
