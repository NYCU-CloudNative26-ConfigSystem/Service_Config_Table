# Config Table Service

高可維護性的 Config Table 微服務，使用 FastAPI、PostgreSQL 和 Redis。

## 概述

Config Table Service 負責管理 **Key-Value 配對映射表**，每筆記錄包含：

| 欄位 | 說明 |
|------|------|
| `from_id` | Key ID（來自 Config Service） |
| `to_id` | Value ID（來自 Config Service） |
| `creator` | 建立者的用戶名 |
| `company` | 建立者所屬公司 |
| `create_time` | 建立時間（UTC） |

## 技術棧

- **FastAPI**：現代、快速的 Python Web 框架
- **PostgreSQL**：存儲 config table 記錄（靜態數據）
- **Redis**：會話管理（動態數據）
- **JWT**：安全令牌認證（與 Service_Login 共用 SECRET_KEY）
- **Alembic**：資料庫遷移管理

## 架構設計

### 項目結構

```
Service_Config_Table/
├── app/
│   ├── core/                    # 核心配置和異常
│   │   ├── config.py            # 應用配置（pydantic-settings）
│   │   ├── exceptions.py        # 自定義 HTTP 異常
│   │   └── logging.py           # 日誌配置
│   ├── models/                  # SQLAlchemy 數據模型
│   │   └── config_table.py      # ConfigTable ORM 模型
│   ├── schemas/                 # Pydantic 驗證模型
│   │   └── config_table.py      # 請求/響應模型
│   ├── database/                # 數據庫連接
│   │   ├── connection.py        # PostgreSQL 異步連接
│   │   └── redis.py             # Redis 客戶端（單例）
│   ├── services/                # 業務邏輯層
│   │   └── config_table_service.py
│   ├── routers/                 # API 路由
│   │   ├── auth.py              # JWT 令牌端點（開發用）
│   │   ├── config_table.py      # Config Table CRUD 端點
│   │   └── deps.py              # FastAPI 依賴（JWT 驗證）
│   └── utils/                   # 工具函數
│       ├── security.py          # JWT 加密
│       └── config_service_client.py  # Config Service API 客戶端
├── alembic/                     # 資料庫遷移
│   └── versions/
│       └── 0001_create_config_table.py
├── tests/                       # 測試
│   ├── conftest.py
│   └── test_config_table.py
├── main.py                      # FastAPI 應用入口
├── docker-compose.yml
├── Dockerfile
├── Makefile
├── alembic.ini
├── requirements.txt
└── .env.example
```

## 快速開始

### 使用 Docker Compose（推薦）

1. **複製環境配置**

```bash
cp .env.example .env
# 編輯 .env，確保 SECRET_KEY 與 Service_Login 一致
```

2. **啟動服務**

```bash
docker compose up -d --build
```

預設會直接將主機埠 `${APP_HOST_PORT}`（預設 `18001`）映射到容器 `18001`。
可用以下命令確認：

```bash
docker compose ps
# 預期看到類似：0.0.0.0:18001->18001/tcp
```

3. **訪問應用**

- API 文檔：http://localhost:18001/docs
- 健康檢查：http://localhost:18001/health
- 若你在 `.env` 修改 `APP_HOST_PORT`，請把 URL 中的 `18001` 換成該值

若無法連線，請依序檢查：

```bash
# 1) 確認 app 容器有在跑
docker compose ps app

# 2) 查看 app 啟動錯誤（常見是 DB/Redis 尚未就緒）
docker compose logs app --tail=100

# 3) 確認主機埠沒有被佔用，或改用其他埠
# .env
APP_HOST_PORT=18002
docker compose down
docker compose up -d
```

### 本地開發

1. **創建虛擬環境並安裝依賴**

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

2. **配置環境變數**

```bash
cp .env.example .env
```

3. **啟動資料庫服務**

```bash
docker compose up -d postgres redis
```

4. **執行資料庫遷移**

```bash
make migrate
```

5. **啟動應用**

```bash
make run
# 或直接: uvicorn main:app --reload --host 0.0.0.0 --port 18001
```

## API 端點

所有端點前綴為 `/api/v1`。認證端點除外，其餘所有端點均需要 Bearer JWT 令牌。

### 認證（開發用）

#### 取得 JWT 令牌

```
POST /api/v1/auth/token
Content-Type: application/x-www-form-urlencoded

username=alice&password=secret&client_id=acme

Response (200):
{
  "access_token": "eyJ0eXAiOiJKV1QiLC...",
  "token_type": "bearer"
}
```

> **注意**：在生產環境中，令牌由 **Service_Login** 頒發；此端點僅供獨立測試使用。

### Config Table

#### 建立 Config Table Entry

```
POST /api/v1/configs/
Authorization: Bearer {access_token}
Content-Type: application/json

{
  "from_id": "key-001",
  "to_id":   "val-001",
  "company": "acme-corp"
}

Response (201):
{
  "id":          "550e8400-...",
  "from_id":     "key-001",
  "to_id":       "val-001",
  "creator":     "alice",
  "company":     "acme-corp",
  "create_time": "2026-05-13T10:00:00Z"
}
```

#### 查詢 Config Table Entries

```
GET /api/v1/configs/?skip=0&limit=100&creator=alice&company=acme-corp
Authorization: Bearer {access_token}
```

#### 取得單筆 Entry

```
GET /api/v1/configs/{entry_id}
Authorization: Bearer {access_token}
```

#### 更新 Entry（append-only，僅建立者）

```
PUT /api/v1/configs/{entry_id}
Authorization: Bearer {access_token}
Content-Type: application/json

{
  "to_id": "val-002"
}

Response (201):
{
  "id":          "a-new-uuid-...",
  "from_id":     "key-001",
  "to_id":       "val-002",
  "creator":     "alice",
  "company":     "acme-corp",
  "create_time": "2026-05-13T10:05:00Z"
}
```

> **說明**：此服務採用不可變資料模式；更新不會覆寫舊資料，而是新增一筆新 row（新 `id`）。

## 資料庫遷移

```bash
make migrate                          # 升級到最新版本
make migrate-down                     # 回滾一個版本
make migrate-new message="add column" # 自動生成新遷移
```

## 安全特性

- **JWT 驗證**：與 Service_Login 共用 `SECRET_KEY`，tokens 互通
- **所有者保護**：只有建立者可以用「更新（新增新版本）」語義建立自己的後續 entry
- **Config Service 驗證**：建立/更新時驗證 Key ID 和 Value ID 是否存在（Config Service 不可達時 fail-open，防止單點故障）
- **輸入驗證**：Pydantic 嚴格校驗所有請求欄位

## 測試

```bash
make test
# 或: pytest tests/ -v
```

## 配置

所有配置通過環境變量管理（見 `.env.example`）：

```env
DATABASE_URL=postgresql://user:password@localhost:5432/config_table_db
REDIS_URL=redis://localhost:6379/0
SECRET_KEY=your-super-secret-key-change-in-production  # 必須與 Service_Login 一致
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
CONFIG_SERVICE_URL=http://config-service:8000
LOG_LEVEL=INFO
```
