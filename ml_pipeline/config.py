"""ML Pipeline configuration."""
import os

# Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
MODEL_DIR = os.path.join(DATA_DIR, "models")
RAW_DATA_DIR = os.path.join(DATA_DIR, "raw")
PROCESSED_DATA_DIR = os.path.join(DATA_DIR, "processed")

# Create directories
for d in [DATA_DIR, MODEL_DIR, RAW_DATA_DIR, PROCESSED_DATA_DIR]:
    os.makedirs(d, exist_ok=True)

# Model hyperparameters
EMBEDDING_DIM = 64
HIDDEN_DIMS = [256, 128, 64]
LEARNING_RATE = 1e-3
BATCH_SIZE = 256
EPOCHS = 20
MAX_SEQ_LEN = 50
TOP_K = 20
NEG_SAMPLE_RATIO = 4
COMPLETION_RATE_THRESHOLD = 0.3  # Below this = negative sample
