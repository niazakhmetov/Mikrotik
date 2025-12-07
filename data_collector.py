import paramiko
import csv
import time
from datetime import datetime, timedelta
import re
import json
import random 
import sys
import os

# --- Файлы проекта ---
CONFIG_FILE = 'config.json'
LOG_DIR = 'logs'

# ==============================================================================
# КОНФИГУРАЦИЯ И ЗАГРУЗКА
# ==============================================================================

def load_config():
    """Загружает конфигурацию из JSON-файла."""
    # Проверяем наличие config.json в текущей директории
    if not os.path.exists(CONFIG_FILE):
        print(f"Ошибка: Файл конфигурации '{CONFIG_FILE}' не найден.")
        sys.exit(1)
    with open(CONFIG_FILE, 'r') as f:
        return json.load(f)

CONFIG = load_config()

CSV_HEADERS = [
    "Timestamp",
    "Rig_ID",
    "Client_MAC",
    "Longitude_X",
    "Latitude_Y",
    "RSSI",
    "TxRate",
    "RxRate"
]

def get_rig_info(rig_id):
    """Находит информацию о буровой установке по её ID."""
    for rig in CONFIG.get('rigs', []):
        if rig['rig_id'] == rig_id:
            return rig
    return None

def get_log_file_path(now=None):
    """
    Определяет имя лог-файла на основе рабочего дня (с 20:00 до 20:00).
    Рабочий день датируется днем, на который приходится его окончание (т.е. 20:00).
    """
    if now is None:
        now = datetime.now()
        
    # Если время >= 20:00, данные относятся к завтрашнему рабочему дню (заканчивается завтра в 20:00).
    if now.hour >= 20:
        log_date = now.date() + timedelta(days=1)
    # Если время < 20:00, данные относятся к текущему рабочему дню (заканчивается сегодня в 20:00).
    else:
        log_date = now.date()
        
    # Формат пути: logs/coverage_log_YYYY-MM-DD.csv
    return os.path.join(LOG_DIR, f"coverage_log_{log_date.strftime('%Y-%m-%d')}.csv")

def initialize_csv(file_path):
    """Проверяет наличие CSV-файла и записывает заголовки, если файл пуст."""
    # Убеждаемся, что папка logs существует
    if not os.path.exists(LOG_DIR):
         os.makedirs(LOG_DIR)
         
    if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
        with open(file_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(CSV_HEADERS)
        print(f"-> Создан новый лог-файл: {file_path}")

# ------------------------------------------------------------------------------
# ФУНКЦИИ СБОРА ДАННЫХ
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
            mikrotik_data["RSSI"] = int(rssi_match.group(1))

        tx_rate_match = re.search(r'tx-rate=(\d+\.?\d*Mbps)', output)
        if tx_rate_match:
            mikrotik_data["TxRate"] = tx_rate_match.group(1).replace("Mbps", "")
        
        rx_rate_match = re.search(r'rx-rate=(\d+\.?\d*Mbps)', output)
        if rx_rate_match:
            mikrotik_data["RxRate"] = rx_rate_match.group(1).replace("Mbps", "")
            
    except paramiko.AuthenticationException:
        print("   [ERROR] Ошибка аутентификации SSH. Проверьте логин/пароль.")
    except Exception as e:
        print(f"   [ERROR] Ошибка подключения/парсинга: {e}")
    finally:
        if ssh.get_transport() is not None and ssh.get_transport().is_active():
            ssh.close()
        
    return mikrotik_data

# ==============================================================================
# ОСНОВНОЙ ЦИКЛ СБОРА
# ==============================================================================

def collect_data_for_rig(rig_id):
    """Основной цикл для ОДНОЙ буровой установки."""
    rig_info = get_rig_info(rig_id)
    if not rig_info:
        print(f"[FATAL] Буровая установка с ID '{rig_id}' не найдена в config.json. Выход.")
        return

    # 1. Определяем путь к лог-файлу для начала работы
    current_log_file = get_log_file_path()
    initialize_csv(current_log_file)
    
    mac_address = rig_info['mikrotik_mac']
    interval_sec = CONFIG["data_storage"]["collection_interval_sec"]

    print(f"--- Мониторинг запущен для {rig_id} ({mac_address}). Лог: {current_log_file} ---")
    
    while True:
        try:
            timestamp = datetime.now()
            
            # 1. Проверка смены рабочего дня (переход через 20:00)
            new_log_file = get_log_file_path(timestamp)
            if new_log_file != current_log_file:
                 current_log_file = new_log_file
                 initialize_csv(current_log_file)
                 print(f"--- Смена рабочего дня. Новый лог: {current_log_file} ---")
            
            # 2. Сбор данных Mikrotik
            mikrotik_metrics = get_mikrotik_data(mac_address)
            
            # 3. Сбор GPS-данных (мокируем)
            lon, lat, hdop = get_gps_data_mock(rig_id)
            
            # 4. Формирование строки данных
            row = [
                timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                rig_id,
                mac_address,
                lon,
                lat,
                mikrotik_metrics["RSSI"],
                mikrotik_metrics["TxRate"],
                mikrotik_metrics["RxRate"]
            ]

            # 5. Запись в CSV
            with open(current_log_file, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(row)
                
            print(f"[{timestamp.strftime('%H:%M:%S')}] {rig_id}: RSSI={mikrotik_metrics['RSSI']} dBm")

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