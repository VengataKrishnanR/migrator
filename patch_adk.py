"""
Patch google-adk so JSX/TypeScript curly braces in agent prompts
don't throw KeyError. Run once after `pip install -r requirements.txt`.
Safe to run multiple times.
"""
import sys
from pathlib import Path

venv_root = Path(sys.executable).parent.parent
target = venv_root / "Lib" / "site-packages" / "google" / "adk" / "utils" / "instructions_utils.py"

if not target.exists():
    print(f"ERROR: {target} not found — is the venv activated?")
    sys.exit(1)

text = target.read_text(encoding="utf-8")

OLD = "raise KeyError(f'Context variable not found: `{var_name}`.')"
NEW = "return match.group(0)  # pass through unresolvable vars (e.g. JSX {expr})"

if OLD not in text:
    if NEW in text:
        print("Already patched — nothing to do.")
    else:
        print(f"WARN: target line not found in {target.name} — ADK version may differ.")
        print("      Check the file manually and replace the raise KeyError line.")
    sys.exit(0)

target.write_text(text.replace(OLD, NEW), encoding="utf-8")
print(f"Patched: {target}")
print("ADK will now silently pass through unresolvable template variables.")
