import os
import hashlib
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import multiprocessing
from fnmatch import fnmatch
import threading
import time

current_file = ""
current_file_lock = threading.Lock()
processing_done = False
processed_files = 0
total_files = 0

def format_size(size_bytes):
    """Форматирует размер файла в МБ с 2 знаками после запятой"""
    return f"{size_bytes / (1024 * 1024):.2f} МБ"

def get_file_info(file_path, block_size=65536):
    """Возвращает (размер, хэш, имя файла, путь)"""
    global current_file
    with current_file_lock:
        current_file = file_path
    
    try:
        # Для symlinks получаем информацию о конечном файле
        if os.path.islink(file_path):
            real_path = os.path.realpath(file_path)
            file_size = os.path.getsize(real_path)
        else:
            file_size = os.path.getsize(file_path)
            
        file_name = os.path.basename(file_path)
        md5 = hashlib.md5()
        with open(file_path, 'rb') as f:
            for block in iter(lambda: f.read(block_size), b''):
                md5.update(block)
        return (file_size, md5.hexdigest(), file_name, file_path)
    except (IOError, PermissionError, OSError) as e:
        return (None, None, None, file_path)
    finally:
        global processed_files
        processed_files += 1
        with current_file_lock:
            if current_file == file_path:
                current_file = ""

def scan_directory(directory, exclude_patterns=None, min_size=None, max_size=None, follow_symlinks=False):
    if exclude_patterns is None:
        exclude_patterns = []
    
    files = []
    for root, dirs, filenames in os.walk(directory):
        # Исключаем директории, начинающиеся с точки
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        
        for filename in filenames:
            file_path = os.path.join(root, filename)
            
            # Пропускаем символические ссылки (если не включена опция follow_symlinks)
            if not follow_symlinks and os.path.islink(file_path):
                continue
                
            # Проверка исключений по маске
            if any(fnmatch(filename, pattern) for pattern in exclude_patterns):
                continue
                
            # Проверка размера файла
            try:
                if os.path.islink(file_path):
                    real_path = os.path.realpath(file_path)
                    file_size = os.path.getsize(real_path)
                else:
                    file_size = os.path.getsize(file_path)
                    
                if min_size is not None and file_size < min_size:
                    continue
                if max_size is not None and file_size > max_size:
                    continue
                files.append(file_path)
            except OSError:
                continue
                
    return files

def print_progress():
    """Выводит текущий прогресс обработки"""
    global current_file, processing_done, processed_files, total_files
    while not processing_done:
        with current_file_lock:
            progress = f"{processed_files}/{total_files}"
            current = f" | Обрабатывается: {current_file[:80]}..." if current_file else ""
            print(f"\r{progress}{current}", end="", flush=True)
        time.sleep(0.1)

