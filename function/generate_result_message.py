from utils_calculate import (
    calculate_injury_compensation,
    calculate_auto_injury_compensation,
    calculate_death_compensation,
    calculate_auto_death_compensation,
    calculate_lost_income,
    calculate_auto_lost_income,
    calculate_disability_compensation,
    calculate_lost_profits,
    calculate_death_lost_profits
)
from db import supabase

from gspread import Worksheet

def generate_result_message(responses, user_id, sheet: Worksheet = None):
    
    type = responses.get('accident_type')
    
    text = ""
    
    if type == "死亡":
        death_compensation = calculate_death_compensation(responses.get('role'))
        relatives = int(responses.get('dependents'))
        if responses.get('marital_status') == "既婚":
            relatives += 1
        
        auto_death_compensation = calculate_auto_death_compensation(int(responses.get('dependents')), relatives)
        
        death_lost_profits = calculate_death_lost_profits(
            int(responses.get('income')) * 10000,
            responses.get('role'),
            responses.get('gender'),
            int(responses.get('dependents')),
            int(responses.get('age')),
        )
        
        auto_death_lost_profits = death_lost_profits
        
        if auto_death_compensation + auto_death_lost_profits > 30000000:
            auto_death_lost_profits = 30000000 - auto_death_compensation
        
        
        total = death_compensation + death_lost_profits
        auto_total = auto_death_compensation + auto_death_lost_profits
        
        text = (f"診断結果\n\n"
            f"✓死亡慰謝料\n"
            f"（弁護士基準）: {death_compensation // 10000:,} 万円\n"
            f"（自賠責基準）: {auto_death_compensation // 10000:,} 万円\n"
            f"✓逸失利益\n"
            f"（弁護士基準）: {death_lost_profits // 10000:,} 万円\n"
            f"（自賠責基準）: {auto_death_lost_profits // 10000:,} 万円\n"
            f"✓総額\n"
            f"（弁護士基準）: {total // 10000:,} 万円\n"
            f"（自賠責基準）: {auto_total // 10000:,} 万円\n\n"
            f"自賠責基準の場合、慰謝料{auto_total // 10000:,}万円のところ、弁護士に依頼することで{(total - auto_total) // 10000 :,}万円増額の総額{total // 10000 :,}万円受け取ることができる可能性があります。\n"
            f"※こちらの結果はあくまで目安となります。詳しくは弁護士にご相談ください。"
        )
        
        if sheet: 
            # === スプレッドシート処理 ===
            keys = ["death_compensation", "auto_death_compensation", "death_lost_profits", "auto_death_lost_profits", "total", "auto_total"]
            values = [death_compensation, auto_death_compensation, death_lost_profits, auto_death_lost_profits, total, auto_total]
            if sheet:
                
                all_rows = sheet.get_all_values()

                header = all_rows[0]  # 2行目がヘッダー
                user_col_index = header.index("id")
                
                # 3行目以降で user_id を探す
                user_row_index = None
                for idx, row in enumerate(all_rows[2:], start=3):
                    if len(row) > user_col_index and row[user_col_index] == user_id:
                        # 対象のセルを更新（1-based）
                        user_row_index = idx
                        
                if user_row_index is None:
                    raise ValueError(f"user_id '{user_id}' は見つかりませんでした")
                
                for key, value in zip(keys, values):
                    
                    if key not in header:
                        raise ValueError(f"'{key}' カラムが見つかりません")

                    key_col_index = header.index(key)
                    sheet.update_cell(user_row_index, key_col_index + 1, value)

        
    else:
        injury_compensation = calculate_injury_compensation(int(responses.get('hospitalization')) // 30, int(responses.get('actual_outpatient')) // 30, type)
        auto_injury_compensation = calculate_auto_injury_compensation(int(responses.get('outpatient')), int(responses.get('actual_outpatient')))
        
        lost_income = calculate_lost_income(int(responses.get('income'))* 10000, int(responses.get('day_off')))
        auto_lost_income = calculate_auto_lost_income(int(responses.get('day_off')))
        
        disability_compensation_data = calculate_disability_compensation(int(responses.get('disability')))
        disability_compensation = disability_compensation_data["amount_lawyer"]
        auto_disability_compensation = disability_compensation_data["amount_auto"]
        
        lost_profits = calculate_lost_profits(int(responses.get('income')) * 10000, int(responses.get('age')), int(responses.get('disability')), type)
        
        auto_disability_limit = supabase.table("auto_limit_amounts").select("amount").eq("grade", int(responses.get('disability'))).single().execute()
        auto_lost_profits = lost_profits
        
        if auto_disability_compensation + auto_lost_profits > auto_disability_limit.data["amount"]:
            auto_lost_profits = auto_disability_limit.data["amount"] - auto_disability_compensation
        
        total = injury_compensation + lost_income + disability_compensation + lost_profits
        auto_total = auto_injury_compensation + auto_lost_income + auto_disability_compensation + auto_lost_profits
        
        text = (f"診断結果\n\n"
            f"✓入通院慰謝料\n"
            f"（弁護士基準）: {injury_compensation // 10000:,} 万円\n"
            f"（自賠責基準）: {auto_injury_compensation // 10000:,} 万円\n"
            f"✓休業損害\n"
            f"（弁護士基準）: {lost_income // 10000:,} 万円\n"
            f"（自賠責基準）: {auto_lost_income // 10000:,} 万円\n"
            f"✓後遺障害慰謝料\n"
            f"（弁護士基準）: {disability_compensation // 10000:,} 万円\n"
            f"（自賠責基準）: {auto_disability_compensation // 10000:,} 万円\n"
            f"✓逸失利益\n"
            f"（弁護士基準）: {lost_profits // 10000:,} 万円\n"
            f"（自賠責基準）: {auto_lost_profits // 10000:,} 万円\n"
            f"✓総額\n"
            f"（弁護士基準）: {total // 10000:,} 万円\n"
            f"（自賠責基準）: {auto_total // 10000:,} 万円\n\n"
            f"自賠責基準の場合、慰謝料{auto_total // 10000:,}万円のところ、弁護士に依頼することで{(total - auto_total) // 10000 :,}万円増額の総額{total // 10000 :,}万円受け取ることができる可能性があります。\n"
            f"※こちらの結果はあくまで目安となります。詳しくは弁護士にご相談ください。"
        )
        
        if sheet:
            # === スプレッドシート処理 ===
            keys = ["injury_compensation", "auto_injury_compensation", "lost_income", "auto_lost_income", "disability_compensation", "auto_disability_compensation", "lost_profits", "auto_lost_profits", "total", "auto_total"]
            values = [injury_compensation, auto_injury_compensation, lost_income, auto_lost_income, disability_compensation, auto_disability_compensation, lost_profits, auto_lost_profits, total, auto_total]
            if sheet:
                
                all_rows = sheet.get_all_values()

                header = all_rows[0]  # 2行目がヘッダー
                user_col_index = header.index("id")
                
                # 3行目以降で user_id を探す
                user_row_index = None
                for idx, row in enumerate(all_rows[2:], start=3):
                    if len(row) > user_col_index and row[user_col_index] == user_id:
                        # 対象のセルを更新（1-based）
                        user_row_index = idx
                        
                if user_row_index is None:
                    raise ValueError(f"user_id '{user_id}' は見つかりませんでした")
                
                for key, value in zip(keys, values):
                    
                    if key not in header:
                        raise ValueError(f"'{key}' カラムが見つかりません")

                    key_col_index = header.index(key)
                    sheet.update_cell(user_row_index, key_col_index + 1, value)
    
    return text