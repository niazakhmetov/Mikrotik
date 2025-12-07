import pandas as pd
import matplotlib.pyplot as plt
import os
from datetime import datetime, timedelta
import json

# --- Файлы проекта ---
CONFIG_FILE = 'config.json'
DATA_PATH = 'coverage_log.csv'
OUTPUT_IMAGE_PATH = 'coverage_heatmap.png'

# ==============================================================================
# КОНФИГУРАЦИЯ И УТИЛИТЫ
# ==============================================================================

# Цветовая шкала качества сигнала RSSI (в дБм)
RSSI_THRESHOLDS = {
    "Excellent (Зеленый)": -65, 
    "Good (Желтый)": -75,      
    "Poor (Красный)": -85       
}

def define_quality_color(rssi):
    """Определяет цвет точки на основе уровня сигнала RSSI."""
    if rssi > RSSI_THRESHOLDS["Excellent (Зеленый)"]:
        return 'green'
    elif rssi > RSSI_THRESHOLDS["Good (Желтый)"]:
        return 'gold'
    elif rssi > RSSI_THRESHOLDS["Poor (Красный)"]:
        return 'red'
    else:
        return 'maroon' # Очень слабый сигнал

def get_current_shift_period():
    """Определяет временной диапазон текущей смены."""
    now = datetime.now()
    
    shift2_start = now.replace(hour=8, minute=0, second=0, microsecond=0)
    shift2_end = now.replace(hour=20, minute=0, second=0, microsecond=0)
    
    if now >= shift2_start and now < shift2_end:
        # Дневная смена
        start_time = shift2_start
        end_time = shift2_end
        shift_info = "Дневная Смена (08:00 - 20:00)"
    else:
        if now >= shift2_end:
            # Ночная смена (началась сегодня)
            start_time = shift2_end
            end_time = (now + timedelta(days=1)).replace(hour=8, minute=0, second=0, microsecond=0)
        else:
            # Ночная смена (началась вчера)
            start_time = (now - timedelta(days=1)).replace(hour=20, minute=0, second=0, microsecond=0)
            end_time = shift2_start
        
        shift_info = "Ночная Смена (20:00 - 08:00)"

    return start_time, end_time, shift_info

# ==============================================================================
# ОСНОВНАЯ ФУНКЦИЯ ГЕНЕРАЦИИ КАРТЫ
# ==============================================================================

def generate_heatmap():
    """Читает данные, фильтрует по текущей смене и генерирует карту покрытия."""
    
    start_time, end_time, shift_info = get_current_shift_period()

    try:
        df = pd.read_csv(DATA_PATH)
    except FileNotFoundError:
        print(f"Ошибка: Файл данных не найден по пути {DATA_PATH}.")
        return
    except pd.errors.EmptyDataError:
        print("Ошибка: Файл данных пуст.")
        return
    
    df['RSSI'] = pd.to_numeric(df['RSSI'], errors='coerce')
    df['Timestamp'] = pd.to_datetime(df['Timestamp'])
    df.dropna(subset=['RSSI', 'Timestamp'], inplace=True)

    # 1. Фильтрация данных по текущей смене
    df_filtered = df[(df['Timestamp'] >= start_time) & (df['Timestamp'] < end_time)]

    if df_filtered.empty:
        print(f"Нет данных для текущей смены ({shift_info}).")
        # Создаем заглушку, чтобы GUI не ругался на отсутствие файла
        plt.figure(figsize=(10, 8))
        plt.text(0.5, 0.5, f"НЕТ ДАННЫХ ДЛЯ {shift_info}", ha='center', va='center', fontsize=16)
        plt.title("Карта Покрытия (Нет данных)", fontsize=18)
        plt.savefig(OUTPUT_IMAGE_PATH)
        return

    # 2. Определение цвета
    df_filtered['Color'] = df_filtered['RSSI'].apply(define_quality_color)
    
    # 3. Построение scatter plot
    plt.figure(figsize=(14, 10))
    
    legend_elements = [
        plt.scatter([], [], color='green', label=f'Отлично (> {RSSI_THRESHOLDS["Excellent (Зеленый)"]} дБм)'),
        plt.scatter([], [], color='gold', label=f'Хорошо ({RSSI_THRESHOLDS["Good (Желтый)"]} до {RSSI_THRESHOLDS["Excellent (Зеленый)"]} дБм)'),
        plt.scatter([], [], color='red', label=f'Низкое ({RSSI_THRESHOLDS["Poor (Красный)"]} до {RSSI_THRESHOLDS["Good (Желтый)"]} дБм)'),
        plt.scatter([], [], color='maroon', label=f'Критическое (< {RSSI_THRESHOLDS["Poor (Красный)"]} дБм)'),
    ]

    plt.scatter(
        df_filtered['Longitude_X'], 
        df_filtered['Latitude_Y'], 
        c=df_filtered['Color'], 
        s=100,            
        alpha=0.8,        
        edgecolors='black', 
        linewidths=0.5
    ) 

    plt.xlabel('Долгота (Longitude X)')
    plt.ylabel('Широта (Latitude Y)')
    plt.title(f'Карта Качества Wi-Fi в Карьере ({shift_info}) \n (Точек: {len(df_filtered)})')
    plt.legend(handles=legend_elements, loc='upper right', title="Качество сигнала RSSI")
    
    plt.autoscale(tight=True)
    plt.grid(True, linestyle='--', alpha=0.6)
    
    # 4. Сохранение результата
    plt.savefig(OUTPUT_IMAGE_PATH)
    print(f"Карта успешно сохранена: {OUTPUT_IMAGE_PATH} (Данные за {shift_info})")

if __name__ == "__main__":
    generate_heatmap()