def find_duplicates(directory, output_file, num_workers=None, 
                   exclude_patterns=None, min_size=None, max_size=None,
                   follow_symlinks=False):
    global processing_done, total_files
    
    if exclude_patterns is None:
        exclude_patterns = []
        
    total_cores = multiprocessing.cpu_count()
    if not num_workers:
        num_workers = max(1, total_cores // 2)
    
    print(f"Доступно ядер процессора: {total_cores}")
    print(f"Используется рабочих потоков: {num_workers}")
    if exclude_patterns:
        print(f"Исключаемые шаблоны файлов: {', '.join(exclude_patterns)}")
    if min_size is not None:
        print(f"Минимальный размер файла: {format_size(min_size)}")
    if max_size is not None:
        print(f"Максимальный размер файла: {format_size(max_size)}")
    print(f"Следовать по символическим ссылкам: {'Да' if follow_symlinks else 'Нет'}")
    print(f"\nСканирование директории {directory}...")
    
    all_files = scan_directory(directory, exclude_patterns, min_size, max_size, follow_symlinks)
    total_files = len(all_files)
    print(f"\nНайдено {total_files} файлов (после применения фильтров). Поиск дубликатов...\n")

    file_dict = {}  # { (размер, хэш, имя): [пути] }
    processing_done = False

    status_thread = threading.Thread(target=print_progress)
    status_thread.daemon = True
    status_thread.start()

    try:
        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            futures = [executor.submit(get_file_info, file) for file in all_files]
            
            for future in as_completed(futures):
                try:
                    file_size, file_hash, file_name, file_path = future.result()
                    if all([file_size is not None, file_hash is not None, file_name is not None]):
                        key = (file_size, file_hash, file_name)
                        if key in file_dict:
                            file_dict[key].append(file_path)
                        else:
                            file_dict[key] = [file_path]
                except Exception as e:
                    print(f"\nОшибка при обработке файла {file_path}: {e}")
    
    except KeyboardInterrupt:
        print("\nПрерывание пользователем...")
    finally:
        processing_done = True
        status_thread.join(timeout=1)
        print("\r" + " " * 120 + "\r", end="")  # Очищаем строку статуса

    # Фильтруем только дубликаты (где список путей > 1)
    duplicates = {k: v for k, v in file_dict.items() if len(v) > 1}

    with open(output_file, 'w') as f:
        if duplicates:
            f.write("Найдены дубликаты файлов (с одинаковым размером, хэшем и именем):\n")
            for (file_size, file_hash, file_name), files in duplicates.items():
                size_mb = format_size(file_size)
                f.write(f"\nИмя: {file_name} | Размер: {size_mb} | Хэш: {file_hash}\n")
                for file_path in files:
                    f.write(f"{file_path}\n")
            print(f"\nНайдено {len(duplicates)} групп дубликатов. Результаты сохранены в {output_file}")
        else:
            f.write("Дубликаты не найдены.\n")
            print("\nДубликаты не найдены.")

def parse_size(size_str):
    """Парсит размер файла из строки (поддерживает K, M, G суффиксы)"""
    if not size_str:
        return None
    size_str = size_str.upper().strip()
    if size_str.endswith('K'):
        return int(size_str[:-1]) * 1024
    elif size_str.endswith('M'):
        return int(size_str[:-1]) * 1024 * 1024
    elif size_str.endswith('G'):
        return int(size_str[:-1]) * 1024 * 1024 * 1024
    else:
        return int(size_str)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Поиск дубликатов файлов по размеру, хэш-сумме и имени.')
    parser.add_argument('directory', type=str, help='Директория для поиска дубликатов')
    parser.add_argument('--output', type=str, default='duplicates.txt', 
                       help='Файл для сохранения результатов (по умолчанию: duplicates.txt)')
    parser.add_argument('--workers', type=int, 
                       help='Количество рабочих потоков (по умолчанию: половина доступных ядер)')
    parser.add_argument('--exclude', type=str,
                       help='Шаблоны файлов для исключения (через запятую, например "*.tmp,*.bak")')
    parser.add_argument('--min-size', type=str,
                       help='Минимальный размер файлов для проверки (например 1M, 500K, 1000000)')
    parser.add_argument('--max-size', type=str,
                       help='Максимальный размер файлов для проверки (например 10M, 1G, 50000000)')
    parser.add_argument('--follow-symlinks', action='store_true',
                       help='Следовать по символическим ссылкам (по умолчанию False)')

    args = parser.parse_args()

    if not os.path.isdir(args.directory):
        print(f"Ошибка: {args.directory} не является директорией.")
        exit(1)

    exclude_patterns = [p.strip() for p in args.exclude.split(',')] if args.exclude else []
    
    # Парсим минимальный и максимальный размер
    min_size = parse_size(args.min_size) if args.min_size else None
    max_size = parse_size(args.max_size) if args.max_size else None

    find_duplicates(
        args.directory,
        args.output,
        args.workers,
        exclude_patterns,
        min_size,
        max_size,
        args.follow_symlinks
    )