#!/usr/bin/env python3
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime
from jira import JIRA
import os
import sys
from dotenv import load_dotenv

# Загрузка переменных
load_dotenv('/cloud/repo/example_1C/python/jira_assigne.env')

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

def update_labels_to_2line(jira_client, jql_query):
    """
    Изменение меток на "2линия" для задач, соответствующих JQL запросу
    :param jira_client: Объект клиента Jira
    :param jql_query: JQL запрос для поиска задач
    :return: Кортеж (количество обновленных задач, количество ошибок)
    """
    issues = find_issues(jira_client, jql_query)
    
    if not issues:
        logger.info(f"Не найдено задач по запросу: {jql_query}")
        return 0, 0
    
    updated_count = 0
    error_count = 0
    
    for issue in issues:
        try:
            # Получаем текущие метки
            current_labels = issue.fields.labels
            
            # Удаляем метку "1Линия" если она есть
            if '1Линия' in current_labels:
                current_labels.remove('1Линия')
            
            # Добавляем метку "2линия" если её ещё нет
            if '2линия' not in current_labels:
                current_labels.append('2линия')
            
            # Обновляем задачу
            issue.update(fields={'labels': current_labels})
            logger.info(f"УСПЕХ: Метки обновлены для задачи {issue.key}: {current_labels}")
            updated_count += 1
        except Exception as e:
            logger.error(f"ОШИБКА: Не удалось обновить метки для задачи {issue.key}: {str(e)}")
            error_count += 1
    
    return updated_count, error_count

def clear_assignee(jira_client, jql_query):
    """
    Очистка поля assignee для задач, найденных по JQL запросу
    """
    issues = find_issues(jira_client, jql_query)
    
    if not issues:
        logger.info(f"Не найдено задач по запросу: {jql_query}")
        return 0, 0
    
    processed_count = 0
    error_count = 0
    
    for issue in issues:
        try:
            jira_client.assign_issue(issue, None)
            logger.info(f"УСПЕХ: Поле assignee очищено для задачи {issue.key}")
            processed_count += 1
        except Exception as e:
            logger.error(f"ОШИБКА: Не удалось очистить assignee для задачи {issue.key}: {str(e)}")
            error_count += 1
    
    return processed_count, error_count

def reassign_to_last_human(jira_client, jql_query):
    """
    Переназначение задач на последнего ответственного пользователя
    """
    issues = find_issues(jira_client, jql_query, expand_fields='changelog')
    
    if not issues:
        logger.info(f"Не найдено задач по запросу: {jql_query}")
        return 0, 0
    
    reassigned_count = 0
    skipped_count = 0
    
    for issue in issues:
        logger.info(f"\nАнализ задачи: {issue.key}")
        
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
        robot_jql = 'resolved is EMPTY AND assignee = robot'
        reassigned_count, skipped_count = reassign_to_last_human(jira, robot_jql)
        logger.info(f"\nИтоги переназначения:")
        logger.info(f"Успешно переназначено: {reassigned_count}")
        logger.info(f"Пропущено: {skipped_count}")
        
        # 2. Очистка assignee для задач, назначенных на admin
        admin_jql = 'resolved is EMPTY AND assignee = admin'
        processed_count, error_count = clear_assignee(jira, admin_jql)
        logger.info(f"\nИтоги очистки assignee:")
        logger.info(f"Обработано задач: {processed_count}")
        logger.info(f"Ошибок при обработке: {error_count}")
        
        # 3. Обновление меток для старых задач 1Линии
        labels_jql = 'resolved is EMPTY AND labels = 1Линия AND updatedDate <= startOfDay(-4)'
        updated_count, labels_error_count = update_labels_to_2line(jira, labels_jql)
        logger.info(f"\nИтоги обновления меток:")
        logger.info(f"Обновлено задач: {updated_count}")
        logger.info(f"Ошибок при обновлении: {labels_error_count}")
            
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