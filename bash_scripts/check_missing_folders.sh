#!/bin/bash

# Проверяем наличие файла 1CV8Clst.lst
if [ ! -f "1CV8Clst.lst" ]; then
    echo "❌ Ошибка: Файл 1CV8Clst.lst не найден в текущей директории!"
    exit 1
fi

# Получаем список папок в текущей директории (кроме скрытых и ./ ../)
existing_folders=$(find . -maxdepth 1 -type d ! -name '.' ! -name '.*' -printf '%f\n' | sort)

# Извлекаем имена папок из 1CV8Clst.lst (игнорируя { в начале и всё после первой запятой)
listed_folders=$(grep -oP '^\{\K[^,]+' 1CV8Clst.lst | sort -u)

# Фильтруем папки по правилам: 5 блоков с "-" и не начинаются на "snccntx"
valid_folders=$(echo "$existing_folders" | grep -P '^[^-]+-[^-]+-[^-]+-[^-]+-[^-]+$' | grep -v '^snccntx')

# Находим папки, которых нет в 1CV8Clst.lst
missing_folders=$(comm -23 <(echo "$valid_folders") <(echo "$listed_folders"))

# Создаём временный файл для хранения данных о размерах папок
temp_file=$(mktemp)

# Собираем данные о размерах отсутствующих папок
total_size=0
for folder in $missing_folders; do
    if [ -d "$folder" ]; then
        # Получаем размер папки в байтах
        size_bytes=$(du -sb "$folder" | cut -f1)
        # Конвертируем в удобочитаемый формат
        size_human=$(du -sh "$folder" | cut -f1)
        # Записываем в временный файл (размер в байтах + данные для вывода)
        echo "$size_bytes $size_human $folder" >> "$temp_file"
        # Суммируем общий размер
        total_size=$((total_size + size_bytes))
    fi
done

if [ -z "$missing_folders" ]; then
    echo "✅ Все папки (соответствующие правилам) присутствуют в 1CV8Clst.lst."
    rm -f "$temp_file"
    exit 0
fi

echo "📂 Папки, отсутствующие в 1CV8Clst.lst (отсортировано по размеру ↓):"
echo "----------------------------------------"

# Сортируем по размеру (по убыванию) и выводим результат
sort -rn "$temp_file" | while read -r size_bytes size_human folder; do
    # Проверяем второй блок для этой папки
    second_block=$(grep -oP "^\{$folder,\s*\"\K[^\"]+" 1CV8Clst.lst | head -1)
    if [ -n "$second_block" ]; then
        echo "➖ $folder (размер: $size_human) → второй блок: \"$second_block\""
    else
        echo "➖ $folder (размер: $size_human)"
    fi
done

echo "----------------------------------------"

# Конвертируем общий размер в удобочитаемый вид
if [ $total_size -ge 1073741824 ]; then  # Если больше 1 ГБ
    total_size_human=$(awk "BEGIN {printf \"%.2f GБ\", $total_size/1073741824}")
elif [ $total_size -ge 1048576 ]; then  # Если больше 1 МБ
    total_size_human=$(awk "BEGIN {printf \"%.2f MБ\", $total_size/1048576}")
elif [ $total_size -ge 1024 ]; then     # Если больше 1 КБ
    total_size_human=$(awk "BEGIN {printf \"%.2f KБ\", $total_size/1024}")
else
    total_size_human="$total_size Б"
fi

echo "📊 Общий размер отсутствующих папок: $total_size_human"
echo "🔢 Всего отсутствует в списке: $(echo "$missing_folders" | wc -l) папок."

# Удаляем временный файл
rm -f "$temp_file"

# read -p "Удалить эти папки и освободить $total_size_human? (y/N) " answer
if [[ "$answer" =~ [yY] ]]; then
    echo "Удаление..."
    rm -rf $missing_folders
