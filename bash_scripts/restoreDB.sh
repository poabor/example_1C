#!/bin/bash
export LANG=ru_RU.UTF-8
export LC_ALL=ru_RU.UTF-8
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export DISPLAY=":0.0"
export XAUTHORITY=/tmp/.Xauthority

PATH_1C="/opt/1cv8/x86_64/8.3.27.1606"
# =============================================
# НАСТРОЙКИ ЛОГИРОВАНИЯ
# =============================================
LOG_FILE="$HOME/logs/1c_restore.log"
LOG_FILE_1C="$HOME/logs/1c_restore_1c.log"
MAX_LOG_SIZE=$((5*1024*1024))  # 5MB
LOG_LEVEL="DEBUG"               # DEBUG, INFO, WARN, ERROR
MAX_LOG_BACKUPS=3              # Количество бэкапов

# =============================================
# ФУНКЦИИ (ОБНОВЛЕННЫЕ)
# =============================================

safe_log_init() {
    # Создаем директорию логов если нет
    mkdir -p "$(dirname "$LOG_FILE")" || {
        echo "Ошибка создания директории логов" >&2
        exit 1
    }
    
    # Инициализация только если файл не существует
    [ -f "$LOG_FILE" ] || { 
        touch "$LOG_FILE" && chmod 644 "$LOG_FILE"
    }
    
    # Добавляем разделитель только если файл не пустой
    [ -s "$LOG_FILE" ] && echo -e "\n" >> "$LOG_FILE"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] === НОВЫЙ ЗАПУСК ===" >> "$LOG_FILE"

    # Инициализация только если файл не существует
    [ -f "$LOG_FILE_1C" ] || { 
        touch "$LOG_FILE_1C" && chmod 644 "$LOG_FILE_1C"
    }
    
    # Добавляем разделитель только если файл не пустой
    [ -s "$LOG_FILE_1C" ] && echo -e "\n" >> "$LOG_FILE_1C"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] === НОВЫЙ ЗАПУСК ===" >> "$LOG_FILE_1C"

}

rotate_logs() {
    [ -f "$LOG_FILE" ] || return
    
    local size=$(stat -c%s "$LOG_FILE")
    [ $size -lt $MAX_LOG_SIZE ] && return
    
    # Ротация бэкапов
    for i in $(seq $MAX_LOG_BACKUPS -1 1); do
        [ -f "${LOG_FILE}.$i" ] && mv "${LOG_FILE}.$i" "${LOG_FILE}.$((i+1))"
    done
    mv "$LOG_FILE" "${LOG_FILE}.1"
    
    # Новый лог-файл
    touch "$LOG_FILE"
    chmod 644 "$LOG_FILE"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Лог пересоздан после ротации" >> "$LOG_FILE"
}

log() {
    local level=$1 msg=$2
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    local entry="[$timestamp] [$level] $msg"
    
    # Фильтр по уровню
    case $LOG_LEVEL in
        "DEBUG") ;;
        "INFO")  [[ $level == "DEBUG" ]] && return ;;
        "WARN")  [[ $level == "DEBUG" || $level == "INFO" ]] && return ;;
        "ERROR") [[ $level != "ERROR" ]] && return ;;
    esac
    
    rotate_logs
    echo "$entry" >> "$LOG_FILE"  # Только добавление в конец
}

# =============================================
# ИНИЦИАЛИЗАЦИЯ ЛОГА (КРИТИЧНО ВАЖНЫЙ БЛОК)
# =============================================

# Отключаем стандартные перенаправления при работе через cron
if [ -t 1 ]; then
    # Режим терминала - выводим в консоль
    exec 3>&1
else
    # Режим cron - перенаправляем только в файл
    exec 3>/dev/null
fi

# Инициализация лога (гарантированно не перезаписывает)
safe_log_init

# Перенаправляем весь вывод в лог-файл
exec >> "$LOG_FILE" 2>&1

# =============================================
# ОСНОВНОЙ КОД СКРИПТА (БЕЗ ИЗМЕНЕНИЙ)
# =============================================
log "INFO" "Запуск скрипта $0 с параметрами: $*"

