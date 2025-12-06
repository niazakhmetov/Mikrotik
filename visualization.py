import pandas as pd
import matplotlib.pyplot as plt

# ==============================================================================
# КОНФИГУРАЦИЯ ВИЗУАЛИЗАЦИИ
# ==============================================================================
CONFIG_VIS = {
    "CSV_FILE_PATH": "coverage_log.csv",
    "OUTPUT_IMAGE_PATH": "coverage_heatmap.png",
    
    # Цветовая шкала качества сигнала RSSI (в дБм)
    "RSSI_THRESHOLDS": {
        "Excellent (Зеленый)": -65, # RSSI > -65 дБм
        "Good (Желтый)": -75,      # -75 < RSSI <= -65 дБм
        "Poor (Красный)": -85       # -85 < RSSI <= -75 дБм
        # Все, что ниже -85, будет темно-красным/черным
    }
}

def define_quality_color(rssi):
    """Определяет цвет точки на основе уровня сигнала RSSI."""
    if rssi > CONFIG_VIS["RSSI_THRESHOLDS"]["Excellent (Зеленый)"]:
        return 'green'
    elif rssi > CONFIG_VIS["RSSI_THRESHOLDS"]["Good (Желтый)"]:
        return 'gold'
    elif rssi > CONFIG_VIS["RSSI_THRESHOLDS"]["Poor (Красный)"]:
        return 'red'
    else:
        return 'maroon' # Очень слабый сигнал

def generate_heatmap(data_path, output_path):
    """Читает данные и генерирует карту покрытия."""
    
    try:
        # 1. Загрузка данных
        df = pd.read_csv(data_path)
    except FileNotFoundError:
        print(f"Ошибка: Файл данных не найден по пути {data_path}. Сначала запустите data_collector.py.")
        return
    except pd.errors.EmptyDataError:
        print("Ошибка: Файл данных пуст. Сначала соберите данные.")
        return
    
    # Убедимся, что колонка RSSI имеет числовой формат
    df['RSSI'] = pd.to_numeric(df['RSSI'], errors='coerce')
    df.dropna(subset=['RSSI'], inplace=True)

    if df.empty:
        print("Нет корректных данных RSSI для построения карты.")
        return

    # 2. Определение цвета
    df['Color'] = df['RSSI'].apply(define_quality_color)
    
    # 3. Построение scatter plot (Карта Покрытия)
    plt.figure(figsize=(14, 10))
    
    # Настройка легенды для цветов
    legend_elements = [
        plt.scatter([], [], color='green', label=f'Отлично (> {CONFIG_VIS["RSSI_THRESHOLDS"]["Excellent (Зеленый)"]} дБм)'),
        plt.scatter([], [], color='gold', label=f'Хорошо ({CONFIG_VIS["RSSI_THRESHOLDS"]["Good (Желтый)"]} до {CONFIG_VIS["RSSI_THRESHOLDS"]["Excellent (Зеленый)"]} дБм)'),
        plt.scatter([], [], color='red', label=f'Низкое ({CONFIG_VIS["RSSI_THRESHOLDS"]["Poor (Красный)"]} до {CONFIGИГ_VIS["RSSI_THRESHOLDS"]["Good (Желтый)"]} дБм)'),
        plt.scatter([], [], color='maroon', label=f'Критическое (< {CONFIG_VIS["RSSI_THRESHOLDS"]["Poor (Красный)"]} дБм)'),
    ]

    # Строим точки: X=Longitude, Y=Latitude, цвет=RSSI
    plt.scatter(
        df['Longitude_X'], 
        df['Latitude_Y'], 
        c=df['Color'], 
        s=100,            # Увеличенный размер для видимости
        alpha=0.8,        # Прозрачность
        edgecolors='black', # Контур точки
        linewidths=0.5
    ) 

    plt.xlabel('Долгота (Longitude X)')
    plt.ylabel('Широта (Latitude Y)')
    plt.title(f'Карта Качества Wi-Fi в Карьере (Покрытие буровых установок) \n (Точек: {len(df)})')
    plt.legend(handles=legend_elements, loc='upper right', title="Качество сигнала RSSI")
    
    # Автоматическая настройка осей, чтобы показать все точки
    plt.autoscale(tight=True)
    plt.grid(True, linestyle='--', alpha=0.6)
    
    # 4. Сохранение результата
    plt.savefig(output_path)
    print(f"\n✅ Карта покрытия успешно сохранена: {output_path}")

if __name__ == "__main__":
    generate_heatmap(CONFIG_VIS["CSV_FILE_PATH"], CONFIG_VIS["OUTPUT_IMAGE_PATH"])
