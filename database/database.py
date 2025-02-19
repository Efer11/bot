import asyncpg
import os
import logging
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Получение данных для подключения к БД
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")

async def connect_db():
    """Подключение к базе данных"""
    try:
        return await asyncpg.connect(
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            host=DB_HOST,
            port=DB_PORT
        )
    except Exception as e:
        logger.error(f"Ошибка подключения к БД: {e}")
        raise

async def create_tables():
    """Создание таблиц printers и reviews"""
    conn = await connect_db()
    try:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS printers (
                id SERIAL PRIMARY KEY,
                telegram_id BIGINT UNIQUE NOT NULL,
                chat_id BIGINT NOT NULL,
                full_name TEXT NOT NULL,
                username TEXT,
                registered_at TIMESTAMP DEFAULT NOW(),
                room_number TEXT NOT NULL,
                price_per_page NUMERIC(5,3) CHECK (price_per_page >= 0) NOT NULL,
                total_earnings NUMERIC(10,3) DEFAULT 0 CHECK (total_earnings >= 0),
                is_active BOOLEAN DEFAULT TRUE,
                description TEXT DEFAULT '',
                card_number TEXT DEFAULT '',
                printer_type TEXT DEFAULT ''
            );
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS reviews (
                id SERIAL PRIMARY KEY,
                printer_id BIGINT NOT NULL REFERENCES printers(telegram_id) ON DELETE CASCADE,
                user_id BIGINT NOT NULL,
                rating INT CHECK (rating BETWEEN 1 AND 5) NOT NULL,
                comment TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            );
        """)
    except Exception as e:
        logger.error(f"Ошибка при создании таблиц: {e}")
    finally:
        await conn.close()

async def register_printer(
    telegram_id: int, chat_id: int, full_name: str, username: str,
    room_number: str, price_per_page: float, description: str = "", card_number: str = ""
):
    """Регистрация нового принтера или обновление данных существующего"""
    if price_per_page < 0:
        raise ValueError("Цена за страницу не может быть отрицательной")

    conn = await connect_db()
    try:
        existing = await conn.fetchval("SELECT telegram_id FROM printers WHERE telegram_id = $1;", telegram_id)

        if existing:
            await conn.execute("""
                UPDATE printers 
                SET full_name = $2, username = $3, room_number = $4, 
                    price_per_page = $5, description = $6, card_number = $7
                WHERE telegram_id = $1;
            """, telegram_id, full_name, username, room_number, price_per_page, description, card_number)
        else:
            await conn.execute("""
                INSERT INTO printers (telegram_id, chat_id, full_name, username, room_number, price_per_page, is_active, description, card_number)
                VALUES ($1, $2, $3, $4, $5, $6, TRUE, $7, $8);
            """, telegram_id, chat_id, full_name, username, room_number, price_per_page, description, card_number)
    except Exception as e:
        logger.error(f"Ошибка при регистрации принтера: {e}")
    finally:
        await conn.close()


async def update_total_earnings(telegram_id: int, amount: float):
    """Обновление общего заработка"""
    if amount < 0:
        raise ValueError("Сумма заработка не может быть отрицательной")

    conn = await connect_db()
    try:
        await conn.execute("""
            UPDATE printers
            SET total_earnings = total_earnings + $1
            WHERE telegram_id = $2;
        """, amount, telegram_id)
    except Exception as e:
        logger.error(f"Ошибка при обновлении заработка: {e}")
    finally:
        await conn.close()

async def get_all_printers():
    """Получение всех активных принтеров"""
    conn = await connect_db()
    try:
        return await conn.fetch("""
            SELECT chat_id, full_name, room_number, price_per_page, printer_type 
            FROM printers 
            WHERE is_active = TRUE;
        """)  # Добавлен printer_type
    except Exception as e:
        logger.error(f"Ошибка при получении списка принтеров: {e}")
        return []
    finally:
        await conn.close()

async def get_printer_room(printer_id: int):
    """Получение номера комнаты принтера"""
    conn = await connect_db()
    try:
        return await conn.fetchval("SELECT room_number FROM printers WHERE chat_id = $1;", printer_id)
    except Exception as e:
        logger.error(f"Ошибка при получении номера комнаты: {e}")
        return None
    finally:
        await conn.close()

async def toggle_printer_status(printer_id: int):
    """Переключение статуса активности принтера"""
    conn = await connect_db()
    try:
        current_status = await conn.fetchval("SELECT is_active FROM printers WHERE chat_id = $1;", printer_id)
        new_status = not current_status
        await conn.execute("UPDATE printers SET is_active = $1 WHERE chat_id = $2;", new_status, printer_id)
        return new_status
    except Exception as e:
        logger.error(f"Ошибка при изменении статуса принтера: {e}")
        return None
    finally:
        await conn.close()

async def get_printer_status(printer_id: int):
    """Получение статуса активности принтера"""
    conn = await connect_db()
    try:
        return await conn.fetchval("SELECT is_active FROM printers WHERE chat_id = $1;", printer_id)
    except Exception as e:
        logger.error(f"Ошибка при получении статуса принтера: {e}")
        return None
    finally:
        await conn.close()

async def get_printer_info(telegram_id: int):
    """Получение информации о принтере"""
    conn = await connect_db()
    try:
        return await conn.fetchrow("""
            SELECT chat_id, full_name, room_number, price_per_page, description, printer_type, card_number
            FROM printers WHERE telegram_id = $1;
        """, telegram_id)
    except Exception as e:
        logger.error(f"Ошибка при получении информации о принтере: {e}")
        return None
    finally:
        await conn.close()

async def update_printer_info(telegram_id: int, room_number: str = None, price_per_page: float = None):
    """Обновление информации о принтере"""
    conn = await connect_db()
    try:
        fields = []
        values = []

        if room_number:
            fields.append("room_number = $" + str(len(values) + 1))
            values.append(room_number)

        if price_per_page is not None:
            fields.append("price_per_page = $" + str(len(values) + 1))
            values.append(price_per_page)

        if fields:
            query = "UPDATE printers SET " + ", ".join(fields) + " WHERE telegram_id = $" + str(len(values) + 1)
            values.append(telegram_id)
            await conn.execute(query, *values)
    except Exception as e:
        logger.error(f"Ошибка при обновлении данных принтера: {e}")
    finally:
        await conn.close()

async def update_printer_description(telegram_id: int, description: str):
    """Обновление описания принтера"""
    conn = await connect_db()
    try:
        await conn.execute("UPDATE printers SET description = $1 WHERE telegram_id = $2;", description, telegram_id)
    except Exception as e:
        logger.error(f"Ошибка при обновлении описания: {e}")
    finally:
        await conn.close()

async def update_printer_type(telegram_id: int, printer_type: str):
    """Обновление типа принтера"""
    conn = await connect_db()
    try:
        await conn.execute("UPDATE printers SET printer_type = $1 WHERE telegram_id = $2;", printer_type, telegram_id)
    except Exception as e:
        logger.error(f"Ошибка при обновлении типа принтера: {e}")
    finally:
        await conn.close()

async def add_review(printer_id: int, user_id: int, rating: int, comment: str):
    """Добавление отзыва в базу данных"""
    conn = await connect_db()
    try:
        await conn.execute("""
            INSERT INTO reviews (printer_id, user_id, rating, comment)
            VALUES ($1, $2, $3, $4);
        """, printer_id, user_id, rating, comment)
    except Exception as e:
        logger.error(f"Ошибка при добавлении отзыва: {e}")
    finally:
        await conn.close()

async def get_average_rating(printer_id: int):
    """Получение среднего рейтинга принтера"""
    conn = await connect_db()
    try:
        result = await conn.fetchval("""
            SELECT AVG(rating) FROM reviews WHERE printer_id = $1;
        """, printer_id)
        return round(result, 1) if result else "Нет отзывов"
    except Exception as e:
        logger.error(f"Ошибка при получении среднего рейтинга: {e}")
        return "Нет отзывов"
    finally:
        await conn.close()

async def get_reviews(printer_id: int):
    """Получение всех отзывов о принтере"""
    conn = await connect_db()
    try:
        return await conn.fetch("""
            SELECT user_id, rating, comment, created_at FROM reviews
            WHERE printer_id = $1 ORDER BY created_at DESC;
        """, printer_id)
    except Exception as e:
        logger.error(f"Ошибка при получении отзывов: {e}")
        return []
    finally:
        await conn.close()
