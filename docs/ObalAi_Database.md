# ObalAi — модель PostgreSQL

> Статус: целевая схема PostgreSQL для MVP реализована в SQLAlchemy-моделях и начальной Alembic-миграции в ветке `codex/postgres-models-migrations` (PR #3). Ревизия `0001_initial_marketplace` применена к локальной базе `obalai`; PR ещё не слит в `main`. PostgreSQL — единственная СУБД; SQLite запрещён.

## 1. Назначение и допущения

Схема поддерживает сценарий: продавец размещает партию со сроком годности, остатком и скидкой; покупатель находит и бронирует товар; продавец принимает и обрабатывает заказ.

Для MVP заложены следующие правила: один заказ относится к одному магазину; валюта — KZT; онлайн-оплата не считается реализованной до подключения настоящего платёжного провайдера. Статус «оплачено» нельзя выставлять имитацией.

Общие соглашения: UUID для ключей; TIMESTAMPTZ в UTC; NUMERIC(12,2) для денег и NUMERIC(12,3) для количества; физически не удалять записи с историей заказа; хранить пароль только в виде безопасного хэша.

## 2. Таблицы и поля

### users — учётные записи

Уже существует в коде: id UUID PK, email VARCHAR(320) UNIQUE, password_hash VARCHAR(255), role VARCHAR(20), created_at TIMESTAMPTZ. Допустимые роли: buyer, seller, admin — ограничить CHECK. Для email обеспечить уникальность без учёта регистра: нормализовать в API и добавить UNIQUE index по lower(email), чтобы защититься от обхода нормализации.

### stores — магазины

- id UUID PK
- owner_user_id UUID NOT NULL FK users(id)
- name VARCHAR(160) NOT NULL
- description TEXT NULL
- address TEXT NOT NULL
- city VARCHAR(120) NOT NULL
- is_active BOOLEAN NOT NULL DEFAULT TRUE
- created_at, updated_at TIMESTAMPTZ NOT NULL

Индексы: owner_user_id; (city, is_active). Предположение MVP — один магазин на владельца (UNIQUE owner_user_id). Если проект поддерживает несколько магазинов или команду владельцев, это ограничение надо изменить до миграции.

### categories — категории

- id UUID PK; name VARCHAR(120) NOT NULL; slug VARCHAR(140) NOT NULL UNIQUE
- parent_id UUID NULL FK categories(id) ON DELETE RESTRICT
- is_active BOOLEAN NOT NULL DEFAULT TRUE

Индекс parent_id. Категории с товарами физически не удалять.

### products — карточки каталога

- id UUID PK; category_id UUID NULL FK categories(id) ON DELETE RESTRICT
- name VARCHAR(180) NOT NULL; description TEXT NULL
- unit VARCHAR(20) NOT NULL: piece, kg или portion
- image_url TEXT NULL; is_active BOOLEAN NOT NULL DEFAULT TRUE
- created_at, updated_at TIMESTAMPTZ NOT NULL

Индексы: (category_id, is_active), name. Полнотекстовый поиск и pg_trgm можно добавить отдельной миграцией после выбора конкретного поиска; начальный поиск может использовать ILIKE.

### inventory_batches — партии и предложения

Каждая партия принадлежит конкретному магазину и товару.

- id UUID PK; store_id UUID NOT NULL FK stores(id) ON DELETE RESTRICT
- product_id UUID NOT NULL FK products(id) ON DELETE RESTRICT
- quantity_total NUMERIC(12,3) NOT NULL CHECK > 0
- quantity_available NUMERIC(12,3) NOT NULL CHECK >= 0 и <= quantity_total
- regular_price NUMERIC(12,2) NOT NULL CHECK >= 0
- discount_price NUMERIC(12,2) NOT NULL CHECK >= 0 и <= regular_price
- currency CHAR(3) NOT NULL DEFAULT KZT CHECK = KZT для MVP
- expires_at TIMESTAMPTZ NOT NULL
- status VARCHAR(20) NOT NULL: active, paused, sold_out, expired
- created_at, updated_at TIMESTAMPTZ NOT NULL

Индексы: (status, expires_at), (store_id, status), (product_id, status). Для каталога партия доступна только при status=active, срок ещё не истёк и quantity_available > 0. Процент скидки вычислять из regular_price и discount_price, отдельное поле не хранить.

### favorites — избранное

- user_id UUID NOT NULL FK users(id) ON DELETE CASCADE
- batch_id UUID NOT NULL FK inventory_batches(id) ON DELETE CASCADE
- created_at TIMESTAMPTZ NOT NULL
- PK/UNIQUE (user_id, batch_id)

Индекс (user_id, created_at DESC). Избранное не резервирует товар.

### orders — заказ и бронирование

- id UUID PK; buyer_user_id UUID NOT NULL FK users(id) ON DELETE RESTRICT
- store_id UUID NOT NULL FK stores(id) ON DELETE RESTRICT
- status VARCHAR(24) NOT NULL: reserved, accepted, rejected, ready, completed, cancelled, expired
- fulfillment_method VARCHAR(12) NOT NULL: pickup или delivery
- delivery_address TEXT NULL; обязательный при delivery
- total_amount NUMERIC(12,2) NOT NULL CHECK >= 0
- currency CHAR(3) NOT NULL DEFAULT KZT CHECK = KZT
- reservation_expires_at TIMESTAMPTZ NULL
- created_at, updated_at TIMESTAMPTZ NOT NULL

Ограничение: pickup допускает NULL delivery_address, delivery требует адрес. Индексы: (buyer_user_id, created_at DESC), (store_id, status, created_at), (status, reservation_expires_at). Статус reserved означает бронь, не оплату. До провайдера платёжная операция не создаётся и заказ не помечается оплаченным.

### order_items — позиции и снимок цены

- id UUID PK
- order_id UUID NOT NULL FK orders(id) ON DELETE RESTRICT
- batch_id UUID NOT NULL FK inventory_batches(id) ON DELETE RESTRICT
- quantity NUMERIC(12,3) NOT NULL CHECK > 0
- unit_price NUMERIC(12,2) NOT NULL CHECK >= 0 — цена в момент бронирования
- line_total NUMERIC(12,2) NOT NULL CHECK >= 0 — рассчитывается сервером
- created_at TIMESTAMPTZ NOT NULL

Индексы: order_id, batch_id. Цена в позиции не меняется при последующем изменении цены партии. Все партии заказа должны принадлежать orders.store_id; API проверяет это в транзакции. При необходимости БД-гарантии добавить составные UNIQUE/FK по (id, store_id).

## 3. Связи

- users 1 — 0..1 stores (MVP; см. допущение о нескольких магазинах).
- categories 1 — N products; категория может иметь родителя.
- stores 1 — N inventory_batches; products 1 — N inventory_batches.
- users N — M inventory_batches через favorites.
- users 1 — N orders; stores 1 — N orders.
- orders 1 — N order_items; каждая позиция ссылается на inventory_batches.

## 4. Атомарная бронь и остатки

В одной транзакции PostgreSQL выбрать партию FOR UPDATE, проверить статус, срок и остаток; создать заказ и позиции с зафиксированной ценой; уменьшить quantity_available; перевести партию в sold_out при нулевом остатке; зафиксировать транзакцию. При ошибке откатить всю операцию. При отмене, отклонении или истечении брони восстановить остаток ровно один раз и атомарно со сменой статуса.

Повторная отправка запроса не должна создавать второй заказ. До реализации бронирования определить API-механизм идемпотентности (например, уникальный idempotency key).

## 5. WSM для сравнения предложений

Для предложения i итог Sᵢ = Σ(wⱼ × rᵢⱼ), где веса wⱼ в сумме равны 1, а нормализованные оценки rᵢⱼ находятся от 0 до 1. Для критерия выгоды (скидка) r=(x−min)/(max−min); для критерия затрат (расстояние) r=(max−x)/(max−min). Срок годности нормализуется относительно явно заданного диапазона.

Пример: веса скидки 0.40, срока 0.35, близости 0.25.

| Предложение | Скидка | Срок | Близость | Расчёт | Итог |
|---|---:|---:|---:|---|---:|
| A | 0.80 | 0.60 | 0.90 | 0.40×0.80 + 0.35×0.60 + 0.25×0.90 | 0.745 |
| B | 0.60 | 0.90 | 0.70 | 0.40×0.60 + 0.35×0.90 + 0.25×0.70 | 0.720 |

По этим критериям A выше B. Если расстояние неизвестно, не подставлять выдуманное число: исключить критерий и перенормировать оставшиеся веса с явным указанием этого, либо вернуть insufficient_data. Хранить версию набора весов/нормализации для воспроизводимости.

## 6. Источники AI-аналитики и недостаток данных

Используемые источники должны быть фактическими записями: завершённые и отменённые заказы с позициями, реальные бронирования, история изменения цен партий, остатки во времени, срок годности и пользовательские события, если они действительно сохраняются. Анализ скидки продавцу учитывает эти факты, а не вымышленные продажи.

Если не хватает наблюдений, временного периода или признаков — вернуть статус insufficient_data и объяснить, каких данных недостаёт. Популярность или просмотры не называть персональной AI-рекомендацией без соответствующего расчёта и оценки качества. Не создавать синтетические записи для демонстрации AI.

## 7. Индексы и ограничения — сводка

- PK и FK на всех связях; UNIQUE для нормализованного email, slug категории и пары избранного.
- CHECK для ролей, статусов, единиц измерения, количества, цен, валюты и типа получения заказа.
- Основные запросы каталога обслуживают индексы по статусу и сроку партии, магазину, товару и категории.
- Заказы индексируются по покупателю, магазину/статусу и сроку окончания брони.
- Не индексировать каждое поле без подтверждённого запроса.

## 8. Текущий статус и следующий шаг

В миграции `0001_initial_marketplace` созданы восемь предметных таблиц: `users`, `stores`, `categories`, `products`, `inventory_batches`, `favorites`, `orders` и `order_items`. Таблица `alembic_version` хранит применённую ревизию. Схема уже развёрнута в локальной базе PostgreSQL `obalai`; результат подключения backend проверен через `/health`.

После ревью и слияния PR #3 следующий этап — API магазинов, каталога, партий и транзакционной брони. Правило «заказ относится к одному магазину» сейчас хранится в `orders.store_id`; сервис бронирования должен дополнительно проверять, что каждая партия в позициях заказа принадлежит этому магазину. Ограничение на уровне БД можно добавить отдельным решением.

Существующие API-маршруты покрывают проверку соединения и авторизацию. Создание магазина, публикация партии, поиск предложений, бронирование и обработка заказа пока не реализованы.
