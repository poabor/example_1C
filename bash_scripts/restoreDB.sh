#!/bin/bash

# Настройки логирования
log_name=$(echo ${1%.*}.log | sed 's/.*=//') # Лог будет с тем же именем, что и первый аргумент, но с расширением .log
LOG_FILE=$log_name  
MAX_LOG_SIZE=1048576    # Максимальный размер лога (1MB)
LOG_LEVEL="INFO"        # Уровень логирования (DEBUG, INFO, WARN, ERROR)

# Функция для ротации логов
rotate_log() {
    if [ -f "$LOG_FILE" ] && [ $(stat -c%s "$LOG_FILE") -ge $MAX_LOG_SIZE ]; then
        mv "$LOG_FILE" "${LOG_FILE}.old"
        echo "[$(date "+%Y-%m-%d %H:%M:%S")] [INFO] Лог переименован в ${LOG_FILE}.old" >> "${LOG_FILE}.old"
    fi
}

# Функция логирования
log() {
    local level=$1
    local message=$2
    local timestamp=$(date "+%Y-%m-%d %H:%M:%S")

    # Проверка уровня логирования
    case $LOG_LEVEL in
        "DEBUG") ;;
        "INFO")  [[ $level == "DEBUG" ]] && return ;;
        "WARN")  [[ $level == "DEBUG" || $level == "INFO" ]] && return ;;
        "ERROR") [[ $level != "ERROR" ]] && return ;;
        *)       LOG_LEVEL="INFO" ;;
    esac

    rotate_log
    echo "[$timestamp] [$level] $message" | tee -a "$LOG_FILE"
}

log "INFO" "Запуск скрипта $0 с параметрами: $@"

CONFIG_FILE=""

# Парсинг аргументов
while getopts ":c:-:" opt; do
    case $opt in
        c) 
            CONFIG_FILE="$OPTARG"
            log "DEBUG" "Найден параметр -c с значением $CONFIG_FILE"
            ;;
        -) 
            case "${OPTARG}" in
                config=*) 
                    CONFIG_FILE="${OPTARG#*=}"
                    log "DEBUG" "Найден параметр --config со значением $CONFIG_FILE"
                    ;;
                *) 
                    log "ERROR" "Неизвестный аргумент --${OPTARG}"
                    exit 1 
                    ;;
            esac
        ;;
        \?) 
            log "ERROR" "Неверный ключ: -$OPTARG"
            exit 1 
            ;;
        :) 
            log "ERROR" "Ключ -$OPTARG требует аргумент."
            exit 1 
            ;;
    esac
done

# Проверка, указан ли файл
if [ -z "$CONFIG_FILE" ]; then
    log "ERROR" "Файл конфигурации не указан"
    echo "Примеры:"
    echo "  $0 -c <config_file>"
    echo "  $0 --config=<config_file>"
    exit 1
fi

# Проверка существования файла
if [ ! -f "$CONFIG_FILE" ]; then
    log "ERROR" "Файл конфигурации '$CONFIG_FILE' не найден!"
    exit 1
fi

# Загрузка конфига
log "INFO" "Загрузка конфигурации из файла $CONFIG_FILE"
if ! source "$CONFIG_FILE"; then
    log "ERROR" "Ошибка при загрузке конфигурации из $CONFIG_FILE"
    exit 1
fi

# Проверка обязательных переменных
required_vars=("SERVER_NAME" "IB_NAME" "DB_USER" "DB_PASS")
for var in "${required_vars[@]}"; do
    if [ -z "${!var}" ]; then
        log "ERROR" "Не задана обязательная переменная: $var"
        exit 1
    fi
done

# Проверяем, установлен ли rsync
if ! command -v rsync &> /dev/null; then
    echo "Ошибка: rsync не установлен. Установите его командой:"
    echo "sudo apt install rsync  # для Linux Mint/Debian"
    exit 1
fi

log "INFO" "Запуск вычисление хэш суммы"
# Проверяем существование исходной директории
if [ ! -d "$source_dir" ]; then
    log "ERROR" "Ошибка: исходная директория '$source_dir' не существует"
    exit 1
fi

# Создаём целевую директорию (если её нет)
if [ ! -d "$target_dir" ]; then
    if ! mkdir -p "$target_dir"; then
        log "ERROR" "Ошибка: не удалось создать целевую директорию '$target_dir'"
        exit 1
    fi
fi

# Находим самый новый файл (исключая поддиректории)
youngest_file=$(find "$source_dir" -maxdepth 1 -type f -name "*.dt" -printf "%T@ %p\n" | sort -n | tail -1 | cut -d' ' -f2-)

# Проверяем, найден ли файл
if [ -z "$youngest_file" ]; then
    log "INFO" "В исходной директории нет файлов для копирования"
    exit 0
fi

filename=$(basename "$youngest_file")

# Вычисляем контрольную сумму исходного файла
log "INFO" "\n[1/4] Вычисляем контрольную сумму исходного файла..."
src_checksum=$(md5sum "$youngest_file" | awk '{print $1}')
log "INFO" "MD5 исходного файла: $src_checksum"

# Копируем с помощью rsync
log "INFO" "\n[2/4] Копируем файл '$filename' в '$target_dir'..."
if ! rsync -ah --info=progress2 "$youngest_file" "$target_dir/"; then
    log "ERROR" "Ошибка: не удалось скопировать файл '$filename' в '$target_dir'"
    exit 1
fi

# Проверяем контрольную сумму
log "INFO" "\n[3/4] Проверяем целостность копии..."
dest_checksum=$(md5sum "$target_dir/$filename" | awk '{print $1}')
log "INFO" "MD5 скопированного файла: $dest_checksum"

# Сравниваем хеши
if [ "$src_checksum" != "$dest_checksum" ]; then
    log "ERROR" "\nОШИБКА: контрольные суммы не совпадают!"
    log "INFO" "Исходная MD5: $src_checksum"
    log "INFO" "Скопированная MD5: $dest_checksum"
    exit 1
fi

log "INFO" "Запуск 1C:Предприятие с параметрами:"
log "INFO" "Сервер: $SERVER_NAME"
log "INFO" "Имя ИБ: $IB_NAME"
log "INFO" "Пользователь: $DB_USER"

# Запуск 1С:Предприятие
log "INFO" "Запуск 1C:Designer..."
$PATH_1C/1cv8 DESIGNER /S "$SERVER_NAME/$IB_NAME" /N"$DB_USER" /P"$DB_PASS" /RestoreIB $target_dir/$filename

if [ $? -eq 0 ]; then
    log "INFO" "1C:Designer завершил работу успешно"
else
    log "ERROR" "1C:Designer завершил работу с ошибкой (код: $?)"
fi

log "INFO" "загрузка завершена"