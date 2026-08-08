# NexRoute API

Backend для сервиса доставки: фирмы создают заказы на свои товары, курьеры принимают их и обновляют статус в реальном времени, админы наблюдают за всей активностью через WebSocket-дашборд.

**Стек:** Django 5 · Django REST Framework · SimpleJWT · Channels 4 + Daphne (ASGI) · drf-spectacular · SQLite (по умолчанию).

---

## Содержание

- [Быстрый старт](#быстрый-старт)
- [Модель ролей](#модель-ролей)
- [Аутентификация](#аутентификация)
- [HTTP endpoints](#http-endpoints)
  - [Auth / Регистрация](#auth--регистрация)
  - [Users (`/users/accounts/`)](#users-usersaccounts)
  - [Couriers (`/users/couriers/`)](#couriers-userscouriers)
  - [Items (`/api/items/`)](#items-apiitems)
  - [Todos (`/api/todos/`)](#todos-apitodos)
  - [Служебные](#служебные)
- [WebSocket API](#websocket-api)
  - [`ws/orders/` — жизненный цикл заказа](#wsorders--жизненный-цикл-заказа)
  - [`ws/admin/` — админский мониторинг](#wsadmin--админский-мониторинг)
- [Машина состояний заказа](#машина-состояний-заказа)
- [Известные проблемы (audit)](#известные-проблемы-audit)

---

## Быстрый старт

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# ВАЖНО: миграция для модели Todo в архиве отсутствует — создайте её:
python manage.py makemigrations order
python manage.py migrate

python manage.py createsuperuser  # роль поставьте вручную через админку → ADMIN

# ASGI-запуск (нужен для WebSocket):
daphne -b 0.0.0.0 -p 8000 core.asgi:application
# или для разработки:
python manage.py runserver 0.0.0.0:8000
```

Переменные окружения:

| Имя | По умолчанию | Назначение |
|---|---|---|
| `DJANGO_SECRET_KEY` | insecure fallback | секрет для подписи |
| `DJANGO_DEBUG` | `True` | `False` для прода |

---

## Модель ролей

Три роли (`users.User.Role`):

- **ADMIN** — полный доступ ко всем ресурсам, монитор в реальном времени.
- **FIRM** — создаёт `Item` и `Order`, назначает `Todo` курьерам. Требует `is_verified=True` для большинства операций (верификация выставляется админом).
- **COURIER** — принимает заказы, обновляет статус доставки, обновляет статус своих Todo. Требует `is_verified=True`.

Флаг `is_verified` устанавливается только админом.

---

## Аутентификация

- **HTTP:** JWT (SimpleJWT) в заголовке `Authorization: Bearer <access>`.
- **WebSocket:** access-токен в query-string: `ws://host/ws/orders/?token=<access>`.
- Access TTL — 2 часа, Refresh TTL — 7 дней, ротация refresh включена, старые токены попадают в blacklist.

Payload access-токена содержит: `role`, `is_verified`, `username`, `user_id`.

---

## HTTP endpoints

Базовые префиксы: `users/…` (auth и профили) и `api/…` (бизнес-объекты).

Все ответы — JSON. Все ошибки валидации / прав — стандартный формат DRF (`{"detail": "..."}` либо словарь по полям).

### Auth / Регистрация

#### `POST /users/token/`
Получить пару JWT-токенов.

- **Auth:** не требуется
- **Body:**
  ```json
  { "username": "acme", "password": "***" }
  ```
- **200:**
  ```json
  {
    "access": "<jwt>",
    "refresh": "<jwt>",
    "user": { "id": 1, "username": "acme", "email": "", "role": "FIRM", "is_verified": false }
  }
  ```

#### `POST /users/token/refresh/`
Обменять refresh на новую пару.

- **Body:** `{ "refresh": "<jwt>" }`
- **200:** `{ "access": "<jwt>", "refresh": "<jwt>" }` (refresh ротируется)

#### `POST /users/register/firm/`
Регистрация фирмы. Создаёт `User(role=FIRM, is_verified=False)` + `FirmProfile`.

- **Auth:** не требуется
- **Body:**
  ```json
  {
    "username": "acme",
    "email": "hello@acme.io",
    "phone_number": "+998900000001",
    "password": "StrongPass123!",
    "company_name": "Acme LLC",
    "firm_type": "FACTORY",   // FACTORY | MARKET
    "tax_id": "TIN-000-001",
    "address": "Tashkent, ..."
  }
  ```
- **201:** объект созданного пользователя (без пароля). Верификацию проставляет админ.

#### `POST /users/register/courier/`
Регистрация курьера. Создаёт `User(role=COURIER, is_verified=False)` + `CourierProfile`.

- **Auth:** не требуется
- **Body:**
  ```json
  {
    "username": "kolya",
    "email": "k@ex.com",
    "phone_number": "+998900000002",
    "password": "StrongPass123!",
    "vehicle_type": "motorbike",
    "license_plate": "01A123BB"
  }
  ```
- **201:** объект пользователя.

---

### Users (`/users/accounts/`)

CRUD пользователей. Админ — полный доступ, обычный пользователь — только свой аккаунт (list/retrieve/update/delete по своему `pk`; create запрещён не-админам).

| Метод | URL | Что делает |
|---|---|---|
| `GET` | `/users/accounts/` | список (админ — все, иначе только сам себя) |
| `POST` | `/users/accounts/` | создать (только админ) |
| `GET` | `/users/accounts/{id}/` | получить |
| `PUT` / `PATCH` | `/users/accounts/{id}/` | обновить (не-админ не может менять `role`, `is_verified`, `is_active`) |
| `DELETE` | `/users/accounts/{id}/` | удалить |

**Тело (create/update):**
```json
{
  "username": "acme",
  "email": "hello@acme.io",
  "phone_number": "+998900000001",
  "role": "FIRM",           // только админ
  "is_verified": true,      // только админ
  "is_active": true,        // только админ
  "password": "..."         // write-only, опционально при update
}
```

**Ответ (retrieve):** те же поля + `id`, `date_joined`, вложенные `firm_profile` и/или `courier_profile` (read-only).

---

### Couriers (`/users/couriers/`)

Управление профилями курьеров.

- **Read (GET list/retrieve):** доступен всем аутентифицированным. Админ видит всех; верифицированная фирма — только активных верифицированных курьеров; курьер — только себя.
- **Write (POST/PUT/PATCH/DELETE):** только `ADMIN`.

| Метод | URL | Что делает |
|---|---|---|
| `GET` | `/users/couriers/` | список |
| `POST` | `/users/couriers/` | админ создаёт пользователя-курьера + профиль |
| `GET` | `/users/couriers/{id}/` | получить |
| `PUT` / `PATCH` | `/users/couriers/{id}/` | обновить |
| `DELETE` | `/users/couriers/{id}/` | удалить |

**Тело create (админ):**
```json
{
  "username": "kolya",
  "email": "k@ex.com",
  "phone_number": "+998900000002",
  "password": "StrongPass123!",
  "is_verified": true,
  "vehicle_type": "car",
  "license_plate": "01A123BB",
  "current_status": "OFFLINE"    // AVAILABLE | ON_DELIVERY | OFFLINE
}
```

**Ответ (retrieve):**
```json
{
  "id": 5,
  "user_id": 42,
  "username": "kolya",
  "email": "k@ex.com",
  "phone_number": "+998900000002",
  "is_verified": true,
  "vehicle_type": "car",
  "license_plate": "01A123BB",
  "current_status": "AVAILABLE"
}
```

---

### Items (`/api/items/`)

Товары, готовые к доставке. Владелец — фирма.

- **Create:** админ или верифицированная фирма. Админ может передать `owner: <firm_user_id>`; фирма всегда владелец = она сама.
- **List/Retrieve:** админ видит все; верифицированная фирма — только свои; курьер — пустой список (получает данные о позиции только через сокет при `order_accepted`).
- **Update/Delete:** админ или владелец-фирма.

| Метод | URL | |
|---|---|---|
| `GET` | `/api/items/` | список |
| `POST` | `/api/items/` | создать |
| `GET` | `/api/items/{id}/` | получить |
| `PUT` / `PATCH` | `/api/items/{id}/` | обновить |
| `DELETE` | `/api/items/{id}/` | удалить |

**Тело create/update:**
```json
{
  "name": "Coffee beans 5kg",
  "position": "41.311081,69.240562",   // адрес или lat,lng, до 512 символов
  "owner": 3                            // опционально, только админ
}
```

**Ответ:**
```json
{
  "id": 1,
  "name": "Coffee beans 5kg",
  "position": "41.311081,69.240562",
  "owner": 3,
  "owner_username": "acme",
  "created_at": "2026-08-05T10:00:00Z",
  "updated_at": "2026-08-05T10:00:00Z"
}
```

> ℹ️ **Заказы (`Order`) создаются НЕ через HTTP, а через WebSocket `ws/orders/`** — см. ниже.

---

### Todos (`/api/todos/`)

Плановые задачи курьеру: адрес, время, описание.

- **Create:** админ или верифицированная фирма. `assigned_by` автоматически = текущий пользователь.
- **List/Retrieve:** админ — все; фирма — только назначенные ею; курьер — назначенные ему.
- **Update/Delete:** админ и назначивший (фирма). Курьер может только менять `status` в `IN_PROGRESS` или `COMPLETED` — используется отдельный `TodoCourierStatusSerializer`.

| Метод | URL | |
|---|---|---|
| `GET` | `/api/todos/` | список |
| `POST` | `/api/todos/` | создать |
| `GET` | `/api/todos/{id}/` | получить |
| `PUT` / `PATCH` | `/api/todos/{id}/` | обновить |
| `DELETE` | `/api/todos/{id}/` | удалить (кроме курьера) |

**Тело create (admin/firm):**
```json
{
  "title": "Pickup at warehouse #3",
  "description": "Take 5 boxes",
  "courier": 5,
  "scheduled_at": "2026-08-06T09:00:00Z",
  "region": "Tashkent Region",
  "city": "Tashkent",
  "street": "Amir Temur 1",
  "longitude": "69.240562",
  "latitude": "41.311081",
  "status": "PENDING"                       // PENDING | IN_PROGRESS | COMPLETED | CANCELLED
}
```

Валидация: `-180 ≤ longitude ≤ 180`, `-90 ≤ latitude ≤ 90`, курьер должен быть `is_active` и `is_verified`.

**Тело update (courier):**
```json
{ "status": "IN_PROGRESS" }   // только IN_PROGRESS или COMPLETED
```
Нельзя изменять уже `COMPLETED` / `CANCELLED` todo.

**Ответ (retrieve):**
```json
{
  "id": 10,
  "title": "Pickup at warehouse #3",
  "description": "Take 5 boxes",
  "assigned_by": 3, "assigned_by_username": "acme",
  "courier": 5,     "courier_username": "kolya",
  "scheduled_at": "2026-08-06T09:00:00Z",
  "region": "...", "city": "...", "street": "...",
  "longitude": "69.240562", "latitude": "41.311081",
  "address": { "region": "...", "city": "...", "street": "...",
               "longitude": "69.240562", "latitude": "41.311081" },
  "status": "PENDING",
  "created_at": "...", "updated_at": "..."
}
```

---

### Служебные

| URL | Что |
|---|---|
| `GET /api/schema/` | OpenAPI 3 (YAML) |
| `GET /swagger/` | Swagger UI |
| `GET /redoc/` | ReDoc |
| `/admin/` | Django admin |

---

## WebSocket API

Оба соединения обязательно требуют JWT в query-string:

```
ws://<host>/ws/orders/?token=<access>
ws://<host>/ws/admin/?token=<access>
```

Коды закрытия при отказе аутентификации: `4401` — токен отсутствует/невалиден, `4403` — недостаточно прав или пользователь не верифицирован.

Формат всех сообщений — JSON. Клиент отправляет объекты с полем `action`; сервер отвечает объектами с полем `type`.

Формат ошибки от сервера:
```json
{ "type": "error", "code": "invalid_action|forbidden|not_found|server_error", "detail": "..." }
```

### `ws/orders/` — жизненный цикл заказа

Доступ: `ADMIN`, `FIRM`, `COURIER` (не-админы должны быть `is_verified`).

При подключении клиент попадает в группы:
- `user_<id>` — всегда;
- `couriers` — если роль COURIER;
- `admins` — если роль ADMIN (и получает те же события, что `ws/admin/`).

#### Клиент → Сервер

**1. Создать заказ** (только `FIRM` или `ADMIN`; фирма может создавать заказ только на свой `Item`):
```json
{
  "action": "create_order",
  "item_id": 1,
  "target_position": "Chilanzar 42, Tashkent"   // до 512 символов
}
```
Заказ создаётся со статусом `PENDING` и рассылается всем курьерам как оффер.

**2. Принять заказ** (только `COURIER`; first-wins, атомарно `SELECT … FOR UPDATE`):
```json
{ "action": "accept_order", "order_id": 12 }
```
Курьер переходит в `ON_DELIVERY`, заказ — в `ACCEPTED`.

**3. Обновить статус доставки** (только `COURIER`, только по своему заказу):
```json
{
  "action": "update_status",
  "order_id": 12,
  "status": "IN_TRANSIT",           // см. переходы ниже
  "status_description": "Left the warehouse",   // ≤ 2000
  "position": "41.31,69.24"                     // опционально, ≤ 512, не сохраняется в БД, только рассылается
}
```
При терминальном статусе (`DELIVERED`/`FAILED`/`CANCELLED`) курьер автоматически возвращается в `AVAILABLE`.

#### Сервер → Клиент

Тип сообщения — в поле `type`. Основные:

| `type` | Кому | Когда | Полезная нагрузка |
|---|---|---|---|
| `order_created` | автору заказа | после `create_order` | `{ order: <Order> }` |
| `order_offered` | всем курьерам (`couriers`) | новый заказ доступен | `{ order: <Order> }` |
| `order_accepted` | курьеру, принявшему заказ | после `accept_order` | `{ order: <Order>, directions: { pickup, destination } }` |
| `order_taken` | остальным курьерам | другой курьер уже взял заказ | `{ order_id, }` |
| `status_updated` | самому курьеру | подтверждение изменения статуса | `{ order: <Order> }` |
| `order_accepted` / `status_updated` | автору заказа | по группе `user_<created_by_id>` | `{ order, courier_position? }` |
| `order_created` / `order_accepted` / `status_updated` | всем админам (`admins`) | любое событие | `{ order, courier_position? }` |
| `error` | клиенту, вызвавшему ошибку | валидация / права / not_found | `{ code, detail }` |

`<Order>` — сериализованный объект (см. `OrderSerializer`):
```json
{
  "id": 12,
  "courier": 5, "courier_username": "kolya",
  "item": 1, "item_name": "Coffee beans 5kg", "item_position": "...",
  "target_position": "Chilanzar 42, Tashkent",
  "status": "ACCEPTED",
  "status_description": "Order accepted by courier.",
  "created_by": 3,
  "directions": { "pickup": "...", "destination": "..." },
  "created_at": "...", "updated_at": "..."
}
```

### `ws/admin/` — админский мониторинг

Доступ: только `ADMIN` (флаг `is_verified` не проверяется).

При подключении сервер шлёт снапшот всех незавершённых заказов:
```json
{ "type": "snapshot", "orders": [ <Order>, ... ] }
```

Клиент может запросить свежий снапшот в любой момент:
```json
{ "action": "snapshot" }
```

Далее в реальном времени приходят события такого же формата, что и в `ws/orders/` для группы `admins`:
- `order_created`
- `order_accepted`
- `status_updated`

Каждое несёт `{ order: <Order>, courier_position?: string }`.

---

## Машина состояний заказа

```
PENDING ──accept──▶ ACCEPTED ──▶ PICKED_UP ──▶ IN_TRANSIT ──▶ DELIVERED
   │                    │              │              │
   │                    ▼              ▼              ▼
   └──▶ CANCELLED    FAILED         FAILED         FAILED
                     CANCELLED
```

Проверяется на уровне модели (`Order.ALLOWED_TRANSITIONS`). Попытка невалидного перехода отвечает `ValidationError`.

Терминальные статусы: `DELIVERED`, `FAILED`, `CANCELLED` — исключены из админ-снапшота.

---

## Известные проблемы (audit)

Перед деплоем на прод обязательно исправить:

1. **Нет миграции для `Todo`** — сгенерировать (`makemigrations order`), иначе `/api/todos/*` упадёт.
2. **`SECRET_KEY` захардкожен в `settings.py`** как fallback, `db.sqlite3` в архиве — удалить из git, ключ хранить только в env.
3. **`ALLOWED_HOSTS = []`** — при `DEBUG=False` сервер откажется отвечать. Вынести в env.
4. **`CORS_ALLOW_ALL_ORIGINS = True`** — сузить до whitelist доменов фронтенда.
5. **`InMemoryChannelLayer`** — работает только внутри одного процесса Daphne. Для нескольких воркеров/масштабирования подключить `channels_redis`.
6. **JWT в query-string WebSocket** попадает в логи reverse-proxy. Либо отключить логирование query, либо перейти на sub-protocol/cookie.
7. **`drf-spectacular` падает на `TodoViewSet`** из-за обращения к `self.request.user.role` без `getattr` (при генерации схемы `user=AnonymousUser`). Fix: `if getattr(user, "role", None) == User.Role.COURIER` в `TodoViewSet.get_serializer_class()`.
8. **`Order.clean()`** не вызывается автоматически на `Order.objects.create` в WS-консьюмере — правило «PENDING без курьера» не срабатывает. Добавить `full_clean()` или переписать через сериализатор.
9. **Нет throttling** на `/users/token/` и `/users/register/*/` — уязвимо к brute-force. Подключить `DEFAULT_THROTTLE_CLASSES`.
10. **Нет тестов** — `tests.py` пустые.
11. **`position` в WS `update_status` не сохраняется** — только рассылается по каналам. Если нужен трек — сделать модель `OrderTrack`.
12. **Нет audit-лога переходов статусов заказа**.

Хорошее уже сделано: атомарный `select_for_update` при принятии заказа (first-wins), гранулярные permissions по ролям, ротация refresh-токенов с blacklist, разделение HTTP/ASGI, отдельный JWT-middleware для WebSocket.
