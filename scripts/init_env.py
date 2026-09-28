"""Creates .env from .env.example and fills in a fresh TOKEN_ENCRYPTION_KEYS if it is blank.

Stdlib only (runs before dependencies are installed). A Fernet key is 32 random bytes,
url-safe base64 encoded. Existing values are never overwritten.
"""
import base64
import os
import re
import shutil
from pathlib import Path

env = Path(".env")
if not env.exists():
    shutil.copy(".env.example", env)

text = env.read_text()
if not re.search(r"^TOKEN_ENCRYPTION_KEYS=\S", text, re.M):
    line = "TOKEN_ENCRYPTION_KEYS=" + base64.urlsafe_b64encode(os.urandom(32)).decode()
    if re.search(r"^TOKEN_ENCRYPTION_KEYS=", text, re.M):
        text = re.sub(r"^TOKEN_ENCRYPTION_KEYS=.*$", line, text, flags=re.M)
    else:
        text = text.rstrip("\n") + "\n" + line + "\n"
    env.write_text(text)
    print("Generated TOKEN_ENCRYPTION_KEYS in .env")
