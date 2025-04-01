#!/bin/bash
LC_ALL=C

# Засекаем время начала выполнения
START_TIME=$(date +%s.%N)
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Начало обработки логов..."

# Вычисляем количество рабочих ядер
WORKER_JOBS=$(( $(nproc) / 2 ))
(( WORKER_JOBS < 1 )) && WORKER_JOBS=1  # Не меньше 1

# Используем parallel для обработки
temp_file=$(mktemp)

# 1. Поиск и сбор данных
find . -type f -path "./*/*.log" -print0 | \
    parallel -0 -j $WORKER_JOBS "grep ',CALL,' {} | awk -v file={} '{print file \"|\" \$0}'" > "$temp_file"

DATA_COLLECTION_TIME=$(date +%s.%N)
echo "[$(date '+%H:%M:%S')] Сбор данных завершен. Обработано строк: $(wc -l < "$temp_file")"

# 2. Анализ данных
echo "[$(date '+%H:%M:%S')] Анализ данных..."
top_results=$(
    mawk -F'|' '
    {
        where = match($2, /Memory=[0-9]+/)
        if (where) {
            mem = substr($2, where+7, RLENGTH-7)+0
            if (mem > 0) {
                printf "%.2f:%d:%s:%s\n", mem/1048576, mem, $1, $2
            }
        }
    }' "$temp_file" | \
    sort -t':' -k2,2nr | \
    head -3
)

# 3. Вывод результатов
echo -e "\n=== Топ-3 максимальных значений Memory ==="
{
    echo "Рейтинг|Память (MB)|Память (байты)|Файл|Строка (первые 100 символов)"
    echo "-------|-----------|--------------|----|--------------------------"
    awk -F':' '{
        printf "%d|%.2f|%d|%s|%.100s\n", NR, $1, $2, $3, $4
    }' <<< "$top_results" | \
    column -t -s'|' -o ' | '
} | sed '2s/ /-/g'

# 4. Вывод полных строк
echo -e "\n=== Полное содержание строк ==="
counter=1
while IFS=':' read -r mem_mb mem_bytes source_file full_line; do
    echo "Место $counter:"
    echo "Файл:    $source_file"
    echo "Память:  $mem_mb MB ($mem_bytes bytes)"
    echo "Строка:  $full_line"
    echo ""
    ((counter++))
done <<< "$top_results"

# 5. Очистка
rm -f "$temp_file"

# Расчет времени выполнения
END_TIME=$(date +%s.%N)
TOTAL_TIME=$(echo "$END_TIME - $START_TIME" | bc)
DATA_TIME=$(echo "$DATA_COLLECTION_TIME - $START_TIME" | bc)
ANALYSIS_TIME=$(echo "$END_TIME - $DATA_COLLECTION_TIME" | bc)

echo -e "\n=== Статистика выполнения ==="
printf "Общее время работы:    %.2f секунд\n" $TOTAL_TIME
printf "Время сбора данных:    %.2f секунд (%.f%%)\n" $DATA_TIME $(echo "100*$DATA_TIME/$TOTAL_TIME" | bc)
printf "Время анализа:         %.2f секунд (%.f%%)\n" $ANALYSIS_TIME $(echo "100*$ANALYSIS_TIME/$TOTAL_TIME" | bc)
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Обработка завершена"