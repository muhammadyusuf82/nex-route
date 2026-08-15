"""
WSGI config for the core project.

PythonAnywhere serves the site over WSGI (it does not support ASGI /
WebSockets on the standard web-app workers), so this module exposes a
plain Django WSGI ``application`` — which is what PA's own
``/var/www/<user>_pythonanywhere_com_wsgi.py`` should import.

The Channels / Daphne setup is still available for local development via
``core/asgi.py`` (run with ``daphne core.asgi:application``).
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")

application = get_wsgi_application()
