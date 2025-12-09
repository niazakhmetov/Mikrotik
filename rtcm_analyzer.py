import socket
import sqlite3
import time
from datetime import datetime
import json
import os
import sys
from pyrtcm import RTCMReader, RTCM_VERSION

# --- Константы ---
CONFIG_FILE = 'config.json'
RTK_DB = 'rtk_log.db'

# Интервал записи статистики в БД (в секундах)
LOG_INTERVAL_SEC = 60

# ==============================================================================
# КОНФИГУРАЦИЯ И УТИЛИТЫ
# ==============================================================================

def load_config():
    """Загружает конфигурацию из JSON-файла."""
    if not os.path.exists(CONFIG_FILE):
        print(f"[FATAL] Файл конфигурации '{CONFIG_FILE}' не найден.")
        sys.exit(1)
    with open(CONFIG_FILE, 'r') as f:
        return json.load(f)

CONFIG = load_config()
RTK_CONFIG = CONFIG.get('rtk_base_station', {})

def initialize_db():
    """Создает таблицу rtk_status с расширенной схемой для анализа RTCM."""
    try:
        conn = sqlite3.connect(RTK_DB)
        cursor = conn.cursor()
        
        # Обновленная SQL-схема для хранения аналитических данных
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS rtk_status (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                Overall_Status TEXT NOT NULL,
                Stream_Quality_Pct REAL,
                Active_Constellations TEXT,
                Station_ID INTEGER,
                Message_Count_Total INTEGER,
                Connection_Latency_sec REAL
            );
        """)
        conn.commit()
        conn.close()
        print(f"[RTK] База данных {RTK_DB} инициализирована с новой схемой.")
    except Exception as e:
        print(f"[RTK-FATAL] Ошибка инициализации БД: {e}")
        sys.exit(1)

def write_analysis_to_db(status, quality, systems, sta_id, total_count, latency):
    """Записывает результаты анализа в базу данных."""
    conn = None
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        conn = sqlite3.connect(RTK_DB)
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO rtk_status (
                timestamp, Overall_Status, Stream_Quality_Pct, Active_Constellations, 
                Station_ID, Message_Count_Total, Connection_Latency_sec
            ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (timestamp, status, quality, systems, sta_id, total_count, latency)
        )
        conn.commit()
        print(f"[{timestamp}] [DB OK] Запись: {status}, Качество: {quality:.1f}%, Системы: {systems}")
    except sqlite3.Error as e:
        print(f"[RTK-ERROR] Ошибка записи анализа в БД: {e}")
    finally:
        if conn:
            conn.close()

def get_constellation_from_type(msg_type: int) -> str:
    """Определяет звездную систему по типу RTCM-сообщения (Message Type ID)."""
    # Сообщения полных наблюдений (Full Observations)
    if 1074 <= msg_type <= 1077: return "GPS"
    if 1084 <= msg_type <= 1087: return "GLONASS"
    if 1094 <= msg_type <= 1097: return "GALILEO"
    if 1124 <= msg_type <= 1127: return "BeiDou"
    
    # Сообщения псевдодальности (SSR, State Space Representation)
    if 4070 <= msg_type <= 4077: return "GPS"
    # Добавьте другие типы сообщений по необходимости
    return "OTHER"

# ==============================================================================
# ОСНОВНОЙ АНАЛИЗАТОР
# ==============================================================================

def rtk_analyzer_loop():
    ip = RTK_CONFIG.get('ip')
    port = RTK_CONFIG.get('port')
    timeout = RTK_CONFIG.get('timeout_sec', 30)
    
    if not ip or not port:
        print("[RTK-FATAL] RTK IP/Port не настроены в config.json.")
        return

    while True:
        try:
            # 1. Попытка установить соединение (Таймаут соединения 5 сек)
            print(f"[{datetime.now().strftime('%H:%M:%S')}] [CONNECT] Попытка подключения к {ip}:{port}...")
            with socket.create_connection((ip, port), timeout=5) as sock:
                sock.settimeout(None) # Убираем таймаут для чтения, чтобы ждать данные
                
                # 2. Инициализация RTCMReader
                # Передаем файловый объект сокета, чтобы RTCMReader мог читать байты по одному
                rtcm_reader = RTCMReader(stream=sock.makefile(mode='rb'), protfilter=RTCM_VERSION.RTCM3) 
                
                # --- Счетчики для статистики за интервал ---
                total_messages = 0
                crc_ok_messages = 0
                active_constellations = set()
                station_id = None
                last_db_log_time = time.time()
                
                print("[RTK-OK] Соединение активно. Начало парсинга RTCMv3...")

                while True:
                    # Чтение и декодирование следующего сообщения
                    (raw_data, parsed_message) = rtcm_reader.readmessage()
                    
                    if raw_data is not None:
                        total_messages += 1
                        
                        current_time = time.time()
                        
                        if parsed_message is not None:
                            # CRC прошла успешно (иначе parsed_message был бы None)
                            crc_ok_messages += 1
                            msg_type = parsed_message.identity

                            # 1. Определение активной системы
                            const = get_constellation_from_type(msg_type)
                            if const != "OTHER":
                                active_constellations.add(const)

                            # 2. Извлечение ID станции (из сообщений, содержащих этот атрибут)
                            if hasattr(parsed_message, 'staid') and parsed_message.staid is not None:
                                station_id = parsed_message.staid
                            
                        # 3. Запись статистики в БД
                        if current_time - last_db_log_time >= LOG_INTERVAL_SEC:
                            
                            # Расчет качества потока
                            quality_pct = (crc_ok_messages / total_messages) * 100 if total_messages > 0 else 0
                            
                            # Логирование в БД
                            write_analysis_to_db(
                                status="OK", 
                                quality=quality_pct, 
                                systems=", ".join(sorted(active_constellations)),
                                sta_id=station_id,
                                total_count=total_messages,
                                latency=current_time - last_db_log_time
                            )
                            
                            # Сброс счетчиков
                            total_messages = 0
                            crc_ok_messages = 0
                            active_constellations.clear()
                            last_db_log_time = current_time

        except socket.timeout:
            error_msg = f"Таймаут соединения: Не удалось подключиться к {ip}:{port}."
            print(f"[RTK-ERROR] {error_msg}")
            write_analysis_to_db("ERROR", 0.0, "", None, 0, 0.0)
            
        except ConnectionRefusedError:
            error_msg = "Отказано в соединении: Базовая станция недоступна или служба не запущена."
            print(f"[RTK-ERROR] {error_msg}")
            write_analysis_to_db("ERROR", 0.0, "", None, 0, 0.0)
            
        except Exception as e:
            error_msg = f"Критическая ошибка в цикле RTCM-анализа: {e}"
            print(f"[RTK-ERROR] {error_msg}")
            write_analysis_to_db("ERROR", 0.0, f"Exception: {e}", None, 0, 0.0)

        # Пауза перед следующей попыткой подключения
        time.sleep(10) 

# ==============================================================================
# ЗАПУСК СЕРВИСА
# ==============================================================================

if __name__ == "__main__":
    if not os.path.exists('logs'):
        os.makedirs('logs')
        
    initialize_db()
    
    print(f"--- RTCM Analyzer Service запущен. Запись статистики каждые {LOG_INTERVAL_SEC} сек. ---")
    
    try:
        rtk_analyzer_loop()
    except KeyboardInterrupt:
        print("\n[RTK] Сервис остановлен вручную.")
    except Exception as e:
        print(f"\n[RTK-CRITICAL] Непредвиденная ошибка запуска: {e}")
