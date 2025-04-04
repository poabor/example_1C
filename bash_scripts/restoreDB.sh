#!/bin/bash
export LANG=ru_RU.UTF-8
export LC_ALL=ru_RU.UTF-8
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

# Настройки логирования
LOG_FILE="/var/log/1c_restore.log"
MAX_LOG_SIZE=$((5*1024*1024))  # 5MB в байтах
LOG_LEVEL="INFO"               # Уровни: DEBUG, INFO, WARN, ERROR
LOG_TO_CONSOLE="false"         # Вывод в консоль (true/false)

# Создаем лог-файл если не существует
mkdir -p "$(dirname "$LOG_FILE")"
touch "$LOG_FILE"
chmod 644 "$LOG_FILE"

# Функция ротации логов
rotate_log() {
    if [ -f "$LOG_FILE" ] && [ $(stat -c%s "$LOG_FILE") -ge $MAX_LOG_SIZE ]; then
        local timestamp=$(date "+%Y%m%d_%H%M%S")
        mv "$LOG_FILE" "${LOG_FILE}.${timestamp}"
        echo "[$(date "+%Y-%m-%d %H:%M:%S")] [INFO] Ротация лога. Старый лог сохранен как ${LOG_FILE}.${timestamp}" > "$LOG_FILE"
    fi
}

# Улучшенная функция логирования
log() {
    local level=$1
    local message=$2
    local timestamp=$(date "+%Y-%m-%d %H:%M:%S")
    local log_entry="[$timestamp] [$level] $message"
    
    # Проверка уровня логирования
    case $LOG_LEVEL in
        "DEBUG") ;;
        "INFO")  [[ $level == "DEBUG" ]] && return ;;
        "WARN")  [[ $level == "DEBUG" || $level == "INFO" ]] && return ;;
        "ERROR") [[ $level != "ERROR" ]] && return ;;
    esac
    
    rotate_log
    echo "$log_entry" >> "$LOG_FILE" || echo "$log_entry" >&2
    
    [ "$LOG_TO_CONSOLE" = "true" ] && echo "$log_entry"
}

# Логируем начало выполнения
log "INFO" "=== Запуск скрипта $0 ==="
log "INFO" "Параметры: $@"

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
    log "ERROR" "Ошибка загрузки конфигурации"
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

# Вывод параметров конфигурации
log "INFO" "=== Параметры конфигурации ==="
log "INFO" "Сервер: $SERVER_NAME"
log "INFO" "Имя ИБ: $IB_NAME"
log "INFO" "Пользователь: $DB_USER"
log "INFO" "Исходная директория: $source_dir"
log "INFO" "Целевая директория: $target_dir"
[ -n "$PATH_1C" ] && log "INFO" "Путь к 1С: $PATH_1C"

# Проверка зависимостей
for cmd in rsync md5sum; do
    if ! command -v $cmd &>/dev/null; then
        log "ERROR" "Не установлена утилита: $cmd"
        exit 1
    fi
done

# Основная логика скрипта
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
mkdir -p "$target_dir"
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

# Загрузка в 1С
log "INFO" "Запуск 1C:Designer..."
"${PATH_1C:-/opt/1C/v8.3/x86_64}/1cv8" DESIGNER /S "$SERVER_NAME/$IB_NAME" /N"$DB_USER" /P"$DB_PASS" /RestoreIB "$target_dir/$filename"

if [ $? -eq 0 ]; then
    log "INFO" "1C:Designer завершил работу успешно"
    rm -f "$target_dir/$filename" && log "INFO" "Временный файл удален" || log "WARN" "Не удалось удалить временный файл"
else
    log "ERROR" "1C:Designer завершил работу с ошибкой (код: $?)"
    exit 1
fi

log "INFO" "=== Скрипт успешно завершен ==="