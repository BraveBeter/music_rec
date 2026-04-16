"""
Generate realistic user interaction data based on Last.FM 1K dataset.

Downloads Last.FM 1K listening data, extracts real user behavior patterns
with ACTUAL track names from the dataset. Inserts real tracks into the DB
so interactions reference songs users truly listened to.

Produces ~800 users with ~200K+ interactions and thousands of real tracks.

Hardware target: Mac M5 16GB RAM
Usage:
    uv run python -m ml_pipeline.data_process.generate_lastfm_data
"""
import asyncio
import sys
import os
import random
import logging
import zipfile
import tarfile
import hashlib
from datetime import datetime, timedelta
from collections import defaultdict

import numpy as np
import pandas as pd
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "mysql+aiomysql://music_app:music_app_pass_2026@localhost:13307/music_rec",
)

DATA_CACHE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "raw",
)
LASTFM_TSV = "userid-timestamp-artid-artname-traid-traname.tsv"

# Target data size (Mac M5 16GB friendly)
NUM_TARGET_USERS = 800
MIN_MAPPED_PLAYS = 30  # minimum mapped artist plays for a valid profile

COUNTRIES = [
    "China", "USA", "UK", "Japan", "Korea", "Brazil", "Germany",
    "France", "India", "Australia", "Canada", "Italy", "Spain",
    "Netherlands", "Sweden", "Russia", "Poland", "Finland", "Mexico", "Argentina",
]

# Feature defaults per genre: (danceability_mean, energy_mean, tempo_mean)
GENRE_FEATURE_DEFAULTS = {
    "Rock": (0.6, 0.8, 130), "Pop": (0.7, 0.6, 120),
    "Hip-Hop": (0.8, 0.7, 95), "Electronic": (0.7, 0.8, 128),
    "Jazz": (0.4, 0.3, 120), "Classical": (0.2, 0.2, 100),
    "R&B": (0.6, 0.5, 100), "Latin": (0.8, 0.7, 110),
}

