import argparse
import json
import os
import subprocess
import sys
from pprint import pprint

CONFIG_FILE = 'config.json'
COLLECTOR_SCRIPT = 'data_collector.py'
VISUALIZATION_SCRIPT = 'visualization.py'
LOG_FILE = 'coverage_log.csv'

def load_config():
    """Загружает конфигурацию из JSON-файла."""
    if not os.path.exists(CONFIG_FILE):
        print(f"Ошибка: Файл конфигурации '{CONFIG_FILE}' не найден.")
        sys.exit(1)
    with open(CONFIG_FILE, 'r') as f:
        return json.load(f)

def save_config(config):
    """Сохраняет конфигурацию в JSON-файл."""
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=4)
    print(f"✅ Конфигурация успешно сохранена в {CONFIG_FILE}.")

## --- Управление Процессами (Start/Stop) ---

def start_monitoring():
    """Запускает скрипт сбора данных в фоновом режиме."""
    print("▶️ Запуск мониторинга...")
    try:
        # Для простоты и универсальности CLI, мы используем 'nohup' 
        # для запуска скрипта в фоновом режиме, если ОС это поддерживает.
        # В реальной системе рекомендуется использовать systemd или Supervisor.
        command = f"nohup python3 {COLLECTOR_SCRIPT} &"
        subprocess.run(command, shell=True, check=True)
        print(f"✅ Сборщик данных '{COLLECTOR_SCRIPT}' запущен в фоновом режиме.")
        print("💡 Проверьте логи для подтверждения запуска.")
    except Exception as e:
        print(f"❌ Ошибка при попытке запуска: {e}")
        print("Пожалуйста, убедитесь, что 'python3' доступен и скрипт существует.")

def stop_monitoring():
    """Останавливает скрипт сбора данных."""
    print("⏹️ Остановка мониторинга...")
    try:
        # Это упрощенный метод, который ищет процесс по имени скрипта.
        # Может быть ненадежным, но соответствует требованию "простоты".
        subprocess.run(["pkill", "-f", COLLECTOR_SCRIPT], check=False)
        print("✅ Попытка остановить фоновый процесс завершена. Проверьте, что процесс остановлен.")
    except Exception as e:
        print(f"❌ Ошибка при попытке остановки: {e}")

## --- Управление Сущностями (Rigs/Mikrotiks) ---

def add_rig(args):
    """Добавляет новую буровую установку в конфигурацию."""
    config = load_config()
    new_rig = {
        "rig_id": args.id,
        "mikrotik_mac": args.mac.upper(),
        "sps855_ip": args.ip
    }
    
    # Проверка на дублирование ID или MAC
    for rig in config['rigs']:
        if rig['rig_id'] == args.id:
            print(f"❌ Буровая установка с ID '{args.id}' уже существует.")
            return
        if rig['mikrotik_mac'] == args.mac.upper():
            print(f"❌ Mikrotik с MAC '{args.mac.upper()}' уже зарегистрирован.")
            return

    config['rigs'].append(new_rig)
    save_config(config)
    print(f"✅ Буровая установка '{args.id}' успешно добавлена.")

def show_config():
    """Показывает текущую конфигурацию и список буровых установок."""
    config = load_config()
    print("--- Текущая Конфигурация Проекта ---")
    pprint(config)
    print("------------------------------------")

## --- Визуализация и Логи ---

def show_map():
    """Запускает генерацию карты и сообщает, где ее искать."""
    print("🗺️ Генерация карты покрытия...")
    try:
        subprocess.run(["python3", VISUALIZATION_SCRIPT], check=True)
        print(f"✅ Карта покрытия сохранена в файл '{VISUALIZATION_SCRIPT.replace('.py', '.png')}'")
    except subprocess.CalledProcessError:
        print(f"❌ Ошибка при выполнении скрипта визуализации. Проверьте {LOG_FILE}.")
    except FileNotFoundError:
        print(f"❌ Скрипт '{VISUALIZATION_SCRIPT}' не найден. Убедитесь, что он находится в папке проекта.")

def show_logs(args):
    """Выводит последние строки лог-файла."""
    try:
        if not os.path.exists(LOG_FILE):
            print(f"Файл логов '{LOG_FILE}' пока пуст или не существует.")
            return
            
        print(f"--- Последние {args.lines} строк лога ---")
        # Используем команду tail (Unix/Linux) для простоты
        subprocess.run(["tail", f"-n{args.lines}", LOG_FILE])
        print("----------------------------------------")
    except FileNotFoundError:
        print(f"Команда 'tail' не найдена. Попробуйте просмотреть файл '{LOG_FILE}' вручную.")

## --- Основная Логика CLI ---

def main():
    parser = argparse.ArgumentParser(
        description="Главное приложение для управления мониторингом Wi-Fi в карьере.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    subparsers = parser.add_subparsers(dest='command', help='Доступные команды')

    # --- Команда START ---
    subparsers.add_parser('start', help='Запустить сбор данных в фоновом режиме.')

    # --- Команда STOP ---
    subparsers.add_parser('stop', help='Остановить фоновый процесс сбора данных.')

    # --- Команда CONFIG ---
    subparsers.add_parser('config', help='Показать текущую конфигурацию проекта.')

    # --- Команда MAP ---
    subparsers.add_parser('map', help='Сгенерировать карту покрытия (coverage_heatmap.png).')

    # --- Команда LOGS ---
    logs_parser = subparsers.add_parser('logs', help='Показать последние записи из лог-файла.')
    logs_parser.add_argument('-l', '--lines', type=int, default=10, help='Количество последних строк для отображения (по умолчанию 10).')

    # --- Команда ADD-RIG ---
    add_parser = subparsers.add_parser('add-rig', help='Добавить новую буровую установку (Mikrotik/SPS855).')
    add_parser.add_argument('id', type=str, help='Уникальный ID буровой установки (напр., Rig_06).')
    add_parser.add_argument('mac', type=str, help='MAC-адрес приемника Mikrotik на буровой.')
    add_parser.add_argument('ip', type=str, help='IP-адрес или идентификатор потока данных SPS855.')
    add_parser.set_defaults(func=add_rig)

    # Разбор аргументов
    args = parser.parse_args()

    if args.command == 'start':
        start_monitoring()
    elif args.command == 'stop':
        stop_monitoring()
    elif args.command == 'config':
        show_config()
    elif args.command == 'map':
        show_map()
    elif args.command == 'logs':
        show_logs(args)
    elif args.command == 'add-rig':
        args.func(args)
    else:
        parser.print_help()

if __name__ == '__main__':
    main()
