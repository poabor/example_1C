import requests
import pandas as pd
import json
from datetime import datetime
import warnings
import math
warnings.filterwarnings('ignore')

# Добавляем прогресс-бар
try:
    from tqdm import tqdm
except ImportError:
    print("Устанавливаем tqdm для прогресс-бара...")
    import subprocess
    import sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "tqdm"])
    from tqdm import tqdm

def get_moex_bonds():
    """
    Получает список облигаций с MOEX ISS API
    """
    print("📡 Загрузка данных с MOEX ISS API...")
    
    # Основные эндпоинты MOEX для облигаций
    securities_url = "https://iss.moex.com/iss/engines/stock/markets/bonds/securities.json?iss.only=securities&securities.fields=SECID,SHORTNAME,ISSUEDATE,MATDATE,COUPONDATE,COUPONPERCENT,CURRENCY,FACEVALUE,ACCRUEDINT"
    # boards_url = "https://iss.moex.com/iss/engines/stock/markets/bonds/boards/TQCB/securities.json"
    boards_url = "https://iss.moex.com/iss/engines/stock/markets/bonds/securities.json"
    
    try:
        # Прогресс-бар для загрузки данных
        with tqdm(total=2, desc="Загрузка API", unit="запрос") as pbar:
            # Получаем данные по облигациям
            resp_sec = requests.get(securities_url, timeout=30)
            resp_sec.raise_for_status()
            securities_data = resp_sec.json()
            pbar.update(1)
            pbar.set_description("Секьюрити OK")
            
            # Получаем рыночные данные (цены, доходность)
            resp_boards = requests.get(boards_url, timeout=30)
            resp_boards.raise_for_status()
            boards_data = resp_boards.json()
            pbar.update(1)
            pbar.set_description("Рынок OK")
        
        print("✅ Данные успешно загружены")
        return securities_data, boards_data
        
    except Exception as e:
        print(f"❌ Ошибка получения данных: {e}")
        return None, None

def parse_bonds_data(securities_data, boards_data):
    """
    Парсит данные и извлекает нужные поля с прогресс-баром
    """
    if not securities_data or not boards_data:
        return []
    
    print("\n🔍 Парсинг данных...")
    
    # Извлекаем таблицы из JSON ответа MOEX
    securities = securities_data['securities']['data']
    securities_columns = securities_data['securities']['columns']
    sec_df = pd.DataFrame(securities, columns=securities_columns)
    
    marketdata = boards_data['marketdata']['data']
    market_columns = boards_data['marketdata']['columns']
    market_df = pd.DataFrame(marketdata, columns=market_columns)
    
    # Объединяем данные по SECID (тикер)
    print("🔗 Объединение данных...")
    merged_df = pd.merge(sec_df, market_df, on='SECID', how='inner')
    
    print(f"📊 Всего облигаций для анализа: {len(merged_df)}")
    
    bonds_list = []
    
    # Прогресс-бар для обработки каждой облигации
    with tqdm(total=len(merged_df), desc="Фильтрация ОФЗ", unit="обл", leave=True) as pbar:
        for idx, (_, row) in enumerate(merged_df.iterrows()):
            ticker = row['SECID']
            name = row.get('SHORTNAME', '')
            
            # Фильтр по ОФЗ (название содержит ОФЗ)
            if 'ОФЗ' not in str(name).upper():
                pbar.update(1)
                continue
            
            # A - активные
            status = row.get('STATUS', 0)
            if 'A' != str(status).upper():
                pbar.update(1)
                continue

            # Пропускаем если нет цены или доходности
            price = row.get('LAST', None) or row.get('WAPRICE', None)
            yield_value = row.get('YIELDCLOSE', None) or row.get('YIELD', None)
            
            if pd.isna(price) or pd.isna(yield_value) or price <= 0:
                pbar.update(1)
                continue
            
            # Фиксированный купон (упрощенный фильтр по типу)
            bond_type = row.get('BONDTYPE', 0)
            if 'Фикс с известным купоном'.upper() not in str(bond_type).upper():
                pbar.update(1)
                continue
            
            # Месяц выплаты купона (берем последний известный)
            coupon_date = row.get('NEXTCOUPON', '')
            coupon_month = None
            if coupon_date:
                try:
                    coupon_dt = pd.to_datetime(coupon_date)
                    coupon_month = coupon_dt.month
                except:
                    pass
            
            # Стоимость купона (примерный расчет)
            coupon_value = row.get('COUPONVALUE', 1000)
            if coupon_value < 45:
                pbar.update(1)
                continue
            face_value = row.get('FACEVALUE', 1000)
            amount_bonds = math.ceil(price*10/coupon_value)
            
            bonds_list.append({
                'Тикер': ticker,
                'Название': name,
                'Цена': round(price, 2),
                'Доходность (%)': yield_value,
                'Месяц купона': coupon_month,
                'Стоимость купона': coupon_value,
                'Номинал': face_value,
                'Дата погашения': row.get('MATDATE', ''),
                'кол-во купонов для +1': amount_bonds
            })
            
            pbar.update(1)
            pbar.set_postfix({'Найдено ОФЗ': len(bonds_list)})
    
    print(f"✅ Найдено подходящих ОФЗ: {len(bonds_list)}")
    return bonds_list

def main():
    print("🚀 Анализ ОФЗ на Московской бирже")
    print("Дата:", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("-" * 60)
    
    securities_data, boards_data = get_moex_bonds()
    
    if not securities_data:
        print("❌ Не удалось получить данные. Проверьте интернет-соединение.")
        return
    
    bonds_list = parse_bonds_data(securities_data, boards_data)
    
    if not bonds_list:
        print("❌ Не найдено подходящих облигаций (ОФЗ без амортизации, фиксированный купон).")
        return
    
    print("\n📈 Сортировка результатов...")
    df = pd.DataFrame(bonds_list)

  # ✅ ОКОНЧАТЕЛЬНОЕ УБИРАНИЕ ДУБЛИКАТОВ ПО ТИКЕРУ
    df = df.drop_duplicates(subset=['Тикер'], keep='first')

    # Сортировка: по доходности убывание, затем по цене убывание
    # df = df.sort_values(by=['Цена', 'Стоимость купона', 'Доходность (%)'], ascending=[True, False, False])
    df = df.sort_values(by=['кол-во купонов для +1', 'Цена', 'Стоимость купона'], ascending=[True, True, False])
    
    # Вывод результатов
    print("\n" + "="*100)
    print("🏆 ОФЗ: ТОП по доходности (без амортизации, фиксированный купон)")
    print("="*100)
    print(df[['Тикер', 'Название', 'Цена', 'Доходность (%)', 'Месяц купона', 'Стоимость купона', 'кол-во купонов для +1']].to_string(index=False))
    
    # Сохранение в CSV
    filename = f"ofz_analysis_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    df.to_csv(filename, index=False, encoding='utf-8-sig')
    print(f"\n💾 Данные сохранены в файл: {filename}")
    
    print(f"\n📊 Всего найдено облигаций: {len(df)}")
    print("✅ Анализ завершен!")

if __name__ == "__main__":
    # Установка зависимостей (выполнить один раз):
    # pip install requests pandas tqdm
    
    main()
