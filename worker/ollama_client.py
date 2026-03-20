"""
worker/ollama_client.py

Handles all communication with Ollama — the locally running AI model.

Ollama is a tool that lets you run large language models (like Llama3)
on your own computer without sending any data to the internet.

This file sends the incoming comment or email text to Ollama,
along with a set of instructions (called a 'system prompt') that tells
the AI who it is and how to respond. Ollama returns a generated reply.

Before using this, make sure Ollama is running:
  ollama serve
  ollama pull llama3
"""

import os
import logging
import requests
from pathlib import Path

log = logging.getLogger(__name__)

# Where Ollama is running on your machine (default port is 11434)
OLLAMA_URL   = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3")

# Folder containing the instruction files for each platform
PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


def generate_reply(platform: str, content: str) -> str | None:
    """
    Sends a comment or email to Ollama and gets a generated reply back.

    How it works:
      1. Loads the instruction file for the platform (e.g. prompts/instagram.txt)
      2. Sends those instructions + the incoming content to Ollama
      3. Returns whatever Ollama writes back as the reply

    The 'system prompt' (instructions file) tells Ollama things like:
      - Who you are (thenullrabbit, a developer)
      - How to write replies (short, friendly, on-brand)
      - What NOT to do (no corporate speak, no more than 3 sentences)

    Returns None if Ollama is unreachable or something goes wrong —
    the worker will use a fallback reply in that case.
    """
    system_prompt = _load_prompt(platform)
    if not system_prompt:
        log.error(f"❌ No instruction file found for platform: {platform}")
        return None

    try:
        response = requests.post(
            f"{OLLAMA_URL}/api/chat",
            json={
                "model":  OLLAMA_MODEL,
                "stream": False,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": content}
                ],
                "options": {
                    "temperature": 0.7,   # 0 = very predictable, 1 = more creative
                    "num_predict": 200,   # maximum words in the reply
                }
            },
            timeout=60  # Llama3 can take up to a minute on slower machines
        )

        response.raise_for_status()
        data  = response.json()
        reply = data.get("message", {}).get("content", "").strip()

        if not reply:
            log.error("❌ Ollama returned an empty reply")
            return None

        return reply

    except requests.exceptions.ConnectionError:
        log.error("❌ Cannot connect to Ollama — is it running?")
        log.error("   Start it with: ollama serve")
        return None
    except requests.exceptions.Timeout:
        log.error("❌ Ollama took too long to respond — the model may still be loading")
        return None
    except Exception as e:
        log.error(f"❌ Ollama error: {e}")
        return None


def check_ollama_health() -> bool:
    """
    Checks whether Ollama is running and the correct model is available.

    Called once when the worker starts. If Ollama is not running,
    the worker will still start but will use fallback replies until
    Ollama comes online.

    Returns True if everything is ready, False otherwise.
    """
    try:
        response = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        models   = [m["name"] for m in response.json().get("models", [])]

        if not any(OLLAMA_MODEL in m for m in models):
            log.warning(f"⚠️  Model '{OLLAMA_MODEL}' not found locally")
            log.warning(f"   Download it with: ollama pull {OLLAMA_MODEL}")
            return False

        log.info(f"✅ Ollama is running with model: {OLLAMA_MODEL}")
        return True

    except Exception:
        log.error("❌ Ollama is not running")
        log.error("   Start it with: ollama serve")
        return False


def _load_prompt(platform: str) -> str | None:
    """
    Reads the instruction file for a given platform from the prompts folder.

    Each platform has its own .txt file that tells the AI how to behave:
      prompts/instagram.txt — instructions for replying to Instagram comments
      prompts/email.txt     — instructions for replying to emails

    You can edit these files at any time to change how the AI responds.
    No code changes needed — just edit the text file and restart the worker.
    """
    prompt_file = PROMPTS_DIR / f"{platform}.txt"

    if not prompt_file.exists():
        log.error(f"❌ Instruction file not found: {prompt_file}")
        return None

    return prompt_file.read_text().strip()
