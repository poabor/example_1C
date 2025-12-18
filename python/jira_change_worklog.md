# Скрипт переноса worklog в Jira

## Описание
Скрипт для автоматического переноса worklog (учетных записей рабочего времени) между задачами в Jira. 
Находит worklog текущего пользователя, содержащие слово "тест" в комментарии, и переносит их в указанную целевую задачу.

## Возможности
- Поиск worklog текущего пользователя с текстом "тест"
- Перенос найденных worklog в другую задачу
- Опциональное удаление исходных worklog после переноса
- Тестовый режим (без внесения изменений в Jira)
- Обработка одного или всех найденных worklog
- Автоматическое создание необходимых директорий
- Подробное логирование всех операций

## Установка зависимостей
pip install jira python-dateutil python-dotenv

## Файл окружения
Создайте файл jira_change_worklog.env со следующими параметрами:
-# Jira настройки подключения
JIRA_SERVER=https://your-jira-instance.atlassian.net
JIRA_ACCESS_TOKEN=your_api_token_here

-# Настройки логирования
LOG_DIR=/path/to/logs
LOG_FILE=jira_worklog_transfer.log

-# Дополнительные настройки
BACKUP_DIR=/path/to/backup

## Примеры использования
Базовое использование (только первый worklog):
python jira_change_worklog.py

Обработка ВСЕХ найденных worklog:
python jira_change_worklog.py --all

Тестовый режим (без изменений):
python jira_change_worklog.py --test-only
python jira_change_worklog.py --all --test-only

Специфические задачи:
python jira_change_worklog.py --source SUP-1234 --target IW-5678 --all

Без удаления исходных worklog:
python jira_change_worklog.py --all --no-delete

Все доступные параметры:
python jira_change_worklog.py --help


## Параметры командной строки
Параметр	    Описание	                        По умолчанию
--source	    Исходная задача	                    SUP-7998
--target	    Целевая задача	                    IW-405
--all	        Обработать ВСЕ найденные worklog	Только первый
--no-delete	    Не удалять исходные worklog	        Удалять
--test-only	    Тестовый режим (без изменений)	    Режим выполнения
--env-file	    Файл с переменными окружения	    jira_change_worklog.env
