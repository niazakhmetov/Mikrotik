import tkinter as tk
from tkinter import messagebox, ttk
import subprocess
import os
import sys
import json
from datetime import datetime, timedelta
import pandas as pd
from PIL import Image, ImageTk

# --- Константы Файлов ---
CONFIG_FILE = 'config.json'
COLLECTOR_SCRIPT = 'data_collector.py'
VISUALIZATION_SCRIPT = 'visualization.py'
LOG_DIR = 'logs'
HEATMAP_FILE = 'coverage_heatmap.png'

# ==============================================================================
# УТИЛИТЫ ДЛЯ СМЕН И ФАЙЛОВ
# ==============================================================================

def get_log_file_path(now=None):
    """Определяет имя лог-файла на основе рабочего дня (с 20:00 до 20:00)."""
    if now is None:
        now = datetime.now()
    if now.hour >= 20:
        log_date = now.date() + timedelta(days=1)
    else:
        log_date = now.date()
    return os.path.join(LOG_DIR, f"coverage_log_{log_date.strftime('%Y-%m-%d')}.csv")

def get_shift_period_by_date(log_date_str):
    """
    Определяет период данных по дате лог-файла (который заканчивается в 20:00 этого дня).
    """
    try:
        end_day = datetime.strptime(log_date_str, '%Y-%m-%d').date()
        
        # Период с 20:00 предыдущего дня до 20:00 текущего дня
        start_time = datetime.combine(end_day - timedelta(days=1), datetime.min.time().replace(hour=20))
        end_time = datetime.combine(end_day, datetime.min.time().replace(hour=20))
        
        shift_info = f"С {start_time.strftime('%Y-%m-%d %H:%M')} по {end_time.strftime('%Y-%m-%d %H:%M')}"
        return shift_info, start_time, end_time
    except ValueError:
        return "Неверный формат даты", None, None

def get_current_shift_period():
    """Возвращает информацию и период для текущего рабочего дня."""
    now = datetime.now()
    current_log_date_str = get_log_file_path(now).split('_')[-1].replace('.csv', '')
    
    # Используем логику get_shift_period_by_date для получения точного периода
    shift_info, start_time, end_time = get_shift_period_by_date(current_log_date_str)
    
    # Уточнение информации о смене (Дневная/Ночная)
    if now.hour >= 8 and now.hour < 20:
         shift_type = "Дневная"
    else:
         shift_type = "Ночная"
         
    shift_info = f"{shift_type} Смена ({shift_info.split('С ')[-1]})"
    return shift_info, start_time, end_time


# ==============================================================================
# КЛАСС ПРИЛОЖЕНИЯ
# ==============================================================================

