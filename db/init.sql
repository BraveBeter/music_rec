-- ============================================================
-- 音乐推荐系统 数据库初始化
-- ============================================================

USE music_rec;

-- 用户表
CREATE TABLE IF NOT EXISTS users (
    user_id      INT           PRIMARY KEY AUTO_INCREMENT,
    username     VARCHAR(50)   NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role         VARCHAR(20)   NOT NULL DEFAULT 'user',
    age          INT           NULL,
    gender       TINYINT       NULL COMMENT '0=未知, 1=男, 2=女',
    country      VARCHAR(50)   NULL,
    created_at   TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_login   TIMESTAMP     NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 歌曲表
CREATE TABLE IF NOT EXISTS tracks (
    track_id     VARCHAR(64)   PRIMARY KEY,
    title        VARCHAR(255)  NOT NULL,
    artist_name  VARCHAR(255)  NULL,
    album_name   VARCHAR(255)  NULL,
    release_year INT           NULL,
    duration_ms  INT           NULL,
    play_count   INT           NOT NULL DEFAULT 0,
    status       TINYINT       NOT NULL DEFAULT 1 COMMENT '1=正常, 0=已下架',
    preview_url  VARCHAR(512)  NULL COMMENT '试听音频URL',
    cover_url    VARCHAR(512)  NULL COMMENT '封面图URL',
    created_at   TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_status (status),
    INDEX idx_play_count (play_count DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 用户行为日志表
CREATE TABLE IF NOT EXISTS user_interactions (
    interaction_id  BIGINT        PRIMARY KEY AUTO_INCREMENT,
    user_id         INT           NOT NULL,
    track_id        VARCHAR(64)   NOT NULL,
    interaction_type TINYINT      NOT NULL COMMENT '1=play, 2=like, 3=skip, 4=rate',
    rating          FLOAT         NULL,
    play_duration   INT           NULL COMMENT '实际播放ms',
    completion_rate FLOAT         NULL COMMENT '播放完成度',
    created_at      TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (track_id) REFERENCES tracks(track_id) ON DELETE CASCADE,
    INDEX idx_user_time (user_id, created_at),
    INDEX idx_track_time (track_id, created_at),
    INDEX idx_type (interaction_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 歌曲多模态特征表
CREATE TABLE IF NOT EXISTS track_features (
    track_id     VARCHAR(64)   PRIMARY KEY,
    danceability FLOAT         NULL,
    energy       FLOAT         NULL,
    tempo        FLOAT         NULL,
    valence      FLOAT         NULL,
    acousticness FLOAT         NULL,
    updated_at   TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (track_id) REFERENCES tracks(track_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 标签表
CREATE TABLE IF NOT EXISTS tags (
    tag_id   INT           PRIMARY KEY AUTO_INCREMENT,
    tag_name VARCHAR(100)  NOT NULL UNIQUE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 歌曲-标签关联表
CREATE TABLE IF NOT EXISTS track_tags (
    track_id VARCHAR(64)   NOT NULL,
    tag_id   INT           NOT NULL,
    PRIMARY KEY (track_id, tag_id),
    FOREIGN KEY (track_id) REFERENCES tracks(track_id) ON DELETE CASCADE,
    FOREIGN KEY (tag_id) REFERENCES tags(tag_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 离线推荐兜底表
CREATE TABLE IF NOT EXISTS offline_recommendations (
    user_id               INT       PRIMARY KEY,
    recommended_track_ids JSON      NOT NULL,
    updated_at            TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 用户收藏表 (便于快速查询)
CREATE TABLE IF NOT EXISTS user_favorites (
    user_id    INT          NOT NULL,
    track_id   VARCHAR(64)  NOT NULL,
    created_at TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, track_id),
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (track_id) REFERENCES tracks(track_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
