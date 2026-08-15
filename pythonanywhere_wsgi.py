"""
Sample WSGI file for PythonAnywhere.

Copy the contents into /var/www/<yourusername>_pythonanywhere_com_wsgi.py
(replace <yourusername> with your PA username, and adjust the project
path if you cloned somewhere other than /home/<yourusername>/nex-route).

Everything below is what PA's WSGI worker actually needs — nothing more.
"""

import os
import sys

# 1. Absolute path to the project root (where manage.py lives).
project_home = "/home/YOURUSERNAME/nex-route"
if project_home not in sys.path:
    sys.path.insert(0, project_home)

# 2. Tell Django which settings module to use.
os.environ["DJANGO_SETTINGS_MODULE"] = "core.settings"

# 3. Optional but recommended on PA:
os.environ.setdefault("DJANGO_DEBUG", "False")
os.environ.setdefault(
    "DJANGO_ALLOWED_HOSTS",
    "YOURUSERNAME.pythonanywhere.com",
)
os.environ.setdefault(
    "DJANGO_CSRF_TRUSTED_ORIGINS",
    "https://YOURUSERNAME.pythonanywhere.com",
)
# Set a real secret in the PA "Web" tab -> "Environment variables" instead of
# hard-coding it here.
# os.environ.setdefault("DJANGO_SECRET_KEY", "put-a-real-random-secret-here")

# 4. Hand off to Django's WSGI application.
from core.wsgi import application  # noqa: E402,F401
