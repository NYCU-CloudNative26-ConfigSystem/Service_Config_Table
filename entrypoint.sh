#!/bin/sh
set -e

# Wait for postgres and ensure the target database exists before running migrations.
# This handles cold starts and cases where the postgres init script didn't create the DB.
echo "Waiting for postgres and ensuring database exists..."
until python - <<'PYEOF'
import os, sys, asyncio, asyncpg

raw = os.environ.get("DATABASE_URL", "")
for prefix in ("postgresql+asyncpg://", "postgresql://", "postgres://"):
    if raw.startswith(prefix):
        rest = raw[len(prefix):]
        break
else:
    print("No recognizable DATABASE_URL", file=sys.stderr)
    sys.exit(1)

# rest = "user:pass@host:port/dbname"
db_name = rest.rstrip("/").rsplit("/", 1)[-1]
admin_dsn = "postgresql://" + rest.rsplit("/", 1)[0] + "/postgres"

async def ensure():
    conn = await asyncpg.connect(admin_dsn, timeout=5)
    exists = await conn.fetchval(
        "SELECT 1 FROM pg_database WHERE datname=$1", db_name
    )
    if not exists:
        await conn.execute(f"CREATE DATABASE {db_name}")
        print(f"Created database {db_name}")
    else:
        print(f"Database {db_name} exists")
    await conn.close()

asyncio.run(ensure())
PYEOF
do
  echo "  postgres not ready, retrying in 3s..."
  sleep 3
done

alembic upgrade head
exec uvicorn main:app --host 0.0.0.0 --port 18001
