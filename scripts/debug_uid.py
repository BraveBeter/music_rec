"""Debug user2idx key types."""
import os, sys, pandas as pd
sys.path.insert(0, '.')
from ml_pipeline.config import PROCESSED_DATA_DIR

user2idx_df = pd.read_parquet(os.path.join(PROCESSED_DATA_DIR, "user2idx.parquet"))
print("parquet dtypes:", user2idx_df.dtypes.to_dict())
print("first row:", user2idx_df.iloc[0].to_dict())
print("key type from dict:", type(list(dict(user2idx_df.values).keys())[0]))

test = pd.read_parquet(os.path.join(PROCESSED_DATA_DIR, "test.parquet"))
print("test user_id dtype:", test["user_id"].dtype)
print("test user_id sample:", type(test["user_id"].iloc[0]))

# Test lookup
user2idx = {int(k): int(v) for k, v in user2idx_df.values}
test_uid = test["user_id"].iloc[0]
print(f"Lookup {test_uid} (type={type(test_uid)}): {user2idx.get(int(test_uid))}")
print("Keys sample:", list(user2idx.keys())[:5])
