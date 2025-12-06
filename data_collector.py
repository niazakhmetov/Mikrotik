import paramiko
import csv
import time
from datetime import datetime
import re
import random # Для моков координат

# ==============================================================================
# КОНФИГУРАЦИЯ ПРОЕКТА
# Внимание: замените PLACEHOLDER на реальные данные!
# ==============================================================================
CONFIG = {
    # Параметры подключения к Mikrotik AP (MAC: 64:D1:54:6C:53:33)
    "MIKROTIK_IP": "192.168.88.1",  # IP адрес ТД
    "MIKROTIK_USER": "monitor_user", # Логин
    "MIKROTIK_PASSWORD": "YOUR_STRONG_PASSWORD", # Пароль

    # MAC-адреса клиентских приемников Mikrotik на буровых установках
    # Rig_ID: Client_MAC
    "RIG_CLIENT_MACS": {
        "Rig_1": "AA:BB:CC:DD:EE:F1",
        "Rig_2": "AA:BB:CC:DD:EE:F2",
        "Rig_3": "AA:BB:CC:DD:EE:F3",
        "Rig_4": "AA:BB:CC:DD:EE:F4",
        "Rig_5": "AA:BB:CC:DD:EE:F5",
    },

    # Настройки лог-файла
    "CSV_FILE_PATH": "coverage_log.csv",
    "COLLECTION_INTERVAL_SEC": 60 # Интервал сбора данных в секундах
}

# Заголовки для CSV-файла
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

# ==============================================================================
# ФУНКЦИИ СБОРА ДАННЫХ
# ==============================================================================

def initialize_csv(file_path):
    """Проверяет наличие CSV-файла и записывает заголовки, если файл пуст."""
    try:
        with open(file_path, 'r') as f:
            # Читаем первую строку. Если файл не пуст, выходим.
            if f.readline().strip():
                return
    except FileNotFoundError:
        pass # Файл не существует, создадим его.

    print(f"-> Создание нового файла {file_path} и запись заголовков.")
    with open(file_path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(CSV_HEADERS)

# ------------------------------------------------------------------------------
# ФУНКЦИЯ-ЗАГЛУШКА ДЛЯ SPS855 (для простоты)
# ------------------------------------------------------------------------------
def get_gps_data_mock(rig_id):
    """
    Эмуляция получения GPS-координат от SPS855.
    
    В реальном проекте здесь будет код, парсящий NMEA-поток
    с IP-сокета или последовательного порта SPS855.
    """
    # Используем смещение для имитации движения буровых в карьере
    base_lon = 67.50000 
    base_lat = 51.90000
    
    # Добавляем случайное смещение, имитирующее работу/движение буровых
    offset = random.uniform(-0.005, 0.005)
    
    # Присваиваем каждой буровой свою "базовую" позицию
    rig_base_pos = {
        "Rig_1": (base_lon + 0.01, base_lat + 0.01),
        "Rig_2": (base_lon - 0.01, base_lat + 0.02),
        "Rig_3": (base_lon + 0.005, base_lat - 0.005),
        "Rig_4": (base_lon - 0.02, base_lat - 0.01),
        "Rig_5": (base_lon, base_lat),
    }

    lon = rig_base_pos[rig_id][0] + offset
    lat = rig_base_pos[rig_id][1] + offset
    
    return lon, lat

# ------------------------------------------------------------------------------
# СБОР ДАННЫХ MIKROTIK
# ------------------------------------------------------------------------------
def get_mikrotik_data(client_mac):
    """Получает RSSI, TxRate и RxRate для одного MAC-адреса через SSH."""
    
    mikrotik_data = {
        "RSSI": None, 
        "TxRate": None, 
        "RxRate": None
    }
    
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        ssh.connect(
            hostname=CONFIG["MIKROTIK_IP"],
            username=CONFIG["MIKROTIK_USER"],
            password=CONFIG["MIKROTIK_PASSWORD"],
            port=22,
            timeout=5
        )
        
        # Команда RouterOS для получения данных
        command = f'/interface/wireless/registration-table print brief where mac-address="{client_mac}"'
        
        # Выполнение команды
        stdin, stdout, stderr = ssh.exec_command(command)
        output = stdout.read().decode('utf-8').strip()

        if not output:
            print(f"   [WARN] Клиент {client_mac} не найден в registration-table.")
            return mikrotik_data

        # Парсинг вывода: ищем нужные поля
        
        # 1. RSSI (пример: signal-strength=-68@60Mbps)
        rssi_match = re.search(r'signal-strength=(-?\d+)', output)
        if rssi_match:
            mikrotik_data["RSSI"] = int(rssi_match.group(1))

        # 2. TxRate
        tx_rate_match = re.search(r'tx-rate=(\d+\.?\d*Mbps)', output)
        if tx_rate_match:
            mikrotik_data["TxRate"] = tx_rate_match.group(1).replace("Mbps", "")
        
        # 3. RxRate
        rx_rate_match = re.search(r'rx-rate=(\d+\.?\d*Mbps)', output)
        if rx_rate_match:
            mikrotik_data["RxRate"] = rx_rate_match.group(1).replace("Mbps", "")
            
    except paramiko.AuthenticationException:
        print("   [ERROR] Ошибка аутентификации SSH. Проверьте логин/пароль.")
    except paramiko.SSHException as e:
        print(f"   [ERROR] SSH-ошибка: {e}")
    except Exception as e:
        print(f"   [ERROR] Неизвестная ошибка при подключении: {e}")
    finally:
        ssh.close()
        
    return mikrotik_data

# ==============================================================================
# ОСНОВНОЙ ЦИКЛ СБОРА
# ==============================================================================

def collect_data():
    """Основной цикл сбора и записи данных."""
    initialize_csv(CONFIG["CSV_FILE_PATH"])
    
    while True:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"\n--- Сбор данных: {timestamp} ---")
        
        collected_rows = []
        
        # Проход по всем буровым установкам
        for rig_id, mac_address in CONFIG["RIG_CLIENT_MACS"].items():
            print(f"-> Обработка {rig_id} ({mac_address})...")
            
            # 1. Сбор данных Mikrotik
            mikrotik_metrics = get_mikrotik_data(mac_address)
            
            # 2. Сбор GPS-данных
            lon, lat = get_gps_data_mock(rig_id)
            
            # 3. Формирование строки данных
            row = [
                timestamp,
                rig_id,
                mac_address,
                lon,
                lat,
                mikrotik_metrics["RSSI"],
                mikrotik_metrics["TxRate"],
                mikrotik_metrics["RxRate"]
            ]
            collected_rows.append(row)
            print(f"   [OK] RSSI: {mikrotik_metrics['RSSI']} дБм, Lon/Lat: {lon:.5f}/{lat:.5f}")

        # 4. Запись в CSV
        try:
            with open(CONFIG["CSV_FILE_PATH"], 'a', newline='') as f:
                writer = csv.writer(f)
                writer.writerows(collected_rows)
            print(f"--- Успешно записано {len(collected_rows)} строк в CSV. ---")
        except Exception as e:
            print(f"   [FATAL] Ошибка записи в CSV: {e}")
        
        # 5. Ожидание следующего цикла
        print(f"Ожидание {CONFIG['COLLECTION_INTERVAL_SEC']} секунд...")
        time.sleep(CONFIG["COLLECTION_INTERVAL_SEC"])

if __name__ == "__main__":
    try:
        collect_data()
    except KeyboardInterrupt:
        print("\nСбор данных остановлен пользователем.")
    except Exception as e:
        print(f"\nКритическая ошибка в основном цикле: {e}")
