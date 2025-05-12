from fastapi import APIRouter
from datetime import datetime
from db import supabase
from dateutil.parser import parse

router = APIRouter()

@router.get("/calculate")
async def generate_result_message(responses):
    
    question_id_dict = {
        'disablity_id': 'b796ac9c-31a7-4af4-9ab8-180976b32c20',
        'gender_id': '46171ff3-212d-4771-9757-4a5e0e50d50b', 
        'income_id': 'c3856e91-d602-48ce-a398-18ecff70d1ef', 
        'marital_status_id': '2d98f15a-a964-46c5-8dba-4a18e0d6a7bc',
        'victim_id': 'a0d898ab-1a9f-4dc1-8bf7-82667181c548',
        'accident_id': '7c0294cb-a6ab-4e38-afd4-3e0039d2f8ab',
        'injury_id': 'c9edae43-b444-4ff1-8eac-9b9c6eaa926b',
        'treatment_status_id': '614ff372-98b9-4de2-9b1f-0fd000dc758d',
        'has_income_id': '99fc3515-70bb-4699-9658-e8ca12c0ffce',
        'hospitalization_id': '62f108be-a166-4ead-81d9-e59957fb99e1',
        'outpatient_id': '98d4ceca-c229-476e-9454-d95bb1d24d65',
        'actual_outpatient_id': 'e0bc0d91-1587-40df-97c2-a955a96bf6c8',
        'day_off_id': '48eefe11-6f5e-4a87-964a-d4683dbb2d53',
        'age_id': 'f0a157e8-b9ea-44f0-ab6e-25554bdeff40',
        'role_id': '1cab33c2-0cce-4f6d-92ef-6b46b9f58537',
        'dependents_id': '7b1ac05b-1e88-4b43-8ca6-2f35734ae332',
    }
    
    type = responses.get(question_id_dict.get('accident_id'))
    
    text = ""
    
    if type == "死亡":
        death_compensation = calculate_death_compensation(responses.get(question_id_dict.get('role_id')))
        relatives = int(responses.get(question_id_dict.get('dependents_id')))
        if responses.get(question_id_dict.get('marital_status_id')) == "既婚":
            relatives += 1
        
        auto_death_compensation = calculate_auto_death_compensation(int(responses.get(question_id_dict.get('dependents_id'))), relatives)
        
        death_lost_profits = calculate_death_lost_profits(
            int(responses.get(question_id_dict.get('income_id'))) * 10000,
            responses.get(question_id_dict.get('role_id')),
            responses.get(question_id_dict.get('gender_id')),
            int(responses.get(question_id_dict.get('dependents_id'))),
            int(responses.get(question_id_dict.get('age_id'))),
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
        
    else:
        injury_compensation = calculate_injury_compensation(int(responses.get(question_id_dict.get('hospitalization_id'))) // 30, int(responses.get(question_id_dict.get('actual_outpatient_id'))) // 30, type)
        auto_injury_compensation = calculate_auto_injury_compensation(int(responses.get(question_id_dict.get('outpatient_id'))), int(responses.get(question_id_dict.get('actual_outpatient_id'))))
        
        lost_income = calculate_lost_income(int(responses.get(question_id_dict.get('income_id'))) * 10000, int(responses.get(question_id_dict.get('day_off_id'))))
        auto_lost_income = calculate_auto_lost_income(int(responses.get(question_id_dict.get('day_off_id'))))
        
        disability_compensation_data = calculate_disability_compensation(int(responses.get(question_id_dict.get('disablity_id'))))
        disability_compensation = disability_compensation_data["amount_lawyer"]
        auto_disability_compensation = disability_compensation_data["amount_auto"]
        
        lost_profits = calculate_lost_profits(int(responses.get(question_id_dict.get('income_id'))) * 10000, int(responses.get(question_id_dict.get('age_id'))), int(responses.get(question_id_dict.get('disablity_id'))), type)
        
        auto_disability_limit = supabase.table("auto_limit_amounts").select("amount").eq("grade", int(responses.get(question_id_dict.get('disablity_id')))).single().execute()
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
    
    return {'message': text}