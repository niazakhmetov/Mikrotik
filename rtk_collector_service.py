# ==============================================================================
# RTK_COLLECTOR_SERVICE.PY - Сервисное приложение для мониторинга RTK
# ==============================================================================
import time
import socket
import json
import sqlite3
from datetime import datetime

# ------------------------------------------------------------------------------
# 1. КОНСТАНТЫ И КОНФИГУРАЦИЯ
# ------------------------------------------------------------------------------
CONFIG_FILE = "config.json"
DB_NAME = "rtk_log.db" # База данных для записи статусов RTK

# ------------------------------------------------------------------------------
# 2. ФУНКЦИИ БАЗЫ ДАННЫХ
# ------------------------------------------------------------------------------

def initialize_db():
    """Создает таблицу для записи логов RTK-мониторинга, если она не существует."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS rtk_status (
            timestamp TEXT,
            ip TEXT,
            status TEXT,
            message TEXT
        )
    """)
    conn.commit()
    conn.close()

def log_rtk_status(ip, status, message):
    """Записывает результат проверки RTK в базу данных."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO rtk_status VALUES (?, ?, ?, ?)", 
                   (timestamp, ip, status, message))
    conn.commit()
    conn.close()

# ------------------------------------------------------------------------------
# 3. ФУНКЦИЯ МОНИТОРИНГА (ИЗМЕНЕННАЯ ВЕРСИЯ test_rtk_base_connection)
# ------------------------------------------------------------------------------

def check_rtk_base(ip, port, timeout, name):
    """
    Устанавливает TCP-соединение и проверяет наличие активного потока данных.
    
    Возвращает (status, message).
    """
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((ip, port))
        
        # Читаем небольшой объем данных, чтобы убедиться в активности потока
        data = sock.recv(1024) 
        sock.close()

        if data:
            return "OK", f"Поток активен, получено {len(data)} байт."
        else:
            return "WARNING", "Соединение установлено, но поток данных пуст (0 байт)."

    except socket.timeout:
        return "ERROR", f"Таймаут ({timeout}s). Не удалось установить соединение."
    except ConnectionRefusedError:
        return "ERROR", "Соединение отклонено. Порт закрыт или служба не запущена."
    except Exception as e:
        return "ERROR", f"Непредвиденная ошибка: {e}"

# ------------------------------------------------------------------------------
# 4. ГЛАВНЫЙ ЦИКЛ СЕРВИСА
# ------------------------------------------------------------------------------

def run_rtk_collector():
    """
    Основной цикл, который циклически проверяет статус RTK и логирует результат.
    """
    initialize_db()
    
    try:
        with open(CONFIG_FILE, 'r') as f:
            config = json.load(f)
        base_config = config.get("rtk_base_station", {})
        ip = base_config.get("ip")
        port = base_config.get("port")
        timeout = base_config.get("timeout", 5)
        
        if not ip or not port:
            print("ERROR: RTK IP/Port не настроены в config.json. Выход.")
            return

    except FileNotFoundError:
        print(f"ERROR: Файл конфигурации {CONFIG_FILE} не найден.")
        return
    except json.JSONDecodeError:
        print(f"ERROR: Ошибка парсинга {CONFIG_FILE}.")
        return

    print(f"--- RTK Collector Service запущен ({ip}:{port}) ---")
    
    # Цикл мониторинга: каждые 60 секунд (для промышленного мониторинга)
    MONITOR_INTERVAL = 60 

    while True:
        status, message = check_rtk_base(ip, port, timeout, base_config.get("name"))
        log_rtk_status(ip, status, message)
        
        current_time = datetime.now().strftime("%H:%M:%S")
        print(f"[{current_time}] Статус: {status}. Сообщение: {message}")
        
        # Ждем следующего цикла
        time.sleep(MONITOR_INTERVAL)

# ------------------------------------------------------------------------------
# 5. ТОЧКА ВХОДА
# ------------------------------------------------------------------------------

if __name__ == "__main__":
    run_rtk_collector()
