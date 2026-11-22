#!/usr/bin/env python3
"""さくらのAI Engine 疎通確認・利用可能モデル一覧取得スクリプト。"""

import os
import sys
from openai import OpenAI

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.config import get_settings


def main() -> int:
    settings = get_settings()
    if not settings.sakura_ai_api_key or settings.sakura_ai_api_key == "your_sakura_ai_account_token_here":
        print("ERROR: .env の SAKURA_AI_API_KEY を設定してください。", file=sys.stderr)
        return 1

    client = OpenAI(
        base_url=settings.sakura_ai_base_url,
        api_key=settings.sakura_ai_api_key,
        timeout=30.0,
    )

    print("=== 利用可能モデル一覧 (GET /v1/models) ===")
    models = client.models.list()
    for m in models.data:
        print(f"- {m.id}")

    print(f"\n=== チャット疎通テスト (model={settings.sakura_ai_model}) ===")
    resp = client.chat.completions.create(
        model=settings.sakura_ai_model,
        messages=[
            {"role": "user", "content": "『接続成功』とJSON形式 {\"status\": \"ok\"} で返してください。"}
        ],
        temperature=0.0,
    )
    print(resp.choices[0].message.content)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
