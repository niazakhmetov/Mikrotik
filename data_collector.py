import paramiko
import csv
import time
from datetime import datetime, timedelta
import re
import json
import random 
import sys
import os
import sqlite3 # <-- НОВЫЙ ИМПОРТ

# --- Файлы проекта ---
CONFIG_FILE = 'config.json'
MIKROTIK_DB = 'mikrotik_log.db' # <-- НОВАЯ КОНСТАНТА БД

# ==============================================================================
# КОНФИГУРАЦИЯ И ЗАГРУЗКА
# ==============================================================================

def load_config():
    """Загружает конфигурацию из JSON-файла."""
    if not os.path.exists(CONFIG_FILE):
        print(f"Ошибка: Файл конфигурации '{CONFIG_FILE}' не найден.")
        sys.exit(1)
    with open(CONFIG_FILE, 'r') as f:
        return json.load(f)

CONFIG = load_config()

# Удаляем CSV_HEADERS, так как структура будет определяться SQL-схемой

def get_rig_info(rig_id):
    """Находит информацию о буровой установке по её ID (используем mikrotik_cpelist)."""
    # Обновляем, чтобы использовать новую структуру: mikrotik_cpelist
    for rig in CONFIG.get('mikrotik_cpelist', []):
        if rig['rig_id'] == rig_id:
            return rig
    return None

def initialize_db():
    """Создает таблицу mikrotik_log, если она не существует."""
    try:
        conn = sqlite3.connect(MIKROTIK_DB)
        cursor = conn.cursor()
        
        # SQL-схема для хранения логов Mikrotik
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS mikrotik_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                rig_id TEXT NOT NULL,
                client_mac TEXT NOT NULL,
                longitude REAL,
                latitude REAL,
                rssi INTEGER,
                tx_rate TEXT,
                rx_rate TEXT
            );
        """)
        conn.commit()
        conn.close()
        print(f"-> Инициализирована база данных: {MIKROTIK_DB}")
    except Exception as e:
        print(f"[FATAL] Ошибка инициализации базы данных: {e}")
        sys.exit(1)
        
# ------------------------------------------------------------------------------
# ФУНКЦИИ СБОРА ДАННЫХ (Оставляем без изменений)
# ------------------------------------------------------------------------------

def get_gps_data_mock(rig_id):
    """Эмуляция получения GPS-координат от SPS855."""
    base_lon = 67.50000 
    base_lat = 51.90000
    
    offset = random.uniform(-0.005, 0.005)
    
    # Присваиваем каждой буровой свою "базовую" позицию
    rig_base_pos = {
        "Rig_1": (base_lon + 0.01, base_lat + 0.01),
        "Rig_2": (base_lon - 0.01, base_lat + 0.02),
        "Rig_3": (base_lon + 0.005, base_lat - 0.005),
        "Rig_4": (base_lon - 0.02, base_lat - 0.01),
        "Rig_5": (base_lon, base_lat),
    }
    
    if rig_id not in rig_base_pos:
        rig_base_pos[rig_id] = (base_lon + random.uniform(-0.02, 0.02), base_lat + random.uniform(-0.02, 0.02))

    lon = rig_base_pos[rig_id][0] + offset
    lat = rig_base_pos[rig_id][1] + offset
    
    # Возвращаем долготу, широту и фиктивный HDOP
    return lon, lat, 1.2 

def get_mikrotik_data(client_mac):
    """Получает RSSI, TxRate и RxRate для одного MAC-адреса через SSH."""
    mikrotik_data = {"RSSI": None, "TxRate": None, "RxRate": None}
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        ssh.connect(
            hostname=CONFIG["mikrotik_ap"]["ip"],
            username=CONFIG["mikrotik_ap"]["user"],
            password=CONFIG["mikrotik_ap"]["password"],
            port=22,
            timeout=5
        )
        command = f'/interface/wireless/registration-table print brief where mac-address="{client_mac}"'
        stdin, stdout, stderr = ssh.exec_command(command)
        output = stdout.read().decode('utf-8').strip()

        if not output:
            print(f"   [WARN] Клиент {client_mac} не найден в registration-table.")
            return mikrotik_data

        rssi_match = re.search(r'signal-strength=(-?\d+)', output)
        if rssi_match:
            # RSSI должен быть целым числом
            mikrotik_data["RSSI"] = int(rssi_match.group(1))

        # TxRate и RxRate оставляем в виде строк (например, "54M" или "6.5M")
        tx_rate_match = re.search(r'tx-rate=(\d+\.?\d*Mbps)', output)
        if tx_rate_match:
            mikrotik_data["TxRate"] = tx_rate_match.group(1) #.replace("Mbps", "") # Оставим 'Mbps' для строкового хранения
            
        rx_rate_match = re.search(r'rx-rate=(\d+\.?\d*Mbps)', output)
        if rx_rate_match:
            mikrotik_data["RxRate"] = rx_rate_match.group(1) #.replace("Mbps", "")
            
    except paramiko.AuthenticationException:
        print("   [ERROR] Ошибка аутентификации SSH. Проверьте логин/пароль.")
    except Exception as e:
        print(f"   [ERROR] Ошибка подключения/парсинга: {e}")
    finally:
        if ssh.get_transport() is not None and ssh.get_transport().is_active():
            ssh.close()
            
    return mikrotik_data

# ==============================================================================
# ОСНОВНОЙ ЦИКЛ СБОРА (Обновленная версия)
# ==============================================================================

def write_to_db(data_row):
    """Записывает одну строку данных в базу данных SQLite."""
    conn = None
    try:
        conn = sqlite3.connect(MIKROTIK_DB)
        cursor = conn.cursor()
        
        # Используем INSERT INTO с параметрами для безопасности
        sql = """
            INSERT INTO mikrotik_log (timestamp, rig_id, client_mac, longitude, latitude, rssi, tx_rate, rx_rate)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        cursor.execute(sql, data_row)
        conn.commit()
    except sqlite3.Error as e:
        print(f"   [ERROR] Ошибка записи в БД: {e}")
    finally:
        if conn:
            conn.close()

