"""Debug SVD recommendations."""
import os, sys, pandas as pd
sys.path.insert(0, '.')
from ml_pipeline.config import PROCESSED_DATA_DIR, MODEL_DIR
from ml_pipeline.models.matrix_factorization import SVDRecommender

user2idx_df = pd.read_parquet(os.path.join(PROCESSED_DATA_DIR, "user2idx.parquet"))
track2idx_df = pd.read_parquet(os.path.join(PROCESSED_DATA_DIR, "track2idx.parquet"))
all_interactions = pd.read_parquet(os.path.join(PROCESSED_DATA_DIR, "all_interactions.parquet"))

user_seen = all_interactions.groupby("user_id")["track_id"].apply(set).to_dict()

svd = SVDRecommender()
svd.load()
print("SVD user2idx len:", len(svd.user2idx))
print("SVD track2idx len:", len(svd.track2idx))

# Test for a specific user
test_uid = list(user2idx_df["user_id"])[0]
print(f"Testing user_id={test_uid}, seen_items={len(user_seen.get(test_uid, set()))}")
recs = svd.recommend(test_uid, top_k=5, seen_items=user_seen.get(test_uid, set()))
print(f"Recs: {recs}")

# Try without excluding seen
recs_all = svd.recommend(test_uid, top_k=5, exclude_seen=False)
print(f"Recs (no exclude): {recs_all}")
