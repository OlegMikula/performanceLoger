# Performance Logger — моніторинг навантаження процесів

Збирає статистику по CPU та пам'яті для вказаних процесів і зберігає її в CSV.

## Встановлення

```bash
pip install -r requirements.txt
```

## Запуск

**Моніторинг до ручної зупинки (Ctrl+C):**
```bash
python monitor.py -p "chrome.exe,Code.exe"
```

**Моніторинг протягом 60 секунд:**
```bash
python monitor.py -p "chrome.exe" -d 60
```

**Інтервал збору 2 секунди, свій файл виводу:**
```bash
python monitor.py -p "notepad.exe" -i 2 -o my_log.csv
```

### Параметри

| Параметр | Опис |
|----------|------|
| `-p`, `--processes` | Імена процесів через кому (наприклад: `chrome.exe`, `Code.exe`) |
| `-i`, `--interval` | Інтервал збору в секундах (за замовчуванням: 1) |
| `-d`, `--duration` | Тривалість у секундах; якщо не вказано — до Ctrl+C |
| `-o`, `--output` | Шлях до CSV-файлу (за замовчуванням: `performance_log_YYYYMMDD_HHMMSS.csv`) |

## Формат CSV

| Колонка | Опис |
|---------|------|
| timestamp | Час знімка |
| pid | ID процесу (корисно, якщо процес завершився — видно до якого моменту були дані) |
| process_name | Ім'я процесу |
| memory_mb | Пам'ять у МБ |
| cpu_percent | Навантаження CPU у відсотках |
| status | `running` або `exited` (запис про завершення процесу) |

## Графіки (plot_csv.py)

Побудова графіків з CSV: один файл — один графік; два і більше — порівняльний графік (часу від початку по осі X).

**Один CSV (звичайний графік):**
```bash
python plot_csv.py log.csv -o chart.png
```

**Декілька CSV (порівняння):**
```bash
python plot_csv.py run1.csv run2.csv run3.csv -o compare.png
```

**Метрика:** `-m memory` (за замовчуванням), `-m cpu` або `-m both` (два графіки — пам'ять і CPU).

**Без `-o`** — графік відкриється у вікні (plt.show()).
