## Краткое описание файлов:

* find_max_memory.sh - анализирует логи ТЖ и находит ТОП-3 записей с наибольшим потреблением памяти (поле Memory) в событиях CALL.
* tj_unpack.sh - распаковывает архивный файлы ТЖ в тек. директорию. файлы формируются при использовании решения от https://itra-service.ru/
    * Распаковывает архивы параллельно
    * Удаляет файлы <10 байт
    * Удаляет пустые директории
    * Удаляет исходные архивы