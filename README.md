# sakura-ai-pfc-planner

自宅の調理器具制約（IHコンロ1口・電子レンジ・オーブン・クッキングケトル等）と手持ち・宅配の食材リストから、**高タンパク・低脂質（PFC重視）＆初心者向け・洗い物最小の7日間献立プラン**を自動生成する Web アプリケーションです。

**さくらのAI Engine（OpenAI互換API）** × **FastAPI / Pydantic 機械検証＆自己修正リトライ** × **さくらのVPS（Docker Compose + Caddy）** で構成しています。

## 主な特徴

- **調理器具の物理制約を厳守**: IHコンロ1口での同時並行コンロ調理や、選択していない器具の使用をシステムプロンプト＋Pydanticバリデータで二重防止
- **Pydantic による構造化検証＋自己修正リトライ**: スキーマ違反・禁止器具・栄養レンジ異常を検知した場合、エラー理由を添えて自動リトライ
- **無償枠（月3,000リクエスト）を守る運用ガード**: SQLite による同一入力キャッシュ、IP別レート制限、月間ソフトストップを標準装備
- **Zenn読者向けワンクリック体験**: サンプル食材セットボタン＆Markdownコピー機能付き

## クイックスタート（ローカル開発）

```bash
cp .env.example .env
# .env に SAKURA_AI_API_KEY を設定してください

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# ユニットテスト
pytest

# 開発サーバ起動
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

ブラウザで `http://localhost:8000` を開いて動作確認できます。

## さくらのAI Engine 疎通・モデル確認

```bash
python scripts/check_sakura_ai.py
```

## 本番デプロイ（さくらのVPS + Docker Compose）

```bash
cp .env.example .env
# .env に SAKURA_AI_API_KEY と APP_DOMAIN を設定
docker compose up -d --build
```
