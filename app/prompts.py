from __future__ import annotations

from app.schemas import EQUIPMENT_LABELS, PlanRequest


SYSTEM_PROMPT = """あなたは「高タンパク・低脂質（PFC重視）」かつ「自宅の調理器具制約と料理初心者向け手順」を厳守する専属の栄養・献立プランナーです。

## 絶対に守るルール（Negative Constraints）
1. ユーザーが許可していない調理器具は絶対に使わないこと。
2. 許可器具が「IHコンロ（1口）」のみの場合、同時に2つの鍋・フライパンで火加減調理する工程は絶対に提案しないこと。
3. 揚げ物・高脂質メニュー・高度な包丁技術・洗い物が増える複雑な工程は禁止。ワンポット・電子レンジ・クッキングケトル・オーブンを活用した簡単手順にすること。
4. 傷みやすい冷蔵食材・青果（もやし、豆腐、葉物など）は前半の日程で優先的に使い切ること。
5. 出力は必ず指定されたJSONスキーマのみとし、余計な前置きやマークダウンの説明文を一切含めないこと。
"""


def build_user_prompt(req: PlanRequest) -> str:
    equipment_names = "、".join(EQUIPMENT_LABELS[eq] for eq in req.equipments)
    cycle_desc = (
        "Day 1は『夕食』のみ（お届け当日夕食スタート）、Day 2〜7は『朝食・昼食・夕食』、Day 8は『朝食・昼食』のみの計21食（丸7日間サイクル）"
        if req.start_timing == "dinner_start"
        else "Day 1〜7のそれぞれ『朝食・昼食・夕食』の計21食"
    )

    return f"""以下の条件と食材リストをもとに、7日間（計21食）の高タンパク・低脂質PFC献立プランをJSONで出力してください。

## 制約条件
- 1日あたり目標カロリー: 約 {req.target_calories} kcal（高タンパク・低脂質を最優先）
- 使用可能な調理器具: {equipment_names}（これ以外は使用禁止。火不要・調理不要は可）
- 調理スキル: 料理初心者向け（包丁最小限・キッチンバサミやカット済み活用・洗い物最小）
- 献立サイクル: {cycle_desc}

## 食材リスト
<ingredients>
{req.ingredients_text}
</ingredients>

## 出力JSONスキーマ（厳守）
{{
  "summary": "全体方針の簡潔な要約（2〜3文）",
  "assumptions": ["基本調味料・常備プロテイン等の前提条件"],
  "ingredient_usage": [
    {{"ingredient": "食材名", "schedule": "Day 1 夕食、Day 2 昼食で完食"}}
  ],
  "days": [
    {{
      "day": 1,
      "label": "Day 1（お届け日・夕食スタート）",
      "meals": [
        {{
          "slot": "夕食",
          "name": "メニュー名",
          "used_ingredients": ["食材A", "食材B"],
          "equipments": ["クッキングケトル"],
          "calories_kcal": 550,
          "protein_g": 35.0,
          "fat_g": 12.0,
          "carbs_g": 70.0,
          "steps": ["手順1", "手順2"]
        }}
      ],
      "daily_calories_kcal": 550,
      "daily_protein_g": 35.0,
      "daily_fat_g": 12.0,
      "daily_carbs_g": 70.0
    }}
  ]
}}
"""


def build_correction_prompt(violations: list[str]) -> str:
    bullet = "\n".join(f"- {v}" for v in violations)
    return f"""前回のJSON出力に以下の制約違反が見つかりました。違反箇所をすべて修正し、完全なJSONのみを再出力してください。

## 修正が必要な違反点
{bullet}
"""
