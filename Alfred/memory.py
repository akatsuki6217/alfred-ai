
import json
import os
import re

MEMORY_FILE = os.path.join(os.path.dirname(__file__), 'memory.json')

def load_memory():
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {"name": None, "facts": []}

def save_memory(memory):
    with open(MEMORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(memory, f, indent=2, ensure_ascii=False)

# Words that are NOT names (so "i am tired" doesn't store "tired")
NOT_NAMES = {'a','an','the','here','tired','happy','sad','sorry','good','fine',
             'back','done','not','so','very','just','really','going','looking',
             'trying','working','hungry','bored','confused','ready','new','testing'}

NAME_PATTERNS = [
    r"my name is\s+([A-Za-z]{2,20})",
    r"call me\s+([A-Za-z]{2,20})",
    r"i am\s+([A-Za-z]{2,20})\b",
    r"i'm\s+([A-Za-z]{2,20})\b",
]

def remember_from_message(message):
    """Detect 'my name is X' statements and store them."""
    memory = load_memory()
    changed = False
    for pattern in NAME_PATTERNS:
        m = re.search(pattern, message, re.IGNORECASE)
        if m:
            name = m.group(1).strip().capitalize()
            if name.lower() not in NOT_NAMES and memory.get('name') != name:
                memory['name'] = name
                changed = True
    if changed:
        save_memory(memory)
    return memory

def build_memory_prompt():
    """System-prompt fragment with everything Alfred knows about the user."""
    memory = load_memory()
    lines = []
    if memory.get('name'):
        lines.append(f"The user's name is {memory['name']}. Address them as 'Master {memory['name']}' or 'sir' — naturally, not in every sentence.")
    else:
        lines.append("You do not know the user's name yet. If it comes up naturally, politely ask for it once (e.g. 'Might I know your name, sir?').")
    for fact in memory.get('facts', []):
        lines.append(f"- {fact}")
    return "\n\nThings you remember about the user:\n" + "\n".join(lines)