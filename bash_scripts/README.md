## bash скрипты для сервера 1С:

* dir_clst.sh - анализирует файл 1CV8Clst.lst, выводит отсортированный список папок с названием баз в кластере. сортирует папки по объему.
* check_missing_folders.sh - выводит отсортированный по объему список директорий, которые не указаны в кластере (в файле 1CV8Clst.lst)

### restoreDB.sh - копирование и восстановление бекапа базы
Этот скрипт автоматизирует процесс:
    # Поиска самого нового файла резервной копии 1С (с расширением .dt)
    # Копирования с проверкой целостности
    # Загрузки в указанную базу 1С через 1C:Designer
    # Очистки временных файлов

Обязательный аргумент:
    ./script.sh -c /путь/конфиг.conf
    # или
    ./script.sh --config=/путь/конфиг.conf

#### Структура конфигурационного файла
Пример config.conf:
    # Обязательные параметры
    SERVER_NAME="1C_SERVER"
    IB_NAME="Бухгалтерия"
    DB_USER="Администратор"
    DB_PASS="пароль"

    # Опционально
    PATH_1C="/opt/1C/v8.3/x86_64"  # Путь к 1C:Enterprise
    source_dir="/backups/1c"        # Директория с .dt-файлами
    target_dir="/tmp/1c_restore"    # Временная директория