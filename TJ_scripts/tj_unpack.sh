#!/bin/bash

# Получаем количество доступных ядер
total_cores=$(nproc)
half_cores=$((total_cores / 2))
[[ $half_cores -lt 1 ]] && half_cores=1  # Минимум 1 ядро

echo "Используем $half_cores ядер из $total_cores доступных"

# Функция для отображения прогресса
progress() {
    local current=$1
    local total=$2
    local msg=$3
    local width=50
    local percent=$((current * 100 / total))
    local progress=$((current * width / total))
    
    printf "\r%s [" "$msg"
    printf "%0.s=" $(seq 1 $progress)
    [[ $progress -lt $width ]] && printf ">"
    printf "%0.s " $(seq $((progress + 1)) $width)
    printf "] %3d%%" "$percent"
}

# Шаг 1: Распаковка архивов
echo "Распаковка архивов *.tar.gz..."
archives=(*.tar.gz)
total_archives=${#archives[@]}
current=0
processed=0

for archive in "${archives[@]}"; do
    ((current++))
    progress $current $total_archives "Распаковка"
    
    # Распаковка в фоновом режиме
    tar -xzf "$archive" &
    
    # Ограничиваем количество параллельных процессов
    if [[ $(jobs -r -p | wc -l) -ge $half_cores ]]; then
        wait -n
        ((processed++))
    fi
done
wait
((processed += $(jobs -p | wc -l)))
printf "\nРаспаковано %d архивов.\n" "$processed"

# Шаг 2: Удаление маленьких файлов
echo "Поиск и удаление файлов меньше 10 байт..."
mapfile -t small_files < <(find . -type f -size -10c)
total_small=${#small_files[@]}
current=0

for file in "${small_files[@]}"; do
    ((current++))
    progress $current $total_small "Удаление малых файлов"
    rm -f "$file"
done
printf "\nУдалено %d файлов меньше 10 байт.\n" "$total_small"

# Шаг 3: Удаление пустых директорий
echo "Удаление пустых директорий..."
while IFS= read -r -d '' dir; do
    rmdir "$dir" 2>/dev/null
done < <(find . -type d -empty -print0)
empty_count=$(find . -type d -empty | wc -l)
printf "Осталось пустых директорий: %d\n" "$empty_count"

# Шаг 4: Удаление архивных файлов
echo "Удаление исходных архивов..."
archives_count=$(ls *.tar.gz 2>/dev/null | wc -l)
current=0

for archive in *.tar.gz; do
    ((current++))
    progress $current $archives_count "Удаление архивов"
    rm -f "$archive"
done
printf "\nУдалено %d архивных файлов.\n" "$archives_count"

echo "Все операции завершены успешно!"