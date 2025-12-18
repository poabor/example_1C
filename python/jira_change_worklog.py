#!/usr/bin/env python3
"""
Скрипт для переноса worklog между задачами в Jira
Находит worklog текущего пользователя с текстом "тест" и переносит их в другую задачу
"""

import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime, timezone
from jira import JIRA
import os
import sys
import argparse
from dotenv import load_dotenv
import re
import dateutil.parser

# ============================================================================
# Парсинг аргументов командной строки
# ============================================================================
def parse_arguments():
    parser = argparse.ArgumentParser(
        description='Перенос worklog между задачами в Jira',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры использования:
  %(prog)s                    # Обработать только первый найденный worklog
  %(prog)s --all              # Обработать все найденные worklog
  %(prog)s --source SUP-7998 --target IW-405 --all
  
По умолчанию скрипт работает только с первым найденным worklog.
Для обработки всех worklog используйте параметр --all
        """
    )
    
    parser.add_argument(
        '--source',
        type=str,
        default='SUP-7998',
        help='Исходная задача (по умолчанию: SUP-7998)'
    )
    
    parser.add_argument(
        '--target',
        type=str,
        default='IW-405',
        help='Целевая задача (по умолчанию: IW-405)'
    )
    
    parser.add_argument(
        '--all',
        action='store_true',
        help='Обработать ВСЕ найденные worklog (по умолчанию: только первый)'
    )
    
    parser.add_argument(
        '--no-delete',
        action='store_true',
        help='Не удалять исходные worklog после переноса'
    )
    
    parser.add_argument(
        '--test-only',
        action='store_true',
        help='Тестовый режим: только показать найденные worklog без переноса'
    )
    
    parser.add_argument(
        '--env-file',
        type=str,
        default='jira_change_worklog.env',
        help='Файл с переменными окружения (по умолчанию: jira_change_worklog.env)'
    )
    
    return parser.parse_args()

args = parse_arguments()

# ============================================================================
# Настройка путей и проверка директорий
# ============================================================================

# Загрузка переменных окружения
env_file = args.env_file
if not os.path.exists(env_file):
    # Пробуем найти в директории скрипта
    script_dir = os.path.dirname(os.path.abspath(__file__))
    env_path = os.path.join(script_dir, env_file)
    if os.path.exists(env_path):
        env_file = env_path
    else:
        print(f"ОШИБКА: Файл .env не найден: {env_file}")
        print(f"Искали по пути: {env_path}")
        sys.exit(1)

load_dotenv(env_file)

# Получаем настройки из .env
LOG_DIR = os.getenv('LOG_DIR', '/tmp')
LOG_FILE = os.getenv('LOG_FILE', 'jira_script.log')
BACKUP_DIR = os.getenv('BACKUP_DIR', '/tmp/jira_backup')

# Создаем необходимые директории
directories_to_create = [LOG_DIR, BACKUP_DIR]
for directory in directories_to_create:
    try:
        os.makedirs(directory, exist_ok=True)
        print(f"Директория создана/проверена: {directory}")
    except Exception as e:
        print(f"ОШИБКА: Не удалось создать директорию {directory}: {e}")
        sys.exit(1)

# Полный путь к лог-файлу
LOG_PATH = os.path.join(LOG_DIR, LOG_FILE)

# ============================================================================
# Настройка логирования
# ============================================================================
def setup_logging():
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    
    file_handler = RotatingFileHandler(
        LOG_PATH,
        maxBytes=5*1024*1024,
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setFormatter(formatter)
    
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger

logger = setup_logging()

# ============================================================================
# Вспомогательные функции
# ============================================================================
def find_issues(jira_client, jql_query, expand_fields=None):
    """
    Поиск задач в Jira по JQL запросу
    """
    try:
        logger.info(f"Поиск задач по запросу: {jql_query}")
        
        if expand_fields:
            issues = jira_client.search_issues(jql_query, expand=expand_fields)
        else:
            issues = jira_client.search_issues(jql_query)
            
        logger.info(f"Найдено {len(issues)} задач")
        return issues
    except Exception as e:
        logger.error(f"Ошибка при поиске задач: {str(e)}")
        return None

def get_current_user(jira_client):
    """
    Получает информацию о текущем пользователе
    """
    try:
        current_user = jira_client.current_user()
        username = current_user.name if hasattr(current_user, 'name') else str(current_user)
        display_name = current_user.displayName if hasattr(current_user, 'displayName') else username
        logger.info(f"Текущий пользователь: {username} ({display_name})")
        return username
    except Exception as e:
        logger.error(f"Ошибка при получении текущего пользователя: {str(e)}")
        return None

def delete_worklog_safe(jira_client, issue_key, worklog_id):
    """
    Безопасное удаление worklog с проверкой существования
    """
    try:
        issue = jira_client.issue(issue_key)
        worklogs = jira_client.worklogs(issue)
        
        # Ищем worklog по ID
        for worklog in worklogs:
            if str(worklog.id) == str(worklog_id):
                # Получаем информацию о worklog перед удалением
                comment = worklog.comment if hasattr(worklog, 'comment') and worklog.comment else ""
                time_spent = worklog.timeSpentSeconds
                
                # Удаляем worklog
                worklog.delete()
                
                logger.info(f"Удален worklog {worklog_id} из задачи {issue_key}")
                logger.info(f"  Комментарий удаленного: {comment[:50]}...")
                logger.info(f"  Время удаленного: {time_spent} секунд")
                return True
        
        logger.warning(f"Worklog {worklog_id} не найден в задаче {issue_key}")
        return False
        
    except Exception as e:
        logger.error(f"Ошибка при удалении worklog {worklog_id}: {str(e)}")
        return False

def format_jira_datetime(dt_string_or_object):
    """
    Форматирует дату для Jira API из строки или объекта datetime
    Возвращает datetime объект с правильным timezone
    """
    try:
        if isinstance(dt_string_or_object, datetime):
            # Если это уже datetime объект
            if dt_string_or_object.tzinfo is None:
                # Если нет timezone, добавляем UTC
                return dt_string_or_object.replace(tzinfo=timezone.utc)
            return dt_string_or_object
            
        elif isinstance(dt_string_or_object, str):
            # Если это строка, парсим её
            try:
                # Пробуем стандартный парсер
                dt = dateutil.parser.parse(dt_string_or_object)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except:
                # Пробуем разные форматы вручную
                formats = [
                    '%Y-%m-%dT%H:%M:%S.%f%z',
                    '%Y-%m-%dT%H:%M:%S%z',
                    '%Y-%m-%d %H:%M:%S',
                    '%Y-%m-%dT%H:%M:%S'
                ]
                
                for fmt in formats:
                    try:
                        dt = datetime.strptime(dt_string_or_object, fmt)
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                        return dt
                    except:
                        continue
                
                # Если ничего не сработало, возвращаем текущее время
                logger.warning(f"Не удалось распарсить дату: {dt_string_or_object}")
                return datetime.now(timezone.utc)
                
        else:
            # Если неизвестный тип, возвращаем текущее время
            logger.warning(f"Неизвестный тип даты: {type(dt_string_or_object)}")
            return datetime.now(timezone.utc)
            
    except Exception as e:
        logger.error(f"Ошибка при форматировании даты: {str(e)}")
        return datetime.now(timezone.utc)

def transfer_worklogs_with_test_text(jira_client, source_issue_key, target_issue_key, 
                                     delete_original=True, process_all=False, test_only=False):
    """
    Переносит worklog из исходной задачи в целевую, если они содержат текст "тест"
    и принадлежат текущему пользователю
    
    :param jira_client: Объект клиента Jira
    :param source_issue_key: Ключ исходной задачи
    :param target_issue_key: Ключ целевой задачи
    :param delete_original: Удалять ли исходный worklog после переноса
    :param process_all: Обрабатывать все найденные worklog или только первый
    :param test_only: Тестовый режим (только вывод информации без изменений)
    :return: Кортеж (количество обработанных, количество удаленных)
    """
    try:
        logger.info(f"\n=== Перенос worklog из {source_issue_key} в {target_issue_key} ===")
        if test_only:
            logger.info("РЕЖИМ: ТЕСТОВЫЙ (без изменений в Jira)")
        elif delete_original:
            logger.info("Режим: перенос с удалением исходных worklog")
        else:
            logger.info("Режим: копирование worklog (исходные сохраняются)")
        
        if not process_all:
            logger.info("Обработка: только ПЕРВЫЙ найденный worklog")
            logger.info("Для обработки ВСЕХ worklog запустите скрипт с параметром --all")
        
        # Получаем текущего пользователя
        current_username = get_current_user(jira_client)
        if not current_username:
            logger.error("Не удалось определить текущего пользователя")
            return 0, 0
        
        # Проверяем существование обеих задач
        try:
            source_issue = jira_client.issue(source_issue_key)
            logger.info(f"Исходная задача: {source_issue.key} - {source_issue.fields.summary}")
        except Exception as e:
            logger.error(f"Ошибка: Исходная задача {source_issue_key} не найдена: {str(e)}")
            return 0, 0
        
        try:
            target_issue = jira_client.issue(target_issue_key)
            logger.info(f"Целевая задача: {target_issue.key} - {target_issue.fields.summary}")
        except Exception as e:
            logger.error(f"Ошибка: Целевая задача {target_issue_key} не найдена: {str(e)}")
            return 0, 0
        
        # Получаем worklog для исходной задачи
        worklogs = jira_client.worklogs(source_issue)
        
        if not worklogs:
            logger.info(f"В исходной задаче {source_issue_key} нет записей worklog")
            return 0, 0
        
        transferred_count = 0
        deleted_count = 0
        found_count = 0
        processed_count = 0
        
        # Сначала считаем сколько всего найдено
        for worklog in worklogs:
            worklog_author = worklog.author.name if hasattr(worklog.author, 'name') else str(worklog.author)
            if worklog_author == current_username:
                comment = worklog.comment if hasattr(worklog, 'comment') and worklog.comment else ""
                if re.search(r'\bтест(?:[аы]|ов|ом|ами|ах)?\b', comment.lower()):
                    found_count += 1
        
        logger.info(f"Найдено worklog текущего пользователя с текстом 'тест': {found_count}")
        
        # Обрабатываем worklog
        for worklog in worklogs:
            # Проверяем, принадлежит ли worklog текущему пользователю
            worklog_author = worklog.author.name if hasattr(worklog.author, 'name') else str(worklog.author)
            
            if worklog_author != current_username:
                continue
            
            # Проверяем, содержит ли комментарий слово "тест" (регистронезависимо)
            comment = worklog.comment if hasattr(worklog, 'comment') and worklog.comment else ""
            
            if not re.search(r'\bтест(?:[аы]|ов|ом|ами|ах)?\b', comment.lower()):
                continue
            
            processed_count += 1
            
            # Форматируем дату для отображения
            started_date = worklog.started
            if hasattr(started_date, 'strftime'):
                started_str = started_date.strftime('%Y-%m-%d %H:%M:%S')
            else:
                started_str = str(started_date)
            
            # Преобразуем время в читаемый формат
            time_spent_seconds = worklog.timeSpentSeconds
            hours = time_spent_seconds // 3600
            minutes = (time_spent_seconds % 3600) // 60
            time_spent_str = f"{hours}h {minutes}m"
            
            logger.info(f"\n--- Найден worklog #{processed_count} ---")
            logger.info(f"ID: {worklog.id}")
            logger.info(f"Время: {time_spent_str} ({worklog.timeSpentSeconds} секунд)")
            logger.info(f"Дата: {started_str}")
            logger.info(f"Комментарий: {comment}")
            
            # Если тестовый режим - только показываем
            if test_only:
                logger.info("ТЕСТОВЫЙ РЕЖИМ: worklog НЕ будет перенесен")
                if not process_all:
                    logger.info("Завершено в тестовом режиме (только первый worklog)")
                    break
                continue
            
            try:
                # Создаем комментарий с пометкой о переносе
                transfer_note = f"[Перенесено из {source_issue_key}]"
                new_comment = f"{transfer_note}\n\n{comment}" if comment else transfer_note
                
                # Сохраняем ID исходного worklog перед возможным удалением
                original_worklog_id = worklog.id
                
                # Форматируем дату для Jira API
                started_datetime = format_jira_datetime(worklog.started)
                
                # Создаем новый worklog в целевой задаче
                new_worklog = jira_client.add_worklog(
                    issue=target_issue,
                    timeSpentSeconds=worklog.timeSpentSeconds,
                    comment=new_comment,
                    started=started_datetime
                )
                
                transferred_count += 1
                
                # Логируем успешный перенос
                logger.info(f"УСПЕХ: Worklog перенесен из {source_issue_key} в {target_issue_key}")
                
                # Удаляем исходный worklog, если указано
                if delete_original:
                    if delete_worklog_safe(jira_client, source_issue_key, original_worklog_id):
                        deleted_count += 1
                    else:
                        logger.warning(f"  Не удалось удалить исходный worklog {original_worklog_id}")
                        
            except Exception as add_error:
                logger.error(f"ОШИБКА: Не удалось перенести worklog: {str(add_error)}")
            
            # Если не обрабатываем все, выходим после первого
            if not process_all:
                logger.info("\nОбработан только первый найденный worklog")
                logger.info("Для обработки ВСЕХ найденных worklog запустите скрипт с параметром --all")
                break
        
        # Итоговый отчет
        logger.info(f"\n{'='*60}")
        logger.info("ИТОГИ ПЕРЕНОСА:")
        logger.info(f"Исходная задача: {source_issue_key}")
        logger.info(f"Целевая задача: {target_issue_key}")
        logger.info(f"Найдено подходящих worklog: {found_count}")
        logger.info(f"Обработано worklog: {processed_count}")
        
        if not test_only:
            logger.info(f"Успешно перенесено: {transferred_count}")
            if delete_original:
                logger.info(f"Удалено из исходной задачи: {deleted_count}")
        
        if test_only and found_count > 0 and processed_count == 1:
            logger.info("\nСОВЕТ: Для тестирования всех найденных worklog запустите:")
            logger.info(f"  python {os.path.basename(__file__)} --all --test-only")
        
        if not process_all and found_count > 1:
            logger.info("\nВНИМАНИЕ: Найдено несколько подходящих worklog!")
            logger.info("Для обработки ВСЕХ worklog запустите скрипт с параметром --all")
            logger.info(f"  python {os.path.basename(__file__)} --all")
        
        return transferred_count, deleted_count
            
    except Exception as e:
        logger.error(f"Ошибка при переносе worklog: {str(e)}")
        return 0, 0

# ============================================================================
# Основная функция
# ============================================================================
def main():
    logger.info("="*60)
    logger.info("ЗАПУСК СКРИПТА ПЕРЕНОСА WORKLOG В JIRA")
    logger.info("="*60)
    
    # Логируем параметры запуска
    logger.info(f"Параметры запуска:")
    logger.info(f"  Исходная задача: {args.source}")
    logger.info(f"  Целевая задача: {args.target}")
    logger.info(f"  Обработка всех: {'ДА' if args.all else 'НЕТ (только первый)'}")
    logger.info(f"  Удаление исходных: {'НЕТ' if args.no_delete else 'ДА'}")
    logger.info(f"  Тестовый режим: {'ДА' if args.test_only else 'НЕТ'}")
    logger.info(f"  Файл .env: {env_file}")
    
    try:
        logger.info(f"Загрузка переменных из: {env_file}")
        
        # Подключение к Jira
        try:
            jira = JIRA(
                server=os.getenv('JIRA_SERVER'),
                token_auth=os.getenv('JIRA_ACCESS_TOKEN')
            )
            logger.info(f"Успешное подключение к Jira: {os.getenv('JIRA_SERVER')}")
        except Exception as e:
            logger.error(f"Ошибка подключения к Jira: {str(e)}")
            sys.exit(1)
        
        # Выполняем перенос worklog
        transferred, deleted = transfer_worklogs_with_test_text(
            jira, 
            args.source, 
            args.target,
            delete_original=not args.no_delete,
            process_all=args.all,
            test_only=args.test_only
        )
        
        if not args.test_only and transferred == 0:
            logger.warning("Не было перенесено ни одного worklog")
        
    except Exception as e:
        logger.error(f"Общая ошибка: {str(e)}")
        sys.exit(1)
        
    finally:
        if 'jira' in locals():
            jira.close()
            logger.info("Сессия Jira закрыта")
        
        logger.info("="*60)
        logger.info("ЗАВЕРШЕНИЕ РАБОТЫ СКРИПТА")
        logger.info("="*60)

if __name__ == "__main__":
    main()