# Парсинг аргументов
CONFIG_FILE=""
while getopts ":c:-:" opt; do
    case $opt in
        c) CONFIG_FILE="$OPTARG" ;;
        -) 
            case "${OPTARG}" in
                config=*) CONFIG_FILE="${OPTARG#*=}" ;;
                *) log "ERROR" "Неизвестный аргумент --${OPTARG}"; exit 1 ;;
            esac
        ;;
        \?) log "ERROR" "Неверный ключ: -$OPTARG"; exit 1 ;;
        :) log "ERROR" "Ключ -$OPTARG требует аргумент."; exit 1 ;;
    esac
done

# Проверка конфигурационного файла
if [ -z "$CONFIG_FILE" ]; then
    log "ERROR" "Файл конфигурации не указан"
    echo "Примеры:"
    echo "  $0 -c <config_file>"
    echo "  $0 --config=<config_file>"
    exit 1
fi

if [ ! -f "$CONFIG_FILE" ]; then
    log "ERROR" "Файл конфигурации '$CONFIG_FILE' не найден!"
    exit 1
fi

# Загрузка конфигурации
log "INFO" "Загрузка конфигурации из $CONFIG_FILE"
source "$CONFIG_FILE" || {
    log "ERROR" "Ошибка при загрузке конфигурации"
    exit 1
}

# Проверка обязательных параметров
required_vars=("SERVER_NAME" "IB_NAME" "DB_USER" "DB_PASS" "source_dir" "target_dir")
for var in "${required_vars[@]}"; do
    if [ -z "${!var}" ]; then
        log "ERROR" "Не задана обязательная переменная: $var"
        exit 1
    fi
done

# Логирование параметров
log "INFO" "=== Параметры конфигурации ==="
log "INFO" "Сервер: $SERVER_NAME"
log "INFO" "Имя ИБ: $IB_NAME"
log "INFO" "Исходная директория: $source_dir"
log "INFO" "Целевая директория: $target_dir"
[ -n "$PATH_1C" ] && log "INFO" "Путь к 1С: $PATH_1C"

# Проверка зависимостей
for cmd in rsync md5sum; do
    command -v "$cmd" &>/dev/null || {
        log "ERROR" "Не установлена утилита: $cmd"
        exit 1
    }
done

# Поиск самого нового .dt файла
log "INFO" "Поиск самого нового .dt файла в $source_dir"
youngest_file=$(find "$source_dir" -maxdepth 1 -type f -name "*.dt" -printf "%T@ %p\n" | sort -n | tail -1 | cut -d' ' -f2-)

if [ -z "$youngest_file" ]; then
    log "INFO" "Файлы .dt не найдены"
    exit 0
fi

filename=$(basename "$youngest_file")
file_size=$(du -h "$youngest_file" | cut -f1)

log "INFO" "Найден файл: $filename (Размер: $file_size)"
log "INFO" "Вычисление контрольной суммы..."
src_checksum=$(md5sum "$youngest_file" | awk '{print $1}')
log "INFO" "MD5: $src_checksum"

# Копирование файла
mkdir -p "$target_dir" || {
    log "ERROR" "Ошибка создания целевой директории"
    exit 1
}

log "INFO" "Копирование в $target_dir..."
rsync -ah --info=progress2 "$youngest_file" "$target_dir/" || {
    log "ERROR" "Ошибка копирования"
    exit 1
}

# Проверка целостности
dest_checksum=$(md5sum "$target_dir/$filename" | awk '{print $1}')
if [ "$src_checksum" != "$dest_checksum" ]; then
    log "ERROR" "Контрольные суммы не совпадают!"
    log "INFO" "Исходная: $src_checksum"
    log "INFO" "Копия: $dest_checksum"
    exit 1
fi

# set -x
# xhost
# Загрузка в 1С
log "INFO" "Запуск 1C:Designer..."
"$PATH_1C/1cv8" DESIGNER /S "$SERVER_NAME/$IB_NAME" /N"$DB_USER" /P"$DB_PASS" /Out "$LOG_FILE_1C" /RestoreIB "$target_dir/$filename"
# set +x

if [ $? -eq 0 ]; then
    log "INFO" "1C:Designer завершил работу успешно"
    log "INFO" "файл: $filename (Размер: $file_size) загружен"
    rm -f "$target_dir/$filename" && log "INFO" "dt файл удален" || log "WARN" "Не удалось удалить dt файл"
else
    log "ERROR" "1C:Designer завершил работу с ошибкой (код: $?)"
    exit 1
fi

log "INFO" "=== Скрипт успешно завершен ==="
exit 0