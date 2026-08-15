# Deploying nex-route on PythonAnywhere

## What was actually wrong

Even with a correct WSGI file and correct static-files mapping, the site would
not start on PythonAnywhere because of the **repository itself**, not your PA
configuration. Fixed here:

1. **`requirements.txt` was UTF-16 encoded** (BOM `ÿþ`, NUL bytes between every
   character). `pip install -r requirements.txt` reads it as UTF-8 and dies
   with `UnicodeDecodeError` — so nothing installs, the virtualenv is empty,
   and PA's worker fails to import Django. Rewritten as clean UTF-8.

2. **`Django==6.0.7` does not exist.** The Django 6.0 series has no `.7`
   release, so pip aborts with *"No matching distribution found for
   Django==6.0.7"*. Same for a dozen other invented pins:
   `cryptography==50.0.0`, `cffi==2.1.1`, `rpds-py==2026.6.3`,
   `Twisted==26.4.0`, `packaging==26.3`, `autobahn==26.7.1`,
   `pyOpenSSL==26.4.0`, `PyJWT==2.13.0`, `attrs==26.1.0`, `tzdata==2026.3`,
   `jsonschema==4.26.0`, `PyYAML==6.0.3`, `zope.interface==8.5`,
   `service-identity==26.1.0`, `Automat==25.4.16`, `Incremental==24.11.0`,
   `msgpack==1.2.1`, `ujson==5.13.0`, `referencing==0.37.0`,
   `jsonschema-specifications==2025.9.1`, `cbor2==6.1.4`, `typing_extensions==4.16.0`,
   `daphne==4.2.3`, `channels==4.3.2`, `asgiref==3.12.1`.
   All rewritten to real, resolvable ranges targeting Django 5.2 LTS.

3. **`rest-framework-simplejwt==0.0.2`** (with hyphens) is a dead stub package
   on PyPI that collides with the real `djangorestframework-simplejwt`.
   Removed.

4. **Channels/Daphne WebSockets do not run on PythonAnywhere.** PA's web-app
   worker is WSGI-only — it cannot serve `ws://…/ws/orders/` or
   `ws://…/ws/admin/`. Under the old `core/wsgi.py` this only broke websockets,
   but under `core/asgi.py` (which some tutorials tell you to point PA at) it
   crashes the whole site. Deployment now uses `core/wsgi.py` and the plain
   Django WSGI application; ASGI is kept for local `daphne` runs.

5. **Missing `CSRF_TRUSTED_ORIGINS`.** With `DEBUG=False` on PA, the admin
   login form 403s over HTTPS unless PA's origin is trusted. Added, driven by
   `DJANGO_CSRF_TRUSTED_ORIGINS` env var, defaulting to
   `https://*.pythonanywhere.com`.

6. **`DEBUG` defaulted to `True`.** Flipped to `False` by default; enable
   locally by exporting `DJANGO_DEBUG=1`.

7. Added `MEDIA_URL` / `MEDIA_ROOT` so uploads don't 500.


## Deploying — step by step

Assume your PA username is `YOURUSERNAME` and the site is
`YOURUSERNAME.pythonanywhere.com`.

### 1. Upload / clone

Unzip `nex-route-fixed.zip` into `/home/YOURUSERNAME/nex-route`, **or** if you
push this fixed copy to GitHub:

```bash
cd ~
git clone https://github.com/YOURUSERNAME/nex-route.git
```

### 2. Create a virtualenv (Python 3.11 or 3.12)

```bash
mkvirtualenv --python=/usr/bin/python3.11 nex-route
pip install --upgrade pip
pip install -r ~/nex-route/requirements.txt
```

If `pip install` errors, that is now a real dependency problem — not the
UTF-16/fake-version issue that was blocking you before.

### 3. Migrate + collect static

```bash
cd ~/nex-route
python manage.py migrate
python manage.py collectstatic --noinput
```

### 4. Configure the PA web app

On the PA **Web** tab, create (or reconfigure) a **Manual configuration** web
app with the same Python version as your virtualenv.

- **Source code**: `/home/YOURUSERNAME/nex-route`
- **Working directory**: `/home/YOURUSERNAME/nex-route`
- **Virtualenv**: `/home/YOURUSERNAME/.virtualenvs/nex-route`
- **WSGI file**: copy the contents of `pythonanywhere_wsgi.py` from this repo
  into `/var/www/YOURUSERNAME_pythonanywhere_com_wsgi.py` and replace every
  `YOURUSERNAME` placeholder.
- **Static files**:
  - URL `/static/`  →  Directory `/home/YOURUSERNAME/nex-route/staticfiles`
  - URL `/media/`   →  Directory `/home/YOURUSERNAME/nex-route/media`
- **Environment variables** (Web tab → *Environment variables*):
  - `DJANGO_SECRET_KEY` = *a real random string*
  - `DJANGO_DEBUG` = `False`
  - `DJANGO_ALLOWED_HOSTS` = `YOURUSERNAME.pythonanywhere.com`
  - `DJANGO_CSRF_TRUSTED_ORIGINS` = `https://YOURUSERNAME.pythonanywhere.com`

Hit **Reload**.

### 5. About the WebSockets

`ws/orders/` and `ws/admin/` will **not** work on PythonAnywhere — the platform
does not proxy WebSockets to user code. The REST endpoints (`/api/…`,
`/users/…`, `/admin/`, `/swagger/`, `/redoc/`) all work fine over WSGI.

If you need the WebSocket layer in production, host it elsewhere (a small
Daphne process on Fly.io / Railway / Render / a VPS) and point the front end
at that host for `ws://` traffic while keeping the REST API on PA. Locally you
can still run everything with `daphne core.asgi:application`.

### 6. If the site still 500s

Read `/var/log/YOURUSERNAME.pythonanywhere.com.error.log` — with the fixes
above, any remaining error will be an application-level exception (missing
migration, missing env var, etc.), not an import/dependency failure.