# ---------------------------------------------------------------------------
# Artist → Genre mapping  (8 genres matching our track catalog)
# Covers the most popular artists in the Last.FM 1K dataset (~2005-2009 era)
# ---------------------------------------------------------------------------
ARTIST_GENRE_MAP: dict[str, str] = {
    # --- Rock / Alternative ---
    "radiohead": "Rock", "the beatles": "Rock", "muse": "Rock",
    "metallica": "Rock", "nirvana": "Rock", "linkin park": "Rock",
    "pink floyd": "Rock", "the rolling stones": "Rock", "led zeppelin": "Rock",
    "queen": "Rock", "red hot chili peppers": "Rock", "green day": "Rock",
    "system of a down": "Rock", "the killers": "Rock", "iron maiden": "Rock",
    "the white stripes": "Rock", "oasis": "Rock", "the strokes": "Rock",
    "foo fighters": "Rock", "placebo": "Rock", "r.e.m.": "Rock", "u2": "Rock",
    "the doors": "Rock", "the cure": "Rock", "joy division": "Rock",
    "pixies": "Rock", "sonic youth": "Rock", "the smashing pumpkins": "Rock",
    "arctic monkeys": "Rock", "weezer": "Rock", "ac/dc": "Rock",
    "aerosmith": "Rock", "black sabbath": "Rock", "deep purple": "Rock",
    "david bowie": "Rock", "the who": "Rock", "guns n' roses": "Rock",
    "bon jovi": "Rock", "bruce springsteen": "Rock", "pearl jam": "Rock",
    "soundgarden": "Rock", "alice in chains": "Rock",
    "rage against the machine": "Rock", "incubus": "Rock",
    "nickelback": "Rock", "the offspring": "Rock", "blink-182": "Rock",
    "the clash": "Rock", "sex pistols": "Rock", "ramones": "Rock",
    "talking heads": "Rock", "blondie": "Rock", "the police": "Rock",
    "fleetwood mac": "Rock", "eagles": "Rock", "jimi hendrix": "Rock",
    "eric clapton": "Rock", "jeff buckley": "Rock", "neil young": "Rock",
    "bob dylan": "Rock", "kings of leon": "Rock", "the national": "Rock",
    "interpol": "Rock", "franz ferdinand": "Rock", "kasabian": "Rock",
    "mogwai": "Rock", "sigur rós": "Rock", "snow patrol": "Rock",
    "travis": "Rock", "keane": "Pop", "3 doors down": "Rock",
    "stone sour": "Rock", "godsmack": "Rock", "disturbed": "Rock",
    "slipknot": "Rock", "korn": "Rock", "limp bizkit": "Rock",
    "papa roach": "Rock", "staind": "Rock", "three days grace": "Rock",
    "seether": "Rock", "breaking benjamin": "Rock",
    "smashing pumpkins": "Rock", "cat power": "Rock",
    "bright eyes": "Rock", "the verve": "Rock",
    "dinosaur jr": "Rock", "pavement": "Rock", "guided by voices": "Rock",
    "wire": "Rock", "the fall": "Rock",
    "velvet underground": "Rock", "the velvet underground": "Rock",
    "iggy pop": "Rock", "lou reed": "Rock", "patti smith": "Rock",
    "tom waits": "Rock", "leonard cohen": "Rock", "nick cave": "Rock",
    "the smiths": "Rock", "morrissey": "Rock", "the libertines": "Rock",
    "babyshambles": "Rock", "dirty pretty things": "Rock",
    "creedence clearwater revival": "Rock", "lynyrd skynyrd": "Rock",
    "the allman brothers band": "Rock", "zz top": "Rock",
    "jethro tull": "Rock", "yes": "Rock", "genesis": "Rock",
    "king crimson": "Rock", "emerson, lake & palmer": "Rock",
    "rush": "Rock", "tool": "Rock", "dream theater": "Rock",

    # --- Pop ---
    "madonna": "Pop", "lady gaga": "Pop", "britney spears": "Pop",
    "katy perry": "Pop", "taylor swift": "Pop", "adele": "Pop",
    "bruno mars": "Pop", "justin timberlake": "Pop",
    "christina aguilera": "Pop", "robbie williams": "Pop",
    "michael jackson": "Pop", "prince": "Pop", "george michael": "Pop",
    "elton john": "Pop", "billy joel": "Pop", "abba": "Pop",
    "dido": "Pop", "pink": "Pop", "lily allen": "Pop",
    "miley cyrus": "Pop", "kelly clarkson": "Pop", "james blunt": "Pop",
    "daniel powter": "Pop", "maroon 5": "Pop", "avril lavigne": "Pop",
    "duran duran": "Pop", "spandau ballet": "Pop", "a-ha": "Pop",
    "take that": "Pop", "wham!": "Pop", "culture club": "Pop",
    "roxy music": "Pop", "supertramp": "Pop", "electric light orchestra": "Pop",
    "fleetwood mac": "Pop", "stevie wonder": "R&B",
    "n*sync": "Pop", "backstreet boys": "Pop",
    "spice girls": "Pop", "destiny's child": "R&B",
    "sugababes": "Pop", "girls aloud": "Pop",
    "rihanna": "R&B", "beyoncé": "R&B",
    "nelly furtado": "Pop", "fergie": "Pop", "gwen stefani": "Pop",
    "no doubt": "Pop", "john mayer": "Pop",

    # --- Hip-Hop ---
    "eminem": "Hip-Hop", "kanye west": "Hip-Hop", "jay-z": "Hip-Hop",
    "50 cent": "Hip-Hop", "wu-tang clan": "Hip-Hop", "nas": "Hip-Hop",
    "outkast": "Hip-Hop", "lil wayne": "Hip-Hop", "2pac": "Hip-Hop",
    "tupac": "Hip-Hop", "the notorious b.i.g.": "Hip-Hop",
    "notorious b.i.g.": "Hip-Hop", "a tribe called quest": "Hip-Hop",
    "beastie boys": "Hip-Hop", "snoop dogg": "Hip-Hop",
    "dr. dre": "Hip-Hop", "ice cube": "Hip-Hop", "n.w.a": "Hip-Hop",
    "the roots": "Hip-Hop", "common": "Hip-Hop", "mos def": "Hip-Hop",
    "talib kweli": "Hip-Hop", "mf doom": "Hip-Hop",
    "gorillaz": "Hip-Hop", "missy elliott": "Hip-Hop",
    "t.i.": "Hip-Hop", "ludacris": "Hip-Hop", "nelly": "Hip-Hop",
    "black eyed peas": "Hip-Hop", "ciara": "R&B",
    "run-d.m.c.": "Hip-Hop", "public enemy": "Hip-Hop",
    "de la soul": "Hip-Hop", "gang starr": "Hip-Hop",
    "the pharcyde": "Hip-Hop", "digable planets": "Hip-Hop",
    "the game": "Hip-Hop", "young jeezy": "Hip-Hop",
    "chamillionaire": "Hip-Hop", "m.i.a.": "Electronic",
    "kesha": "Pop", "pitbull": "Hip-Hop", "flo rida": "Hip-Hop",
    "soulja boy": "Hip-Hop", "lil jon": "Hip-Hop",
    "twista": "Hip-Hop", "ja rule": "Hip-Hop",
    "method man": "Hip-Hop", "redman": "Hip-Hop",
    "busta rhymes": "Hip-Hop", "scarface": "Hip-Hop",

    # --- Electronic ---
    "daft punk": "Electronic", "the prodigy": "Electronic",
    "aphex twin": "Electronic", "moby": "Electronic",
    "kraftwerk": "Electronic", "the chemical brothers": "Electronic",
    "chemical brothers": "Electronic", "boards of canada": "Electronic",
    "autechre": "Electronic", "basement jaxx": "Electronic",
    "fatboy slim": "Electronic", "underworld": "Electronic",
    "orbital": "Electronic", "massive attack": "Electronic",
    "portishead": "Electronic", "tricky": "Electronic",
    "thievery corporation": "Electronic", "air": "Electronic",
    "st germain": "Electronic", "bonobo": "Electronic",
    "tycho": "Electronic", "deadmau5": "Electronic",
    "the avalanches": "Electronic", "brian eno": "Electronic",
    "goldfrapp": "Electronic", "lcd soundsystem": "Electronic",
    "justice": "Electronic", "moderat": "Electronic",
    "modeselektor": "Electronic", "richie hawtin": "Electronic",
    "carl cox": "Electronic", "paul oakenfold": "Electronic",
    "paul van dyk": "Electronic", "tiësto": "Electronic",
    "armin van buuren": "Electronic", "booka shade": "Electronic",
    "trentemøller": "Electronic", "vitalic": "Electronic",
    "kruder & dorfmeister": "Electronic",
    "four tet": "Electronic", "squarepusher": "Electronic",
    "venetian snares": "Electronic", "agyptian": "Electronic",
    "leftfield": "Electronic", "orb": "Electronic",
    "future sound of london": "Electronic", "fluke": "Electronic",
    "detroit grand pubahs": "Electronic", "felix da housecat": "Electronic",

    # --- R&B / Soul ---
    "mariah carey": "R&B", "alicia keys": "R&B", "usher": "R&B",
    "whitney houston": "R&B", "tlc": "R&B", "erykah badu": "R&B",
    "d'angelo": "R&B", "maxwell": "R&B", "jill scott": "R&B",
    "john legend": "R&B", "ne-yo": "R&B", "chris brown": "R&B",
    "boyz ii men": "R&B", "marvin gaye": "R&B", "al green": "R&B",
    "sam cooke": "R&B", "otis redding": "R&B", "ray charles": "R&B",
    "aretha franklin": "R&B", "lauryn hill": "R&B",
    "aaliyah": "R&B", "brandy": "R&B", "monica": "R&B",
    "trey songz": "R&B", "akon": "R&B", "sean paul": "R&B",
    "mary j. blige": "R&B", "toni braxton": "R&B",
    "etta james": "R&B", "dinah washington": "R&B",
    "natalie cole": "R&B", "chet baker": "Jazz",

    # --- Jazz ---
    "miles davis": "Jazz", "john coltrane": "Jazz", "thelonious monk": "Jazz",
    "dave brubeck": "Jazz", "bill evans": "Jazz", "charles mingus": "Jazz",
    "ella fitzgerald": "Jazz", "duke ellington": "Jazz", "stan getz": "Jazz",
    "billie holiday": "Jazz", "count basie": "Jazz", "oscar peterson": "Jazz",
    "herbie hancock": "Jazz", "weather report": "Jazz", "pat metheny": "Jazz",
    "keith jarrett": "Jazz", "wayne shorter": "Jazz", "art blakey": "Jazz",
    "sonny rollins": "Jazz", "dizzy gillespie": "Jazz", "louis armstrong": "Jazz",
    "wynton marsalis": "Jazz", "brad mehldau": "Jazz",
    "esbjörn svensson trio": "Jazz", "avishai cohen": "Jazz",
    "medeski martin & wood": "Jazz", "the bad plus": "Jazz",
    "ron carter": "Jazz", "cannonball adderley": "Jazz",
    "norah jones": "Jazz", "diana krall": "Jazz", "cassandra wilson": "Jazz",
    " Cassandra wilson": "Jazz",
    "chick corea": "Jazz", "stanley clarke": "Jazz",
    "freddie hubbard": "Jazz", "lee morgan": "Jazz", "hank mobley": "Jazz",
    "wes montgomery": "Jazz", "joe pass": "Jazz", "barney kessel": "Jazz",
    "oscar peterson trio": "Jazz", "bill evans trio": "Jazz",

    # --- Classical ---
    "beethoven": "Classical", "mozart": "Classical", "bach": "Classical",
    "chopin": "Classical", "debussy": "Classical", "tchaikovsky": "Classical",
    "vivaldi": "Classical", "brahms": "Classical", "schubert": "Classical",
    "rachmaninoff": "Classical", "handel": "Classical", "mendelssohn": "Classical",
    "dvořák": "Classical", "grieg": "Classical", "liszt": "Classical",
    "ravel": "Classical", "richard strauss": "Classical", "mahler": "Classical",
    "prokofiev": "Classical", "shostakovich": "Classical",
    "stravinsky": "Classical", "bartók": "Classical",
    "glenn gould": "Classical", "martha argerich": "Classical",
    "yo-yo ma": "Classical", "itzhak perlman": "Classical",
    "hilary hahn": "Classical", "lang lang": "Classical",
    "murray perahia": "Classical", "alfred brendel": "Classical",
    "vladimir horowitz": "Classical", "arthur rubinstein": "Classical",
    "daniel barenboim": "Classical", "mstislav rostropovich": "Classical",
    "jacqueline du pré": "Classical",
    "wagner": "Classical", "verdi": "Classical", "puccini": "Classical",
    "rossini": "Classical", "bizet": "Classical",

    # --- Latin ---
    "shakira": "Latin", "juanes": "Latin", "maná": "Latin",
    "enrique iglesias": "Latin", "ricky martin": "Latin",
    "daddy yankee": "Latin", "don omar": "Latin", "carlos vives": "Latin",
    "luis fonsi": "Latin", "thalía": "Latin", "celia cruz": "Latin",
    "héctor lavoe": "Latin", "willie colón": "Latin", "rubén blades": "Latin",
    "buena vista social club": "Latin", "ibrahim ferrer": "Latin",
    "compay segundo": "Latin", "caetano veloso": "Latin",
    "gilberto gil": "Latin", "joão gilberto": "Latin",
    "antonio carlos jobim": "Latin", "los lonely boys": "Latin",
    "ozomatli": "Latin", "café tacvba": "Latin", "calle 13": "Latin",
    "bacilos": "Latin", "juan luis guerra": "Latin",
    "alejandro sanz": "Latin", "david bisbal": "Latin",
    "luis miguel": "Latin", "cristian castro": "Latin",
    "vicente fernández": "Latin", "pepe aguilar": "Latin",
    "ana gabriel": "Latin",
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Phase 1: Download
# ---------------------------------------------------------------------------
def _download_lastfm_1k() -> str:
    """Download and cache Last.FM 1K dataset. Returns path to TSV file."""
    os.makedirs(DATA_CACHE_DIR, exist_ok=True)
    tsv_path = os.path.join(DATA_CACHE_DIR, LASTFM_TSV)

    if os.path.exists(tsv_path):
        size_mb = os.path.getsize(tsv_path) / (1024 * 1024)
        logger.info(f"Using cached dataset: {tsv_path} ({size_mb:.0f}MB)")
        return tsv_path

    manual_path = os.environ.get("LASTFM_TSV_PATH")
    if manual_path and os.path.exists(manual_path):
        logger.info(f"Using manually specified dataset: {manual_path}")
        return manual_path

    import urllib.request

    sources = [
        {
            "url": "https://zenodo.org/records/6090214/files/lastfm-dataset-1K.tar.gz",
            "format": "tar.gz",
            "archive": os.path.join(DATA_CACHE_DIR, "lastfm-1K.tar.gz"),
        },
        {
            "url": "http://ocelma.net/MusicRecommendationDataset/lastfm-dataset-1K.tar.gz",
            "format": "tar.gz",
            "archive": os.path.join(DATA_CACHE_DIR, "lastfm-1K.tar.gz"),
        },
    ]

    for source in sources:
        url = source["url"]
        archive_path = source["archive"]
        try:
            logger.info(f"Downloading Last.FM 1K dataset from {url}")
            logger.info("File size ~640MB — this may take several minutes...")

            last_report = [0.0]

            def _reporthook(count, block_size, total_size, _lr=last_report):
                downloaded = count * block_size
                import time
                now = time.time()
                if now - _lr[0] > 15:
                    if total_size > 0:
                        pct = min(downloaded / total_size * 100, 100)
                        logger.info(
                            f"  {downloaded / (1024*1024):.0f}MB / "
                            f"{total_size / (1024*1024):.0f}MB ({pct:.1f}%)"
                        )
                    _lr[0] = now

            urllib.request.urlretrieve(url, archive_path, reporthook=_reporthook)

            logger.info("Extracting TSV from archive...")
            if source["format"] == "tar.gz":
                with tarfile.open(archive_path, "r:gz") as tf:
                    target = None
                    for member in tf.getmembers():
                        basename = os.path.basename(member.name)
                        if basename == LASTFM_TSV:
                            target = member
                            break
                    if target is None:
                        tsv_members = [m for m in tf.getmembers()
                                       if m.name.endswith(".tsv") and m.size > 100_000]
                        if tsv_members:
                            target = max(tsv_members, key=lambda m: m.size)
                    if target is None:
                        raise RuntimeError("Could not find listening-history TSV in archive")
                    logger.info(f"  Extracting: {target.name} ({target.size / (1024*1024):.0f}MB)")
                    src = tf.extractfile(target)
                    if src:
                        with open(tsv_path, "wb") as dst:
                            while True:
                                chunk = src.read(8192)
                                if not chunk:
                                    break
                                dst.write(chunk)
            else:
                with zipfile.ZipFile(archive_path, "r") as zf:
                    for name in zf.namelist():
                        if name.endswith(".tsv"):
                            with zf.open(name) as src, open(tsv_path, "wb") as dst:
                                while True:
                                    chunk = src.read(8192)
                                    if not chunk:
                                        break
                                    dst.write(chunk)
                            break

            os.remove(archive_path)
            size_mb = os.path.getsize(tsv_path) / (1024 * 1024)
            logger.info(f"Dataset cached: {tsv_path} ({size_mb:.0f}MB)")
            return tsv_path

        except Exception as e:
            logger.warning(f"Download from {url} failed: {e}")
            if os.path.exists(archive_path):
                os.remove(archive_path)
            continue

    logger.error("=" * 60)
    logger.error("Failed to download Last.FM 1K dataset automatically.")
    logger.error("Please download manually:")
    logger.error("  Zenodo: https://zenodo.org/records/6090214/files/lastfm-dataset-1K.tar.gz")
    logger.error(f"  Extract TSV to: {DATA_CACHE_DIR}/")
    logger.error("  Or set LASTFM_TSV_PATH=/path/to/file.tsv")
    logger.error("=" * 60)
    sys.exit(1)


# ---------------------------------------------------------------------------
# Phase 2: Extract user profiles AND real tracks from TSV
# ---------------------------------------------------------------------------
def _extract_data_from_tsv(tsv_path: str) -> tuple[
    dict[str, dict[str, float]],              # user_profiles: userid -> genre -> weight
    dict[str, list[str]],                      # user_tracks: userid -> [track_id, ...]
    dict[str, tuple[str, str, str, int]],     # track_info: track_id -> (title, artist, genre, duration_ms)
]:
    """
    Parse Last.FM 1K TSV and extract:
    1. User genre preference profiles (for user selection)
    2. Per-user list of real track IDs they listened to
    3. Full track info for all unique tracks
    """
    logger.info("Extracting user profiles and real tracks from Last.FM 1K...")

    user_genre_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    user_track_listens: dict[str, list[str]] = defaultdict(list)
    # key = (artname_lower, traname_lower) for dedup
    unique_tracks: dict[tuple[str, str], tuple[str, str, str]] = {}  # (art_lower, tr_lower) -> (artname, traname, genre)

    chunk_size = 500_000
    total_rows = 0

    for chunk in pd.read_csv(
        tsv_path,
        sep="\t",
        header=None,
        usecols=[0, 3, 5],
        names=["userid", "artname", "traname"],
        dtype={"userid": str, "artname": str, "traname": str},
        chunksize=chunk_size,
        on_bad_lines="skip",
        engine="c",
    ):
        chunk["artname_lower"] = chunk["artname"].fillna("").str.lower().str.strip()
        chunk["traname_lower"] = chunk["traname"].fillna("").str.lower().str.strip()
        chunk["genre"] = chunk["artname_lower"].map(ARTIST_GENRE_MAP)

        # Only keep rows where artist maps to a known genre
        mapped = chunk[chunk["genre"].notna()].copy()
        if mapped.empty:
            total_rows += len(chunk)
            continue

        # Build genre counts per user
        counts = mapped.groupby(["userid", "genre"]).size()
        for (userid, genre), count in counts.items():
            user_genre_counts[userid][genre] += count

        # Build track info and user-track mapping
        for _, row in mapped.iterrows():
            art_lower = row["artname_lower"]
            tr_lower = row["traname_lower"]
            if not tr_lower or tr_lower == "":
                continue
            genre = row["genre"]
            key = (art_lower, tr_lower)
            if key not in unique_tracks:
                unique_tracks[key] = (
                    row["artname"] if pd.notna(row["artname"]) else art_lower,
                    row["traname"] if pd.notna(row["traname"]) else tr_lower,
                    genre,
                )
            track_id = f"LFM{hashlib.md5(f'{art_lower}|{tr_lower}'.encode()).hexdigest()[:10].upper()}"
            user_track_listens[row["userid"]].append(track_id)

        total_rows += len(chunk)
        if total_rows % 2_000_000 < chunk_size:
            logger.info(f"  Processed {total_rows:,} rows — {len(user_genre_counts)} users, {len(unique_tracks)} unique tracks")

    # Build track_info dict with duration
    track_info: dict[str, tuple[str, str, str, int]] = {}
    for (art_lower, tr_lower), (artname, traname, genre) in unique_tracks.items():
        track_id = f"LFM{hashlib.md5(f'{art_lower}|{tr_lower}'.encode()).hexdigest()[:10].upper()}"
        duration = random.randint(180000, 360000)
        track_info[track_id] = (traname, artname, genre, duration)

    # Deduplicate user track lists
    for uid in user_track_listens:
        user_track_listens[uid] = list(dict.fromkeys(user_track_listens[uid]))  # preserve order, remove dups

    # Normalise to preference weights
    user_profiles: dict[str, dict[str, float]] = {}
    for userid, genres in user_genre_counts.items():
        total = sum(genres.values())
        if total >= MIN_MAPPED_PLAYS:
            user_profiles[userid] = {g: c / total for g, c in genres.items()}

    logger.info(f"Extracted {len(user_profiles)} valid user profiles")
    logger.info(f"Extracted {len(track_info)} unique real tracks from TSV")

    # Genre distribution
    genre_counts: dict[str, int] = defaultdict(int)
    for _, (_, _, genre, _) in track_info.items():
        genre_counts[genre] += 1
    for g, c in sorted(genre_counts.items()):
        logger.info(f"  {g}: {c} unique tracks")

    return user_profiles, dict(user_track_listens), track_info


# ---------------------------------------------------------------------------
# Phase 3: Select users ensuring genre diversity
# ---------------------------------------------------------------------------
def _select_users(
    profiles: dict[str, dict[str, float]],
    user_tracks: dict[str, list[str]],
    n: int,
) -> list[tuple[str, dict[str, float]]]:
    """Sample n users, ensuring coverage of all 8 genres and each has real tracks."""
    all_genres = {"Pop", "Rock", "Hip-Hop", "Electronic", "Jazz", "Classical", "R&B", "Latin"}
    items = [(uid, prefs) for uid, prefs in profiles.items() if uid in user_tracks and len(user_tracks[uid]) >= 10]
    random.shuffle(items)

    selected: list[tuple[str, dict[str, float]]] = []
    covered_genres: set[str] = set()

    # First pass: ensure at least one user per genre
    for genre in all_genres:
        for uid, prefs in items:
            if genre in prefs and prefs[genre] >= 0.15 and uid not in {s[0] for s in selected}:
                selected.append((uid, prefs))
                covered_genres.add(genre)
                break

    logger.info(f"Genre-coverage pass: {len(selected)} users covering {len(covered_genres)} genres")

    # Fill remaining slots
    remaining = [item for item in items if item[0] not in {s[0] for s in selected}]
    random.shuffle(remaining)
    for uid, prefs in remaining:
        if len(selected) >= n:
            break
        selected.append((uid, prefs))

    logger.info(f"Selected {len(selected)} users for generation")
    return selected


# ---------------------------------------------------------------------------
# Phase 4: Generate interaction metadata
# ---------------------------------------------------------------------------
def _interaction_metadata(liked: bool) -> dict:
    """Generate interaction type & metadata."""
    if liked:
        roll = random.random()
        if roll < 0.65:
            completion = random.uniform(0.6, 1.0)
            return {
                "interaction_type": 1,
                "rating": random.choice([None, None, 4.0, 5.0]) if random.random() < 0.15 else None,
                "completion_rate": round(completion, 3),
                "duration_fraction": completion,
            }
        elif roll < 0.85:
            return {
                "interaction_type": 2,
                "rating": None,
                "completion_rate": round(random.uniform(0.5, 1.0), 3),
                "duration_fraction": random.uniform(0.5, 1.0),
            }
        else:
            return {
                "interaction_type": 4,
                "rating": random.choice([4.0, 4.5, 5.0]),
                "completion_rate": round(random.uniform(0.7, 1.0), 3),
                "duration_fraction": random.uniform(0.7, 1.0),
            }
    else:
        roll = random.random()
        if roll < 0.6:
            return {
                "interaction_type": 3,
                "rating": None,
                "completion_rate": round(random.uniform(0.0, 0.25), 3),
                "duration_fraction": random.uniform(0.0, 0.25),
            }
        elif roll < 0.85:
            completion = random.uniform(0.05, 0.35)
            return {
                "interaction_type": 1,
                "rating": None,
                "completion_rate": round(completion, 3),
                "duration_fraction": completion,
            }
        else:
            return {
                "interaction_type": 4,
                "rating": random.choice([1.0, 1.5, 2.0, 2.5]),
                "completion_rate": round(random.uniform(0.1, 0.4), 3),
                "duration_fraction": random.uniform(0.1, 0.4),
            }


def _generate_interactions_from_real_listens(
    track_ids: list[str],
    track_info: dict[str, tuple[str, str, str, int]],
    genre_prefs: dict[str, float],
) -> list[dict]:
    """
    Generate interactions based on user's REAL listening history from TSV.
    Uses actual tracks the user listened to, not random picks.
    """
    if not track_ids:
        return []

    interactions = []
    base_time = datetime.now() - timedelta(days=180)

    for track_id in track_ids:
        info = track_info.get(track_id)
        genre = info[2] if info else "Pop"
        genre_weight = genre_prefs.get(genre, 0.1)

        # Liked probability scales with genre preference
        liked = random.random() < (0.3 + genre_weight * 0.7)

        meta = _interaction_metadata(liked)

        duration_ms = info[3] if info else 30000
        play_duration = int(duration_ms * meta["duration_fraction"])

        day_offset = random.betavariate(2, 5) * 180
        hour = int(random.betavariate(5, 3) * 24)
        ts = base_time + timedelta(days=day_offset, hours=hour)

        interactions.append({
            "track_id": track_id,
            "interaction_type": meta["interaction_type"],
            "rating": meta["rating"],
            "play_duration": play_duration,
            "completion_rate": meta["completion_rate"],
            "created_at": ts,
        })

    return interactions


# ---------------------------------------------------------------------------
# Phase 5: MySQL operations
# ---------------------------------------------------------------------------
async def _insert_real_tracks(session, track_info: dict[str, tuple[str, str, str, int]]) -> int:
    """Insert all real tracks extracted from TSV into the database."""
    logger.info(f"Inserting {len(track_info)} real tracks into database...")

    # Pre-fetch existing LFM tracks to skip
    result = await session.execute(
        text("SELECT track_id FROM tracks WHERE track_id LIKE 'LFM%'")
    )
    existing_lfm = {row[0] for row in result.fetchall()}

    # Pre-fetch all tag IDs
    result = await session.execute(text("SELECT tag_id, tag_name FROM tags"))
    tag_ids: dict[str, int] = {row[1]: row[0] for row in result.fetchall()}

    # Ensure all needed tags exist
    all_genres = set()
    for _, (_, _, genre, _) in track_info.items():
        all_genres.add(genre)
    for genre in all_genres:
        if genre not in tag_ids:
            await session.execute(text("INSERT IGNORE INTO tags (tag_name) VALUES (:tag)"), {"tag": genre})
    await session.flush()
    result = await session.execute(text("SELECT tag_id, tag_name FROM tags"))
    tag_ids = {row[1]: row[0] for row in result.fetchall()}

    inserted = 0
    batch_size = 500

    for track_id, (title, artist, genre, duration) in track_info.items():
        if track_id in existing_lfm:
            continue

        # Clean title/artist — truncate to reasonable length
        clean_title = title[:200] if title else "Unknown"
        clean_artist = artist[:200] if artist else "Unknown"

        await session.execute(text("""
            INSERT IGNORE INTO tracks
            (track_id, title, artist_name, duration_ms, play_count, status)
            VALUES (:track_id, :title, :artist, :duration, 0, 1)
        """), {
            "track_id": track_id, "title": clean_title,
            "artist": clean_artist, "duration": duration,
        })

        # Insert features based on genre
        d, e, t = GENRE_FEATURE_DEFAULTS.get(genre, (0.5, 0.5, 120))
        await session.execute(text("""
            INSERT IGNORE INTO track_features
            (track_id, danceability, energy, tempo, valence, acousticness)
            VALUES (:track_id, :d, :e, :t, :v, :a)
        """), {
            "track_id": track_id,
            "d": round(random.gauss(d, 0.15), 3),
            "e": round(random.gauss(e, 0.15), 3),
            "t": round(random.gauss(t, 20), 1),
            "v": round(random.uniform(0.1, 0.9), 3),
            "a": round(random.uniform(0.01, 0.6), 3),
        })

        # Insert tag association
        tag_id = tag_ids.get(genre)
        if tag_id:
            await session.execute(text("""
                INSERT IGNORE INTO track_tags (track_id, tag_id) VALUES (:tid, :tagid)
            """), {"tid": track_id, "tagid": tag_id})

        inserted += 1
        if inserted % batch_size == 0:
            await session.flush()
            logger.info(f"  Inserted {inserted} tracks...")

    await session.flush()
    logger.info(f"Inserted {inserted} new real tracks (skipped {len(track_info) - inserted + len(existing_lfm)} existing)")
    return inserted


async def _clear_old_data(session):
    """Remove old lastfm users and their interactions."""
    for prefix in ("lastfm_user_%",):
        result = await session.execute(
            text("SELECT user_id FROM users WHERE username LIKE :prefix"),
            {"prefix": prefix},
        )
        user_ids = [row[0] for row in result.fetchall()]
        if user_ids:
            for uid in user_ids:
                await session.execute(
                    text("DELETE FROM user_interactions WHERE user_id = :uid"),
                    {"uid": uid},
                )
            await session.execute(
                text("DELETE FROM users WHERE username LIKE :prefix"),
                {"prefix": prefix},
            )
            logger.info(f"Cleared {len(user_ids)} {prefix.strip('%')} accounts")


async def _insert_user(session, idx: int, age: int, gender: int, country: str) -> int | None:
    """Insert a user and return their user_id."""
    username = f"lastfm_user_{idx:04d}"
    await session.execute(
        text("""
            INSERT IGNORE INTO users (username, password_hash, role, age, gender, country)
            VALUES (:username, :ph, 'user', :age, :gender, :country)
        """),
        {
            "username": username,
            "ph": "$2b$12$iIr5ocgmGsKOhOG4/Ke4AuXeaFukrV/Q9N2dhjATHvHlT3ERecz46",
            "age": age, "gender": gender, "country": country,
        },
    )
    await session.flush()
    result = await session.execute(
        text("SELECT user_id FROM users WHERE username = :username"),
        {"username": username},
    )
    row = result.first()
    return row[0] if row else None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
async def generate():
    logger.info("=" * 60)
    logger.info("Last.FM 1K Data Generator (Real Tracks)")
    logger.info(f"Target: {NUM_TARGET_USERS} users with real listening history")
    logger.info("=" * 60)

    # 1. Download / cache
    tsv_path = _download_lastfm_1k()

    # 2. Extract user profiles AND real tracks from TSV
    user_profiles, user_tracks, track_info = _extract_data_from_tsv(tsv_path)
    if not user_profiles:
        logger.error("No valid user profiles extracted. Check ARTIST_GENRE_MAP coverage.")
        return

    # 3. Select users with genre diversity (only those with real tracks)
    selected = _select_users(user_profiles, user_tracks, NUM_TARGET_USERS)

    # 4. Connect to DB
    engine = create_async_engine(DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        # 5. Insert all real tracks into DB first
        logger.info(f"Total unique tracks to ensure in DB: {len(track_info)}")
        await _insert_real_tracks(session, track_info)
        await session.commit()

        # 6. Clear old lastfm users
        logger.info("Clearing old lastfm user data...")
        await _clear_old_data(session)
        await session.commit()

        # 7. Generate and insert users + interactions based on real listens
        total_interactions = 0
        batch_interactions = []

        logger.info(f"Generating {len(selected)} users with real listening interactions...")
        for i, (lfm_uid, prefs) in enumerate(selected):
            age = random.choice([
                random.randint(16, 22),
                random.randint(23, 35),
                random.randint(36, 55),
            ])
            gender = random.choice([0, 1, 2])
            country = random.choice(COUNTRIES)

            user_id = await _insert_user(session, i, age, gender, country)
            if not user_id:
                continue

            # Use this user's REAL tracks from TSV
            real_tracks = user_tracks.get(lfm_uid, [])
            if not real_tracks:
                continue

            interactions = _generate_interactions_from_real_listens(
                real_tracks, track_info, prefs,
            )

            for ia in interactions:
                batch_interactions.append({
                    "user_id": user_id,
                    "track_id": ia["track_id"],
                    "interaction_type": ia["interaction_type"],
                    "rating": ia["rating"],
                    "play_duration": ia["play_duration"],
                    "completion_rate": ia["completion_rate"],
                    "created_at": ia["created_at"],
                })
                total_interactions += 1

            # Flush in batches of 50 users
            if (i + 1) % 50 == 0 and batch_interactions:
                for ia in batch_interactions:
                    await session.execute(
                        text("""
                            INSERT INTO user_interactions
                            (user_id, track_id, interaction_type, rating,
                             play_duration, completion_rate, created_at)
                            VALUES (:user_id, :track_id, :interaction_type, :rating,
                                    :play_duration, :completion_rate, :created_at)
                        """),
                        ia,
                    )
                await session.flush()
                logger.info(f"  {i + 1}/{len(selected)} users — {total_interactions:,} interactions")
                batch_interactions = []

        # Insert remaining
        for ia in batch_interactions:
            await session.execute(
                text("""
                    INSERT INTO user_interactions
                    (user_id, track_id, interaction_type, rating,
                     play_duration, completion_rate, created_at)
                    VALUES (:user_id, :track_id, :interaction_type, :rating,
                            :play_duration, :completion_rate, :created_at)
                """),
                ia,
            )

        # Update play counts
        await session.execute(text("""
            UPDATE tracks t SET play_count = (
                SELECT COUNT(*) FROM user_interactions ui
                WHERE ui.track_id = t.track_id AND ui.interaction_type = 1
            )
        """))

        await session.commit()
        logger.info("=" * 60)
        logger.info(f"Generated {len(selected)} users, {total_interactions:,} interactions")
        logger.info(f"Total real tracks in DB: {len(track_info)}")
        logger.info("=" * 60)

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(generate())
