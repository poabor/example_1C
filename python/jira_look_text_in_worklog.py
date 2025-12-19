#!/usr/bin/env python3
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime
from jira import JIRA
import os
import sys
from dotenv import load_dotenv
import re

# Загрузка переменных
load_dotenv('jira_change_worklog.env')

# Настройка путей для логов
LOG_DIR = os.getenv('LOG_DIR', '/tmp')
LOG_FILE = os.getenv('LOG_FILE', 'jira_script.log')

# Создаем директорию для логов если не существует
os.makedirs(LOG_DIR, exist_ok=True)

# Полный путь к лог-файлу
LOG_PATH = os.path.join(LOG_DIR, LOG_FILE)

# Настройка логирования
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

def find_issues(jira_client, jql_query, expand_fields=None):
    """
    Поиск задач в Jira по JQL запросу
    :param jira_client: Объект клиента Jira
    :param jql_query: JQL запрос для поиска
    :return: Список найденных задач или None в случае ошибки
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

def print_worklogs_with_test_text(jira_client, issue_key):
    """
    Выводит worklog из указанной задачи, содержащие текст "тест"
    :param jira_client: Объект клиента Jira
    :param issue_key: Ключ задачи (например, SUP-7998)
    """
    try:
        logger.info(f"\n=== Поиск worklog в задаче {issue_key} ===")
        
        # Получаем задачу
        issue = jira_client.issue(issue_key)
        logger.info(f"Задача: {issue.key} - {issue.fields.summary}")
        
        # Получаем worklog для задачи
        worklogs = jira_client.worklogs(issue)
        
        if not worklogs:
            logger.info(f"В задаче {issue_key} нет записей worklog")
            return
        
        test_worklogs_found = 0
        
        for worklog in worklogs:
            # Проверяем, содержит ли комментарий слово "тест" (регистронезависимо)
            comment = worklog.comment if hasattr(worklog, 'comment') and worklog.comment else ""
            
            if re.search(r'\bтест(?:[аы]|ов|ом|ами|ах)?\b', comment.lower()):
                test_worklogs_found += 1
                
                # Получаем автора
                author = worklog.author.displayName if hasattr(worklog.author, 'displayName') else worklog.author.name
                
                # Форматируем дату начала
                started = worklog.started
                if isinstance(started, str):
                    started_str = started
                else:
                    started_str = started.strftime('%Y-%m-%d %H:%M:%S') if hasattr(started, 'strftime') else str(started)
                
                # Преобразуем время в секундах в часы и минуты
                time_spent_seconds = worklog.timeSpentSeconds
                hours = time_spent_seconds // 3600
                minutes = (time_spent_seconds % 3600) // 60
                seconds = time_spent_seconds % 60
                
                logger.info(f"\n--- Worklog #{test_worklogs_found} ---")
                logger.info(f"ID: {worklog.id}")
                logger.info(f"Автор: {author}")
                logger.info(f"Начало: {started_str}")
                logger.info(f"Затраченное время: {hours} ч {minutes} мин {seconds} сек ({time_spent_seconds} секунд)")
                logger.info(f"Комментарий: {comment}")
                logger.info("-" * 40)
        
        if test_worklogs_found == 0:
            logger.info(f"В задаче {issue_key} не найдено worklog с текстом 'тест'")
        else:
            logger.info(f"\nВсего найдено worklog с текстом 'тест': {test_worklogs_found}")
            
    except Exception as e:
        logger.error(f"Ошибка при получении worklog для задачи {issue_key}: {str(e)}")

def main():
    logger.info("=== Запуск скрипта работы с Jira ===")
    
    try:
        # Загрузка переменных окружения
        load_dotenv('jira_assigne.env')
        logger.info("Переменные окружения загружены")
        
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
        
        # 1. Вывод worklog из задачи SUP-7998 с текстом "тест"
        print_worklogs_with_test_text(jira, "SUP-7998")
        
    except Exception as e:
        logger.error(f"Общая ошибка: {str(e)}")
        sys.exit(1)
        
    finally:
        if 'jira' in locals():
            jira.close()
            logger.info("Сессия Jira закрыта")
        logger.info("=== Завершение работы скрипта ===\n")

if __name__ == "__main__":
    main()