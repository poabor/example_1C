#!/usr/bin/env python3
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime
from jira import JIRA
import os
import sys
from dotenv import load_dotenv

# Загрузка переменных
load_dotenv('/cloud/repo/example_1C/python/jira_assigne.env')  # Укажите абсолютный путь

# Настройка путей для логов
LOG_DIR = os.getenv('LOG_DIR', '/tmp')  # fallback на /tmp если не задано
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

def find_issues(jira_client, jql_query):
    """
    Поиск задач в Jira по JQL запросу
    :param jira_client: Объект клиента Jira
    :param jql_query: JQL запрос для поиска
    :return: Список найденных задач или None в случае ошибки
    """
    try:
        logger.info(f"Поиск задач по запросу: {jql_query}")
        issues = jira_client.search_issues(jql_query, expand='changelog')
        logger.info(f"Найдено {len(issues)} задач")
        return issues
    except Exception as e:
        logger.error(f"Ошибка при поиске задач: {str(e)}")
        return None

def check_issue_status(jira_client, issue_key):
    """
    Проверка статуса задачи и возврат информации о ней
    :param jira_client: Объект клиента Jira
    :param issue_key: Ключ задачи (например, PROJ-123)
    :return: Словарь с информацией о задаче или None в случае ошибки
    """
    try:
        issue = jira_client.issue(issue_key)
        return {
            'key': issue.key,
            'status': issue.fields.status.name,
            'assignee': str(issue.fields.assignee) if issue.fields.assignee else None,
            'summary': issue.fields.summary
        }
    except Exception as e:
        logger.error(f"Ошибка при проверке задачи {issue_key}: {str(e)}")
        return None

def reassign_issues(jira_client, issues):
    """
    Переназначение задач на последнего ответственного пользователя
    :param jira_client: Объект клиента Jira
    :param issues: Список задач для обработки
    :return: Кортеж (количество переназначенных задач, количество пропущенных задач)
    """
    reassigned_count = 0
    skipped_count = 0
    
    for issue in issues:
        logger.info(f"\nАнализ задачи: {issue.key}")
        
        # Получаем историю изменений
        changelog = issue.changelog
        last_human_assignee = None
        
        if changelog and changelog.histories:
            for history in reversed(changelog.histories):
                for item in history.items:
                    if item.field == 'assignee':
                        if (item.toString and 
                            item.toString != "Не назначен" and
                            item.toString.lower() != "robot"):
                            last_human_assignee = item.toString
                            logger.debug(f"Найден кандидат: {last_human_assignee}")
                            break
                if last_human_assignee:
                    break
        
        if last_human_assignee:
            try:
                jira_client.assign_issue(issue, last_human_assignee)
                logger.info(f"УСПЕХ: Задача {issue.key} переназначена на {last_human_assignee}")
                reassigned_count += 1
            except Exception as assign_error:
                logger.error(f"ОШИБКА: Не удалось переназначить {issue.key}: {str(assign_error)}")
        else:
            logger.warning(f"ПРОПУСК: Для задачи {issue.key} не найден подходящий пользователь")
            skipped_count += 1
    
    return reassigned_count, skipped_count

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
        
        # 1. Переназначение задач, назначенных на robot
        jql_query = 'resolved is EMPTY AND assignee = robot'
        issues = find_issues(jira, jql_query)
        
        if issues:
            reassigned_count, skipped_count = reassign_issues(jira, issues)
            logger.info(f"\nИтоги переназначения:")
            logger.info(f"Всего задач обработано: {len(issues)}")
            logger.info(f"Успешно переназначено: {reassigned_count}")
            logger.info(f"Пропущено: {skipped_count}")
        
        # 2. Дополнительная операция: проверка статуса конкретной задачи
        example_issue_key = 'ERP25-261'  # Можно заменить на получение из переменных окружения
        issue_info = check_issue_status(jira, example_issue_key)
        if issue_info:
            logger.info(f"\nИнформация о задаче {example_issue_key}:")
            logger.info(f"Статус: {issue_info['status']}")
            logger.info(f"Назначена на: {issue_info['assignee']}")
            logger.info(f"Краткое описание: {issue_info['summary']}")
            
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