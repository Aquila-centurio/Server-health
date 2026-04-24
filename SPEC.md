# ТЗ — srvwatch

> Терминальный дашборд состояния удалённого сервера в реальном времени.

---

## Суть

Одна команда — один IP — живой экран с метриками и историей.

```bash
srvwatch 192.168.1.10
srvwatch myhost.example.com -u root -p 2222 -i 5
```

---

## Интерфейс командной строки

```
srvwatch HOST [OPTIONS]

Позиционные аргументы:
  HOST                IP-адрес или hostname удалённого сервера

Опции:
  -u, --user USER     SSH-пользователь (по умолчанию: текущий / ~/.ssh/config)
  -p, --port PORT     SSH-порт (по умолчанию: 22)
  -i, --interval SEC  Интервал обновления в секундах (по умолчанию: 3)
  -n, --count N       Завершить после N сэмплов (по умолчанию: 0 = бесконечно)
```

---

## Как работает сбор данных

### Транспорт

- Подключение через **системный бинарник `ssh`** (subprocess, не paramiko)
- Использует существующий `~/.ssh/config` и SSH-ключи — никакой дополнительной настройки
- Скрипт передаётся на удалённый хост через **stdin** — никаких файлов не пишется, никакой агент не устанавливается

### Стратегия автодетекта (приоритет → фоллбэк)

```
1. python3 доступен на хосте?
   └── ДА  → запускаем inline Python-скрипт
   └── НЕТ → запускаем pure bash-скрипт

Оба возвращают одну строку JSON.
```

**Dispatcher (отправляется на хост):**
```bash
if command -v python3 >/dev/null 2>&1; then
    python3 - <<'PYEOF'
    # python script
    PYEOF
else
    bash -s <<'BASHEOF'
    # bash fallback
    BASHEOF
fi
```

### Что читает Python-скрипт

| Метрика | Источник | Примечание |
|---------|----------|------------|
| CPU % | `/proc/stat` | Дельта между двумя чтениями с паузой 0.5с |
| RAM | `/proc/meminfo` | Использовать `MemAvailable`, не `MemFree` |
| Disk | `shutil.disk_usage("/")` | Только `/` |
| Load avg | `/proc/loadavg` | 1/5/15 минут |
| Uptime | `/proc/uptime` | Форматировать как `14d 3h 22m` |
| ОС | `/etc/os-release` | `PRETTY_NAME`, фоллбэк на `NAME` |
| Kernel | `platform.release()` | |

### Что читает Bash-скрипт (фоллбэк)

То же самое, но через `awk`, `grep`, `uname -r`, `df -B1`.

CPU: два чтения `/proc/stat` с `sleep 1` между ними, дельта считается через `awk`.

### Формат ответа

Одна строка JSON, одинаковая для обоих вариантов:

```json
{
  "cpu": 58.5,
  "mem_total": 8589934592,
  "mem_used": 4294967296,
  "disk_total": 408021073920,
  "disk_used": 115964116992,
  "load_avg": [1.42, 0.98, 0.81],
  "uptime": "14d 3h 22m",
  "os": "Ubuntu 22.04.3 LTS",
  "kernel": "5.15.0-91-generic",
  "collector": "python3"
}
```

Поле `collector` — `"python3"` или `"bash"`, отображается в шапке дашборда.

---

## Отображение (Rich TUI)

Полноэкранный live-режим (`rich.live.Live`, `screen=True`).

### Шапка

```
 192.168.1.10  │  Ubuntu 22.04.3 LTS  │  kernel: 5.15.0-91-generic  │  uptime: 14d 3h 22m  │  py
```

- IP/hostname жирным цианом
- `py` (циан) если собрано через python3, `sh` (жёлтый) если через bash

### Таблица метрик (3 строки: CPU, RAM, DISK)

| Колонка | Содержимое |
|---------|------------|
| Название | `CPU` / `RAM` / `DISK` |
| Прогресс-бар | `[████████░░░░░░░░]`, ширина 24 символа |
| Цвет бара | зелёный < 70%, жёлтый < 90%, красный ≥ 90% |
| Процент | `58.5%` в цвете бара |
| Значения | CPU: `load: 1.42  0.98  0.81` / RAM: `5.8 GB / 8.0 GB` / Disk: `108.0 GB / 380.0 GB` |
| Sparkline | `▁▂▃▄▅▆▇█` — история за последние 60 сэмплов |

### Футер

```
  refresh: 3s  │  samples: 47  │  q / Ctrl+C to quit
```

### Обработка ошибок

Если SSH упал — TUI не падает, показывает ошибку прямо в интерфейсе:

```
╭─ Error ─────────────────────────────────────╮
│  Cannot connect to host.                    │
│  Connection timed out (15s)                 │
╰─────────────────────────────────────────────╯
```

---

## Структура проекта

```
srvwatch/
├── srvwatch/
│   ├── __init__.py       # версия пакета
│   ├── main.py           # argparse CLI + главный цикл
│   ├── collector.py      # SSH-сбор, dispatcher py/bash, датакласс HostMetrics
│   ├── display.py        # Rich layout, рендер, цвета
│   └── history.py        # кольцевой буфер (60 сэмплов) + sparkline
├── pyproject.toml        # pip-устанавливаемый пакет
├── README.md             # описание, установка, ASCII-скриншот
└── .gitignore
```

---

## Зависимости

| | |
|-|---|
| Внешние | `rich >= 13.0` — единственная зависимость |
| Python | >= 3.9 |
| Система | `ssh` в PATH, настроенные ключи |
| Удалённый хост | Любой Linux с `/proc` и bash. Python3 опционален |

---

## Установка

```bash
# Из PyPI (когда будет опубликован)
pip install srvwatch

# Из исходников
git clone https://github.com/yourname/srvwatch
cd srvwatch
pip install -e .
```

Entry point: `srvwatch = srvwatch.main:main`

---

## Жёсткие ограничения

- CPU % — **только дельта** между двумя чтениями `/proc/stat`, никаких моментальных снимков
- RAM — **только `MemAvailable`**, не `MemFree`
- SSH-ошибки — **не падать**, показывать в TUI
- Никаких файлов на удалённом хосте, никаких агентов
- Одна внешняя зависимость: **`rich`**