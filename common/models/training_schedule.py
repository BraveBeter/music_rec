"""ORM model for training schedules (auto-retraining configuration)."""
from sqlalchemy import Column, Integer, String, SmallInteger, TIMESTAMP, text
from sqlalchemy.orm import DeclarativeBase
from common.database import Base


class TrainingSchedule(Base):
    __tablename__ = "training_schedules"

    schedule_id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    task_type = Column(String(50), nullable=False, comment="preprocess|train_baseline|train_sasrec|train_deepfm|train_all")
    schedule_type = Column(String(20), nullable=False, default="cron", comment="cron|interval|threshold")
    cron_expr = Column(String(100), nullable=True, comment="Cron expression for schedule_type=cron")
    interval_minutes = Column(Integer, nullable=True, comment="Interval in minutes for schedule_type=interval")
    threshold_interactions = Column(Integer, nullable=True, comment="Auto-trigger when new interactions exceed this count")
    is_enabled = Column(SmallInteger, nullable=False, default=1)
    last_run_at = Column(TIMESTAMP, nullable=True)
    next_run_at = Column(TIMESTAMP, nullable=True)
    created_at = Column(TIMESTAMP, nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    updated_at = Column(TIMESTAMP, nullable=False, server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"))


class TrainingThresholdState(Base):
    __tablename__ = "training_threshold_state"

    id = Column(Integer, primary_key=True, autoincrement=True)
    last_training_count = Column(Integer, nullable=False, default=0, comment="Interaction count at last training")
    updated_at = Column(TIMESTAMP, nullable=False, server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"))
