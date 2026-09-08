"""D1：将 Olist 巴西电商数据集（CSV）导入 SQLite 单文件数据库。

用法:
    python scripts/import_data.py                 # 导入 8 张业务表（默认，部署推荐）
    python scripts/import_data.py --with-geolocation  # 额外导入 geolocation（约 100 万行，体积 ~100MB）

说明:
    - 源数据目录: brazilian-ecommerce/（Kaggle 原版 CSV）
    - 输出数据库: data/ecommerce.db
    - 表名: 去掉 olist_ 前缀与 _dataset 后缀（如 olist_orders_dataset -> orders）
    - geolocation（地理定位）为可选扩展：导入后数据库体积从 ~25MB 增至 ~130MB，
      超过 GitHub 单文件 100MB 限制，不利于代码仓库托管/线上部署，因此默认不导入；
      PRD 6.1 的 8 张业务表完全足够支撑 NL2SQL 演示与评测。
    - 所有字段按原始文本导入，日期/数值在查询时用 SQLite 函数处理，
      保证与 Kaggle 原始数据完全一致，便于后续评测对标。
"""
import argparse
import sqlite3
from pathlib import Path

import pandas as pd

# 项目根目录
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "brazilian-ecommerce"
DB_PATH = ROOT / "data" / "ecommerce.db"

# 8 张业务表（PRD 6.1）：CSV 文件名 -> 目标表名
FILE_TABLE_MAP = {
    "olist_orders_dataset.csv": "orders",
    "olist_order_items_dataset.csv": "order_items",
    "olist_customers_dataset.csv": "customers",
    "olist_sellers_dataset.csv": "sellers",
    "olist_order_payments_dataset.csv": "order_payments",
    "olist_order_reviews_dataset.csv": "order_reviews",
    "olist_products_dataset.csv": "products",
    "product_category_name_translation.csv": "product_category_name_translation",
}
# 可选扩展表（需 --with-geolocation）
GEOLOCATION_CSV = "olist_geolocation_dataset.csv"
GEOLOCATION_TABLE = "geolocation"


def import_csv(csv_path: Path, table: str, conn: sqlite3.Connection) -> int:
    """读取 CSV 并写入 SQLite 表，返回写入行数。"""
    # 统一按文本读入，避免邮编前导零 / 数值精度被 pandas 改写
    df = pd.read_csv(csv_path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    df = df.replace({"": None})
    df.to_sql(table, conn, if_exists="replace", index=False, chunksize=10000)
    print(f"  ✔ {table:32s} {len(df):>10,} 行")
    return len(df)


def main() -> None:
    ap = argparse.ArgumentParser(description="Olist CSV → SQLite 导入")
    ap.add_argument("--with-geolocation", action="store_true",
                    help="额外导入 geolocation 地理表（约 +100MB）")
    args = ap.parse_args()

    if not DATA_DIR.is_dir():
        raise FileNotFoundError(f"未找到数据目录: {DATA_DIR}，请将 Olist CSV 放入该目录")

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()  # 重建，保证幂等

    print(f"创建数据库: {DB_PATH}\n")
    conn = sqlite3.connect(DB_PATH)
    try:
        total = 0
        files = dict(FILE_TABLE_MAP)
        if args.with_geolocation:
            files[GEOLOCATION_CSV] = GEOLOCATION_TABLE
        for filename, table in files.items():
            csv_path = DATA_DIR / filename
            if not csv_path.exists():
                print(f"  ⚠ 跳过缺失文件: {filename}")
                continue
            total += import_csv(csv_path, table, conn)
        conn.commit()

        print(f"\n导入完成，共 {total:,} 行。数据库中的表：")
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ):
            name = row[0]
            (cnt,) = conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()
            print(f"  - {name}: {cnt:,} 行")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
