import boto3
import pandas as pd
import io
import os
import logging
import re
from collections import defaultdict
from sqlalchemy import create_engine, MetaData, Table, Column
from sqlalchemy.types import String, Integer, Float, DateTime, Boolean

logger = logging.getLogger()
logger.setLevel(logging.INFO)

S3_BUCKET = os.environ["S3_BUCKET"]
S3_PREFIX = os.environ.get("S3_PREFIX", "gold/")
PG_CONN = os.environ["PG_CONN"]
s3 = boto3.client("s3")


def list_parquet_files():
    logger.info("Listing S3 parquet files...")

    paginator = s3.get_paginator("list_objects_v2")

    files = []
    for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=S3_PREFIX):
        for obj in page.get("Contents", []):
            if obj["Key"].endswith(".parquet"):
                files.append(obj)

    logger.info(f"Found {len(files)} parquet files")
    return files


def get_latest_per_metric(files):
    grouped = defaultdict(list)

    for f in files:
        key = f["Key"]
        parts = key.split("/")

        if len(parts) < 2:
            continue

        metric = parts[1]
        grouped[metric].append(f)

    latest = {}
    for metric, items in grouped.items():
        latest_file = max(items, key=lambda x: x["LastModified"])
        latest[metric] = latest_file["Key"]

    logger.info(f"Resolved latest files for {len(latest)} metrics")
    return latest


def read_parquet(key):
    logger.info(f"Reading parquet: {key}")

    obj = s3.get_object(Bucket=S3_BUCKET, Key=key)
    return pd.read_parquet(io.BytesIO(obj["Body"].read()))


POSSIBLE_KEYS = ["id", "post_id", "user_id", "username"]


def detect_pk(df):
    for k in POSSIBLE_KEYS:
        if k in df.columns:
            return k
    return None


def infer_sql_type(series):
    if pd.api.types.is_integer_dtype(series):
        return Integer()
    if pd.api.types.is_float_dtype(series):
        return Float()
    if pd.api.types.is_bool_dtype(series):
        return Boolean()
    if pd.api.types.is_datetime64_any_dtype(series):
        return DateTime()
    return String()


def normalize_pg_conn(conn_str):
    if conn_str.startswith("postgresql+psycopg2://"):
        return conn_str.replace("postgresql+psycopg2://", "postgresql+pg8000://", 1)
    if conn_str.startswith("postgresql://"):
        return conn_str.replace("postgresql://", "postgresql+pg8000://", 1)
    if conn_str.startswith("postgres://"):
        return conn_str.replace("postgres://", "postgresql+pg8000://", 1)
    return conn_str


def sanitize_table_name(name):
    return re.sub(r"[^a-zA-Z0-9_]", "_", name)


def create_table_if_not_exists(engine, table_name, df, pk):
    metadata = MetaData()

    columns = []
    for col in df.columns:
        col_type = infer_sql_type(df[col])

        if col == pk:
            columns.append(Column(col, col_type, primary_key=True))
        else:
            columns.append(Column(col, col_type))

    table = Table(table_name, metadata, *columns)
    metadata.create_all(engine)

    logger.info(f"Table ensured: {table_name}")
    return table


def batch_upsert(engine, df, table_name, pk):
    logger.info(f"Upserting {len(df)} rows into {table_name}")

    cols = list(df.columns)
    update_cols = [c for c in cols if c != pk]

    rows = [tuple(x) for x in df.to_numpy()]

    chunk_size = 1000

    with engine.begin() as conn:
        for i in range(0, len(rows), chunk_size):
            batch = rows[i:i + chunk_size]

            update_clause = ""
            if update_cols:
                update_clause = ",".join([f"{c}=EXCLUDED.{c}" for c in update_cols])

            insert_sql = f"""
                INSERT INTO {table_name} ({",".join(cols)})
                VALUES ({",".join(["%s"] * len(cols))})
                ON CONFLICT ({pk})
                {"DO UPDATE SET " + update_clause if update_clause else "DO NOTHING"}
            """

            conn.exec_driver_sql(insert_sql, batch)

            logger.info(f"Inserted batch {i + len(batch)}/{len(rows)}")

    logger.info(f"Finished upsert for {table_name}")


def lambda_handler(event, context):

    logger.info("Lambda started")

    engine = create_engine(normalize_pg_conn(PG_CONN), pool_pre_ping=True)

    files = list_parquet_files()
    latest_files = get_latest_per_metric(files)

    results = []

    for metric, key in latest_files.items():
        try:
            table_name = sanitize_table_name(metric)
            logger.info(f"Processing metric: {metric} as table {table_name}")

            df = read_parquet(key)

            if df.empty:
                continue

            pk = detect_pk(df)

            if pk is None:
                raise Exception(f"No primary key found for metric {metric}")

            create_table_if_not_exists(engine, table_name, df, pk)

            df = df.drop_duplicates(subset=[pk])

            batch_upsert(engine, df, table_name, pk)

            results.append({
                "metric": table_name,
                "file": key,
                "rows": len(df),
                "pk": pk
            })

        except Exception as e:
            logger.error(f"Error processing {metric}: {str(e)}")
            continue

    logger.info("Lambda finished")

    return {
        "status": "success",
        "processed": results
    }