from db import supabase

def calculate_injury_compensation(hospitalization_months: int, outpatient_months: int, type: str) -> int:
    if type == "軽傷":
        result = supabase.table("minor_injury_compensation").select("*").eq("hospitalization_months", hospitalization_months).eq('outpatient_months', outpatient_months).single().execute()
        return result.data["amount"] if result.data else 0
    elif type == "重傷":
        print(f"hospitalization_months: {hospitalization_months}, outpatient_months: {outpatient_months}")
        result = supabase.table("severe_injury_compensation").select("*").eq("hospitalization_months", hospitalization_months).eq('outpatient_months', outpatient_months).single().execute()
        return result.data["amount"] if result.data else 0

    return 0

def calculate_auto_injury_compensation(treatment_days: int, visit_days: int) -> int:
    applicable_days = min(treatment_days, visit_days * 2)
    return min(applicable_days * 4300, 1200000)

def calculate_death_compensation(role: str) -> int:
    result = supabase.table("death_compensation").select("*").eq("role", role).single().execute() 
    return result.data["amount"] if result.data else 0

def calculate_auto_death_compensation(dependents: int, relatives: int) -> int:
    result = 4000000
    if dependents > 0:
        result += 2000000
    if relatives > 2:
        result += 7500000
    elif relatives > 1:
        result += 6500000
    elif relatives > 0:
        result += 5500000
    return result

def calculate_lost_income(income: int, days: int) -> int:
    day_income = 0
    if income <= 0:
        day_income = 10,800
    else :
        day_income = income / 365;
    return int(day_income * days)

def calculate_auto_lost_income(days: int) -> int:
    return 6100 * days

def calculate_disability_compensation(grade: int):
    result = supabase.table("disability_compensation").select("*").eq("grade", grade).single().execute()
    return result.data

def calculate_lost_profits(income: int, age: int, grade: int, type: str) -> int:
    disability_loss_result = supabase.table("disability_loss_table").select("*").eq("disability_grade", grade).single().execute()
    life_expectancy_coefficient = supabase.table("life_expectancy_coefficients").select("*").eq("age", age).single().execute()
    if income <= 0:
        return int(10,800 * disability_loss_result.data["work_loss_percent"] * life_expectancy_coefficient.data["coefficient"])
    else:
        return int(income * disability_loss_result.data["work_loss_percent"] * life_expectancy_coefficient.data["coefficient"])
    
def calculate_death_lost_profits(income: int, position: str, gender: str, dependents: int, age: int) -> int:
    living_deduction_rate = 0
    if position == "一家の支柱" and dependents > 1:
        living_deduction_rate = 0.3
    elif position == "一家の支柱" and dependents == 1:
        living_deduction_rate = 0.4
    elif gender == '男性':
        living_deduction_rate = 0.5
    else:
        living_deduction_rate = 0.3
    
    life_expectancy_coefficient = supabase.table("life_expectancy_coefficients").select("*").eq("age", age).single().execute()
    if income <= 0:
        return 10,800 * (1 - living_deduction_rate) * life_expectancy_coefficient.data["coefficient"]
    else:
        return income * (1 - living_deduction_rate) * life_expectancy_coefficient.data["coefficient"]
    

def get_user_response_dict(user_id: str) -> dict:
    """
    特定ユーザーの user_responses を id: response 形式で取得
    """
    try:
        res = supabase.table("user_responses")\
            .select("id, response")\
            .eq("user_id", user_id)\
            .execute()

        if not res.data:
            return {}

        return {item["key"]: item["response"] for item in res.data}

    except Exception as e:
        print(f"エラー: {e}")
        return {}