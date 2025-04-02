#!/bin/bash

# Проверяем наличие файла 1CV8Clst.lst
if [ ! -f "1CV8Clst.lst" ]; then
    echo "❌ Ошибка: Файл 1CV8Clst.lst не найден в текущей директории!"
    exit 1
fi

echo "📋 Существующие папки из 1CV8Clst.lst (отсортировано по размеру ↓):"
echo "--------------------------------------------------"

# Обрабатываем файл и собираем данные
grep -P '^\{' 1CV8Clst.lst | while read -r line; do
    # Извлекаем имя папки (первый блок до запятой)
    folder_name=$(echo "$line" | grep -oP '^\{\K[^,]+')
    
    # Извлекаем описание (второй блок в кавычках)
    description=$(echo "$line" | grep -oP '^[^,]+\s*,\s*"\K[^"]+')
    
    # Проверяем существование папки
    if [ -d "$folder_name" ]; then
        # Получаем размер папки в удобном формате
        size=$(du -sh "$folder_name" 2>/dev/null | cut -f1)
        [ -z "$size" ] && size="0"  # Если ошибка доступа
        
        # Выводим для последующей сортировки
        echo "$size $folder_name \"$description\""
    fi
done | sort -hr | while read -r size folder desc; do
    # Форматируем вывод
    printf "%-40s %-10s %s\n" "$folder" "($size)" "$desc"
done

echo "--------------------------------------------------"
exit 0