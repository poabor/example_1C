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

def clear_admin_assignee(jira_client):
    """
    Поиск задач, назначенных на admin, и очистка поля assignee
    :param jira_client: Объект клиента Jira
    :return: Кортеж (количество обработанных задач, количество ошибок)
    """
    jql_query = 'resolved is EMPTY AND assignee = admin'
    issues = find_issues(jira_client, jql_query)
    
    if not issues:
        logger.info("Не найдено задач, назначенных на admin")
        return 0, 0
    
    processed_count = 0
    error_count = 0
    
    for issue in issues:
        try:
            # Очищаем assignee (назначаем на None)
            jira_client.assign_issue(issue, None)
            logger.info(f"УСПЕХ: Поле assignee очищено для задачи {issue.key}")
            processed_count += 1
        except Exception as e:
            logger.error(f"ОШИБКА: Не удалось очистить assignee для задачи {issue.key}: {str(e)}")
            error_count += 1
    
    return processed_count, error_count

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
        
        # 2. Очистка assignee для задач, назначенных на admin
        processed_count, error_count = clear_admin_assignee(jira)
        logger.info(f"\nИтоги очистки assignee:")
        logger.info(f"Обработано задач: {processed_count}")
        logger.info(f"Ошибок при обработке: {error_count}")
            
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