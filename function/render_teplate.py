import re
from collections import defaultdict
from db import supabase


def extract_placeholders(template: str) -> set:
    """{table.column} のプレースホルダを全て抽出"""
    return set(re.findall(r"{([\w]+\.[\w]+)}", template))

def render_template(template: str, values: dict) -> str:
    """値を埋め込んでテンプレートをレンダリング"""
    def replacer(match):
        table_col = match.group(1)
        table, col = table_col.split(".")
        return str(values.get(table, {}).get(col, f"{{{table_col}}}"))  # 未知ならそのまま残す

    return re.sub(r"{([\w]+\.[\w]+)}", replacer, template)

def fetch_data_for_template(placeholders: set, account_id: str) -> dict:
    """テンプレートに必要なテーブルをSupabaseから取得"""
    table_columns = defaultdict(set)

    # テーブルごとに使われているカラム名を集める
    for ph in placeholders:
        table, column = ph.split(".")
        table_columns[table].add(column)

    results = {}

    for table, columns in table_columns.items():
        # account_id を持つテーブルだけに限定（必要に応じて他条件も）
        if table == "accounts":
            response = supabase.table(table).select("*").eq("id", account_id).maybe_single().execute()
        else:
            response = supabase.table(table).select("*").eq("account_id", account_id).maybe_single().execute()

        if response.data:
            results[table] = response.data
        else:
            results[table] = {}

    return results