def collect_data_for_rig(rig_id):
    """Основной цикл для ОДНОЙ буровой установки."""
    
    # 0. Инициализация БД
    initialize_db()

    rig_info = get_rig_info(rig_id)
    if not rig_info:
        print(f"[FATAL] Буровая установка с ID '{rig_id}' не найдена в config.json (mikrotik_cpelist). Выход.")
        return

    mac_address = rig_info['mikrotik_mac']
    interval_sec = CONFIG["data_storage"]["collection_interval_sec"]

    print(f"--- Мониторинг запущен для {rig_id} ({mac_address}). БД: {MIKROTIK_DB} ---")
    
    while True:
        try:
            timestamp = datetime.now()
            
            # 1. Сбор данных Mikrotik
            mikrotik_metrics = get_mikrotik_data(mac_address)
            
            # 2. Сбор GPS-данных (мокируем)
            lon, lat, hdop = get_gps_data_mock(rig_id)
            
            # 3. Формирование строки данных для БД
            data_row = (
                timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                rig_id,
                mac_address,
                lon,
                lat,
                mikrotik_metrics["RSSI"],
                mikrotik_metrics["TxRate"],
                mikrotik_metrics["RxRate"]
            )

            # 4. Запись в SQLite
            write_to_db(data_row)
                        
            print(f"[{timestamp.strftime('%H:%M:%S')}] {rig_id}: RSSI={mikrotik_metrics['RSSI']} dBm. Записано в БД.")

        except Exception as e:
            print(f"   [FATAL] Ошибка в цикле сбора для {rig_id}: {e}")
            
        time.sleep(interval_sec)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Использование: python data_collector.py <Rig_ID>")
        sys.exit(1)
        
    rig_id_to_monitor = sys.argv[1]
    
    try:
        collect_data_for_rig(rig_id_to_monitor)
    except KeyboardInterrupt:
        print(f"\nМониторинг {rig_id_to_monitor} остановлен вручную.")
    except Exception as e:
        print(f"\nКритическая ошибка: {e}")