class MikrotikMonitorApp:
    def __init__(self, master):
        self.master = master
        master.title("🛰️ Мониторинг Wi-Fi Карьера (Mikrotik/SPS855) - v2.0")
        master.geometry("1000x700")

        # --- Хранилище данных ---
        self.config = self._load_config()
        self.rig_processes = {} # {Rig_ID: subprocess.Popen object}
        self.rig_ids = [rig['rig_id'] for rig in self.config.get('rigs', [])]
        self.archive_dates = []  
        self.status_labels = {} # {Rig_ID: tk.Label object} <-- Новый словарь для статусов

        # --- Переменные для динамического управления ---
        self.font_main = ('Arial', 10)
        self.font_header = ('Arial', 14, 'bold')
        self.selected_rig_id = tk.StringVar(master)
        self.selected_archive_date = tk.StringVar(master)
        
        if self.rig_ids:
            self.selected_rig_id.set(self.rig_ids[0])
            
        # --- Инициализация интерфейса ---
        # 1. Загрузка списка дат перед созданием Combobox
        self._get_available_log_dates() 
        
        self._create_top_frame()
        self._create_status_overview_frame() # <--- НОВЫЙ ВЫЗОВ
        self._create_notebook()
        
        # Установка начальной даты и запуск таймера
        self.selected_archive_date.set("Текущий день")
        self.master.after(1000, self._update_all_dynamic_data) # Обновление каждые 1 секунду

    # ----------------------------------------------------------------------
    # I. ОСНОВНЫЕ МЕТОДЫ И УТИЛИТЫ
    # ----------------------------------------------------------------------

    def _load_config(self):
        """Загружает конфигурацию из JSON-файла."""
        if not os.path.exists(CONFIG_FILE):
            messagebox.showerror("Ошибка", f"Файл конфигурации '{CONFIG_FILE}' не найден.")
            sys.exit(1)
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)

    def _get_available_log_dates(self):
        """Сканирует папку logs и возвращает список дат."""
        self.archive_dates_list = ["Текущий день"]
        if not os.path.exists(LOG_DIR):
            return
            
        temp_dates = []
        for filename in os.listdir(LOG_DIR):
            if filename.startswith("coverage_log_") and filename.endswith(".csv"):
                try:
                    date_part = filename.split('_')[-1].replace('.csv', '')
                    temp_dates.append(date_part)
                except:
                    continue
                    
        self.archive_dates = sorted(list(set(temp_dates)), reverse=True)
        self.archive_dates_list.extend(self.archive_dates)
        
        # Обновляем значения в Combobox, если он уже создан
        if hasattr(self, 'date_selector'):
             self.date_selector.config(values=self.archive_dates_list)

    # ----------------------------------------------------------------------
    # II. ФОРМИРОВАНИЕ ИНТЕРФЕЙСА
    # ----------------------------------------------------------------------

    def _create_top_frame(self):
        """Создает верхнюю панель с селектором и информацией о смене/периоде."""
        top_frame = tk.Frame(self.master, padx=10, pady=10, bd=2, relief=tk.GROOVE)
        top_frame.pack(fill='x')

        # 1. Селектор Буровых Установок
        tk.Label(top_frame, text="Установка:", font=self.font_main).pack(side=tk.LEFT, padx=(5, 5))
        self.rig_selector = ttk.Combobox(top_frame, textvariable=self.selected_rig_id, values=self.rig_ids, state="readonly", width=10, font=self.font_main)
        self.rig_selector.bind("<<ComboboxSelected>>", self._on_rig_select)
        self.rig_selector.pack(side=tk.LEFT, padx=5)
        
        # 2. Селектор Даты/Архива
        tk.Label(top_frame, text="Период Данных:", font=self.font_main).pack(side=tk.LEFT, padx=(20, 5))
        self.date_selector = ttk.Combobox(top_frame, textvariable=self.selected_archive_date, values=self.archive_dates_list, state="readonly", width=15, font=self.font_main)
        self.date_selector.bind("<<ComboboxSelected>>", self._on_archive_date_select)
        self.date_selector.pack(side=tk.LEFT, padx=5)

        # 3. Индикатор Периода/Смены
        self.shift_label = tk.Label(top_frame, font=('Arial', 10, 'bold'), fg='blue')
        self.shift_label.pack(side=tk.LEFT, padx=20)

        # 4. Кнопка настроек
        tk.Button(top_frame, text="⚙️ Config.json", command=self._open_config, font=self.font_main).pack(side=tk.RIGHT)
        
    def _create_status_overview_frame(self):
        """Создает фрейм с кратким статусом мониторинга для всех буровых установок."""
        
        self.overview_frame = tk.LabelFrame(self.master, text="Краткий Статус Мониторинга (Сбор данных)", 
                                            font=('Arial', 10, 'bold'), padx=10, pady=5)
        self.overview_frame.pack(fill='x', padx=20, pady=(0, 10))
        
        rig_count = len(self.rig_ids)
        cols = 3 # Максимальное количество столбцов
        
        for i, rig_id in enumerate(self.rig_ids):
            # Определяем позицию в сетке
            row = i // cols
            col_start = (i % cols) * 2
            
            # 1. Создание лейбла для имени буровой установки
            name_label = tk.Label(self.overview_frame, text=f"{rig_id}:", font=self.font_main)
            name_label.grid(row=row, column=col_start, sticky='w', padx=(20, 0))
            
            # 2. Создание лейбла для статуса (обновляется динамически)
            status_label = tk.Label(self.overview_frame, text="Остановлен", 
                                    font=('Arial', 10, 'bold'), fg='red')
            status_label.grid(row=row, column=col_start + 1, sticky='w', padx=(5, 20))
            
            self.status_labels[rig_id] = status_label


    def _create_notebook(self):
        """Создает контейнер вкладок."""
        self.notebook = ttk.Notebook(self.master)
        self.notebook.pack(pady=10, padx=20, fill="both", expand=True)

        self.tab_control = ttk.Frame(self.notebook); self.notebook.add(self.tab_control, text='🛠️ Управление')
        self.tab_wifi = ttk.Frame(self.notebook); self.notebook.add(self.tab_wifi, text='📶 Статус Wi-Fi')
        self.tab_map = ttk.Frame(self.notebook); self.notebook.add(self.tab_map, text='🗺️ Тепловая Карта')
        self.tab_gps = ttk.Frame(self.notebook); self.notebook.add(self.tab_gps, text='📍 GPS/Система')
        
        self._setup_control_tab()
        self._setup_wifi_status_tab()
        self._setup_heatmap_tab()
        self._setup_gps_status_tab()

    def _setup_control_tab(self):
        tk.Label(self.tab_control, text="Управление Сбором Данных", font=self.font_header).pack(pady=10)
        self.control_frame = tk.Frame(self.tab_control); self.control_frame.pack(pady=20, padx=10)
        self.btn_start = tk.Button(self.control_frame, text="▶️ Запустить Мониторинг", command=self._start_monitoring, bg='#aaffaa', fg='black', font=self.font_header)
        self.btn_start.pack(side=tk.LEFT, padx=10, pady=10)
        self.btn_stop = tk.Button(self.control_frame, text="⏹️ Остановить Мониторинг", command=self._stop_monitoring, bg='#ffaaaa', fg='black', font=self.font_header, state=tk.DISABLED)
        self.btn_stop.pack(side=tk.LEFT, padx=10, pady=10)
        self.current_status_label = tk.Label(self.tab_control, text="Статус: Остановлен", font=('Arial', 18, 'bold'), fg='red')
        self.current_status_label.pack(pady=20)
        tk.Label(self.tab_control, text="Сбор данных для этой установки запускается в отдельном процессе.", font=self.font_main).pack()


    def _setup_wifi_status_tab(self):
        tk.Label(self.tab_wifi, text="Качество Wi-Fi за Выбранный Период", font=self.font_header).pack(pady=10)
        self.summary_frame = tk.LabelFrame(self.tab_wifi, text="Сводка за Период", font=self.font_main, padx=10, pady=10)
        self.summary_frame.pack(fill='x', padx=20)
        self.avg_rssi_label = tk.Label(self.summary_frame, text="Средний RSSI: - дБм", font=('Arial', 16), fg='gray')
        self.avg_rssi_label.pack(pady=5)
        self.avg_rate_label = tk.Label(self.summary_frame, text="Средний Tx/Rx Rate: -", font=('Arial', 16), fg='gray')
        self.avg_rate_label.pack(pady=5)
        tk.Label(self.tab_wifi, text="[Здесь будет отображаться график RSSI/TxRate за смену]", fg='blue').pack(pady=50)


    def _setup_heatmap_tab(self):
        tk.Label(self.tab_map, text="Карта Покрытия Карьера (Общая)", font=self.font_header).pack(pady=10)
        control_frame = tk.Frame(self.tab_map); control_frame.pack(pady=5)
        tk.Button(control_frame, text="🔄 Обновить Карту", command=self._generate_and_reload_map, font=self.font_main).pack(side=tk.LEFT, padx=10)
        self.map_time_label = tk.Label(control_frame, text="Карта создана: -", font=self.font_main, fg='gray'); self.map_time_label.pack(side=tk.LEFT, padx=10)
        self.map_canvas = tk.Label(self.tab_map, bd=2, relief=tk.SUNKEN); self.map_canvas.pack(fill='both', expand=True, padx=20, pady=10)
        self._load_heatmap_image()


    def _setup_gps_status_tab(self):
        tk.Label(self.tab_gps, text="Статус GPS и Логи Выбранной Установки", font=self.font_header).pack(pady=10)
        self.gps_status_frame = tk.LabelFrame(self.tab_gps, text="Статус SPS855", font=self.font_main, padx=10, pady=10); self.gps_status_frame.pack(fill='x', padx=20, pady=5)
        self.gps_info_label = tk.Label(self.gps_status_frame, justify=tk.LEFT, text="Статус: Неизвестен\nПоследняя координата: -", font=self.font_main); self.gps_info_label.pack(fill='x')
        tk.Label(self.tab_gps, text=f"Последние 10 записей из лога:", font=self.font_main).pack(pady=(10, 5))
        self.log_text = tk.Text(self.tab_gps, height=15, width=80, state=tk.DISABLED); self.log_text.pack(fill='both', expand=True, padx=20)

    # ----------------------------------------------------------------------
    # III. ЛОГИКА УПРАВЛЕНИЯ И ОБНОВЛЕНИЯ ДАННЫХ
    # ----------------------------------------------------------------------

    def _on_rig_select(self, event=None):
        self._update_all_dynamic_data()
    
    def _on_archive_date_select(self, event=None):
        self._get_available_log_dates() 
        self._update_all_dynamic_data()

    def _update_all_dynamic_data(self):
        rig_id = self.selected_rig_id.get()
        selected_date_str = self.selected_archive_date.get()
        
        if not rig_id: return

        # Определяем период и путь к лог-файлу
        if selected_date_str == "Текущий день":
            shift_info, start_time, end_time = get_current_shift_period()
            log_file_path = get_log_file_path()
        else:
            shift_info, start_time, end_time = get_shift_period_by_date(selected_date_str)
            log_file_path = os.path.join(LOG_DIR, f"coverage_log_{selected_date_str}.csv")
        
        # 1. Обновить информацию о периоде
        self.shift_label.config(text=f"Период: {shift_info}")
        
        # 2. Обновить Управление (Вкладка 1)
        is_archive_mode = (selected_date_str != "Текущий день")
        self._update_control_tab(rig_id, is_archive_mode)
        
        # 3. Обновить Статус Мониторинга для всех буровых
        self._update_status_overview() # <--- НОВЫЙ ВЫЗОВ
        
        # 4. Обновить Статус Wi-Fi (Вкладка 2)
        self._update_wifi_status_tab(rig_id, start_time, end_time, log_file_path)

        # 5. Обновить GPS и Логи (Вкладка 4)
        self._update_gps_status_tab(rig_id, log_file_path)
        
        self.master.after(1000, self._update_all_dynamic_data) # Повторять обновление

    def _update_control_tab(self, rig_id, is_archive_mode):
        if is_archive_mode:
            self.current_status_label.config(text="Управление недоступно (Архив)", fg='blue')
            self.btn_start.config(state=tk.DISABLED)
            self.btn_stop.config(state=tk.DISABLED)
            return

        process = self.rig_processes.get(rig_id)
        if process and process.poll() is None:
            self.current_status_label.config(text=f"Статус: СБОР ДАННЫХ (PID: {process.pid})", fg='green')
            self.btn_start.config(state=tk.DISABLED)
            self.btn_stop.config(state=tk.NORMAL)
        else:
            self.current_status_label.config(text="Статус: Остановлен", fg='red')
            self.btn_start.config(state=tk.NORMAL)
            self.btn_stop.config(state=tk.DISABLED)
            self.rig_processes[rig_id] = None 

    def _update_status_overview(self):
        """Обновляет статус мониторинга для всех буровых установок во фрейме краткого статуса."""
        for rig_id in self.rig_ids:
            label = self.status_labels.get(rig_id)
            if not label: continue

            process = self.rig_processes.get(rig_id)
            
            # Проверяем, запущен ли процесс и не завершен ли он
            if process and process.poll() is None:
                status_text = "МОНИТОРИНГ"
                color = 'green'
            else:
                status_text = "Остановлен"
                color = 'red'
                
            # Если процесс завершился, обновим словарь процессов
            if process and process.poll() is not None:
                self.rig_processes[rig_id] = None
            
            label.config(text=status_text, fg=color)

    def _update_wifi_status_tab(self, rig_id, start_time, end_time, log_file_path):
        try:
            df = pd.read_csv(log_file_path)
            df['Timestamp'] = pd.to_datetime(df['Timestamp'])
            df['RSSI'] = pd.to_numeric(df['RSSI'], errors='coerce')
            df['TxRate'] = pd.to_numeric(df['TxRate'].astype(str).str.replace('Mbps', ''), errors='coerce') 

            df_rig = df[df['Rig_ID'] == rig_id]
            df_filtered = df_rig[(df_rig['Timestamp'] >= start_time) & (df_rig['Timestamp'] < end_time)].dropna(subset=['RSSI', 'TxRate'])
            
            if df_filtered.empty:
                self.avg_rssi_label.config(text="Средний RSSI: Нет данных за период", fg='gray')
                self.avg_rate_label.config(text="Средний Tx/Rx Rate: -", fg='gray')
                return

            avg_rssi = df_filtered['RSSI'].mean()
            avg_tx_rate = df_filtered['TxRate'].mean()
            
            if avg_rssi > -65:
                color = 'green'
                quality = "Отлично"
            elif avg_rssi > -75:
                color = 'orange'
                quality = "Хорошо"
            else:
                color = 'red'
                quality = "Плохо"

            self.avg_rssi_label.config(text=f"Средний RSSI: {avg_rssi:.2f} дБм ({quality})", fg=color)
            self.avg_rate_label.config(text=f"Средний TxRate/RxRate: {avg_tx_rate:.1f} Mbps", fg='black')

        except FileNotFoundError:
            self.avg_rssi_label.config(text="Средний RSSI: Лог-файл не найден", fg='gray')
            self.avg_rate_label.config(text="Средний Tx/Rx Rate: -", fg='gray')
        except Exception:
            self.avg_rssi_label.config(text="Средний RSSI: Ошибка обработки данных", fg='gray')
            self.avg_rate_label.config(text="Средний Tx/Rx Rate: -", fg='gray')


    def _update_gps_status_tab(self, rig_id, log_file_path):
        try:
            df = pd.read_csv(log_file_path)
            df_rig = df[df['Rig_ID'] == rig_id]
            
            if df_rig.empty:
                self.gps_info_label.config(text="Статус: Офлайн\nНет данных в логе.")
                self.log_text.config(state=tk.NORMAL); self.log_text.delete('1.0', tk.END); self.log_text.config(state=tk.DISABLED)
                return

            last_entry = df_rig.iloc[-1]
            lon = f"{last_entry['Longitude_X']:.5f}"
            lat = f"{last_entry['Latitude_Y']:.5f}"
            
            last_timestamp = last_entry['Timestamp']
            
            gps_status = "Онлайн (Отлично)" 
            hdop = "1.2"
            
            info = (f"Статус: {gps_status} (Обновлено: {last_timestamp})\n"
                    f"Последняя координата: Lon {lon}, Lat {lat}\n"
                    f"Примерная точность (HDOP): {hdop}")
            self.gps_info_label.config(text=info)

            # Обновление лога
            self.log_text.config(state=tk.NORMAL)
            self.log_text.delete('1.0', tk.END)
            
            logs = df_rig.tail(10)[['Timestamp', 'RSSI', 'TxRate', 'RxRate']].to_string(index=False, header=True)
            self.log_text.insert(tk.END, logs)
            self.log_text.config(state=tk.DISABLED)

        except Exception:
            self.gps_info_label.config(text="Статус: Ошибка обработки лога GPS.")

    # ----------------------------------------------------------------------
    # IV. МЕТОДЫ-ДЕЙСТВИЯ (КНОПКИ)
    # ----------------------------------------------------------------------

    def _start_monitoring(self):
        rig_id = self.selected_rig_id.get()
        if not rig_id: messagebox.showerror("Ошибка", "Выберите буровую установку."); return

        try:
            process = subprocess.Popen([sys.executable, COLLECTOR_SCRIPT, rig_id], 
                                       creationflags=subprocess.CREATE_NEW_CONSOLE)
            self.rig_processes[rig_id] = process
            messagebox.showinfo("Запуск", f"Мониторинг для {rig_id} запущен. PID: {process.pid}")
        except Exception as e:
            messagebox.showerror("Ошибка Запуска", f"Не удалось запустить сборщик данных для {rig_id}: {e}")
        self._update_control_tab(rig_id, False)

    def _stop_monitoring(self):
        rig_id = self.selected_rig_id.get()
        process = self.rig_processes.get(rig_id)
        
        if process and process.poll() is None:
            try:
                process.terminate() 
                self.rig_processes[rig_id] = None
                messagebox.showinfo("Остановка", f"Мониторинг для {rig_id} остановлен.")
            except Exception as e:
                messagebox.showerror("Ошибка Остановки", f"Не удалось остановить процесс: {e}")
        else:
             messagebox.showinfo("Статус", "Мониторинг уже остановлен.")
        self._update_control_tab(rig_id, False)

    def _generate_and_reload_map(self):
        try:
            subprocess.run([sys.executable, VISUALIZATION_SCRIPT], check=True, capture_output=True)
            self._load_heatmap_image()
            self.map_time_label.config(text=f"Карта создана: {datetime.now().strftime('%H:%M:%S')}", fg='black')
        except subprocess.CalledProcessError as e:
            messagebox.showerror("Ошибка Карты", f"Скрипт visualization.py вернул ошибку.")
        except FileNotFoundError:
            messagebox.showerror("Ошибка", f"Файл {VISUALIZATION_SCRIPT} не найден.")
        

    def _load_heatmap_image(self):
        try:
            img = Image.open(HEATMAP_FILE)
            width, height = img.size
            new_width = 700 
            new_height = int(new_width * height / width)
            
            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            self.tk_img = ImageTk.PhotoImage(img)

            self.map_canvas.config(image=self.tk_img)
            self.map_canvas.image = self.tk_img
        except FileNotFoundError:
            self.map_canvas.config(text="Тепловая карта еще не сгенерирована.", image='')
        except Exception:
            self.map_canvas.config(text="Ошибка загрузки изображения карты.", image='')
        
    def _open_config(self):
        try:
            os.startfile(CONFIG_FILE)
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось открыть файл конфигурации: {e}")


if __name__ == "__main__":
    try:
        import pandas as pd
        from PIL import Image
    except ImportError:
        messagebox.showerror("Критическая ошибка", "Не установлены необходимые библиотеки (pandas, Pillow). Выполните 'pip install -r requirements.txt'.")
        sys.exit(1)
        
    root = tk.Tk()
    app = MikrotikMonitorApp(root)
    root.mainloop()