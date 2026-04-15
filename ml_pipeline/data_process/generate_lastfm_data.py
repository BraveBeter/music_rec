"""
Generate realistic user interaction data based on Last.FM 1K dataset.

Downloads Last.FM 1K listening data, extracts real user behavior patterns
(genre preferences, activity levels), and maps them to our track catalog
in MySQL. Produces ~800 users with ~200K+ interactions.

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
MIN_INTERACTIONS_PER_USER = 50
MAX_INTERACTIONS_PER_USER = 500
MIN_MAPPED_PLAYS = 30  # minimum mapped artist plays for a valid profile

COUNTRIES = [
    "China", "USA", "UK", "Japan", "Korea", "Brazil", "Germany",
    "France", "India", "Australia", "Canada", "Italy", "Spain",
    "Netherlands", "Sweden", "Russia", "Poland", "Finland", "Mexico", "Argentina",
]

# ---------------------------------------------------------------------------
# Artist → Genre mapping  (8 genres matching our Deezer track catalog)
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

    # Zenodo mirror (tar.gz) and original mirrors (zip)
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
                    # Find the main listening-history TSV (contains 'artid' and 'traid')
                    # NOT the smaller profile file
                    target = None
                    for member in tf.getmembers():
                        basename = os.path.basename(member.name)
                        if basename == LASTFM_TSV:
                            target = member
                            break
                    # Fallback: pick the largest .tsv file
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
# Phase 2: Extract user genre profiles from TSV
# ---------------------------------------------------------------------------
def _extract_user_profiles(tsv_path: str) -> dict[str, dict[str, float]]:
    """
    Parse Last.FM 1K TSV (chunked) and build normalised genre-preference
    vectors for every user who has >= MIN_MAPPED_PLAYS mapped artist plays.
    """
    logger.info("Extracting user genre profiles from Last.FM 1K...")
    user_genre_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    chunk_size = 500_000
    total_rows = 0

    for chunk in pd.read_csv(
        tsv_path,
        sep="\t",
        header=None,
        usecols=[0, 3],
        names=["userid", "artname"],
        dtype={"userid": str, "artname": str},
        chunksize=chunk_size,
        on_bad_lines="skip",
        engine="c",
    ):
        chunk["artname_lower"] = chunk["artname"].fillna("").str.lower().str.strip()
        chunk["genre"] = chunk["artname_lower"].map(ARTIST_GENRE_MAP)

        mapped = chunk[chunk["genre"].notna()]
        if mapped.empty:
            total_rows += len(chunk)
            continue

        counts = mapped.groupby(["userid", "genre"]).size()
        for (userid, genre), count in counts.items():
            user_genre_counts[userid][genre] += count

        total_rows += len(chunk)
        if total_rows % 2_000_000 < chunk_size:
            logger.info(f"  Processed {total_rows:,} rows — {len(user_genre_counts)} users so far")

    # Normalise to preference weights
    user_profiles: dict[str, dict[str, float]] = {}
    for userid, genres in user_genre_counts.items():
        total = sum(genres.values())
        if total >= MIN_MAPPED_PLAYS:
            user_profiles[userid] = {g: c / total for g, c in genres.items()}

    logger.info(f"Extracted {len(user_profiles)} valid user genre profiles")
    return user_profiles


# ---------------------------------------------------------------------------
# Phase 3: Select users ensuring genre diversity
# ---------------------------------------------------------------------------
def _select_users(
    profiles: dict[str, dict[str, float]], n: int,
) -> list[tuple[str, dict[str, float]]]:
    """Sample n users, ensuring coverage of all 8 genres."""
    all_genres = {"Pop", "Rock", "Hip-Hop", "Electronic", "Jazz", "Classical", "R&B", "Latin"}
    items = list(profiles.items())
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
# Phase 4: Generate interactions
# ---------------------------------------------------------------------------
def _interaction_metadata(liked: bool) -> dict:
    """Generate interaction type & metadata (same logic as synthetic generator)."""
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


def _generate_interactions_for_user(
    genre_prefs: dict[str, float],
    genre_tracks: dict[str, list[str]],
    all_track_ids: list[str],
    track_durations: dict[str, int],
) -> list[dict]:
    """Generate a realistic set of interactions for one user."""
    n_interactions = random.randint(MIN_INTERACTIONS_PER_USER, MAX_INTERACTIONS_PER_USER)
    genres = list(genre_prefs.keys())
    weights = [genre_prefs[g] for g in genres]

    # Decide activity level based on preference concentration
    # Users with concentrated taste interact more with preferred genres
    max_weight = max(weights) if weights else 0.5

    interactions = []
    base_time = datetime.now() - timedelta(days=180)

    for j in range(n_interactions):
        # Pick genre weighted by user preference
        genre = random.choices(genres, weights=weights, k=1)[0]
        candidates = genre_tracks.get(genre, [])
        if not candidates:
            candidates = all_track_ids

        track_id = random.choice(candidates)

        # Liked probability scales with genre preference weight
        liked = random.random() < (0.3 + genre_prefs.get(genre, 0.1) * 0.7)

        meta = _interaction_metadata(liked)

        duration_ms = track_durations.get(track_id, 30000)
        play_duration = int(duration_ms * meta["duration_fraction"])

        # Spread timestamps over last 180 days with realistic clustering
        day_offset = random.betavariate(2, 5) * 180  # more recent = more likely
        hour = int(random.betavariate(5, 3) * 24)  # peak evening hours
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
MIN_TRACKS_PER_GENRE = 100  # Ensure each genre has enough tracks


async def _ensure_genre_tracks(session, genre_tracks: dict[str, list[str]]) -> None:
    """
    Ensure each genre has at least MIN_TRACKS_PER_GENRE tracks.
    Creates synthetic tracks from ARTIST_GENRE_MAP entries when a genre is underpopulated.
    """
    # Build reverse map: genre -> list of artists
    genre_artists: dict[str, list[str]] = {}
    for artist, genre in ARTIST_GENRE_MAP.items():
        genre_artists.setdefault(genre, []).append(artist)

    total_created = 0
    for genre, artists in genre_artists.items():
        existing = len(genre_tracks.get(genre, []))
        needed = max(0, MIN_TRACKS_PER_GENRE - existing)
        if needed <= 0:
            continue

        # Ensure tag exists
        await session.execute(text("INSERT IGNORE INTO tags (tag_name) VALUES (:tag)"), {"tag": genre})
        tag_result = await session.execute(
            text("SELECT tag_id FROM tags WHERE tag_name = :tag"), {"tag": genre}
        )
        tag_row = tag_result.first()
        if not tag_row:
            continue
        tag_id = tag_row[0]

        # Create synthetic tracks from artist names
        created = 0
        for i in range(needed):
            artist = artists[i % len(artists)]
            # Deterministic ID from artist + index to avoid duplicates
            raw = f"LFM-{artist}-{i}"
            track_id = f"LFM{hashlib.md5(raw.encode()).hexdigest()[:10].upper()}"

            # Skip if already exists
            existing_check = await session.execute(
                text("SELECT track_id FROM tracks WHERE track_id = :tid"), {"tid": track_id}
            )
            if existing_check.first():
                continue

            duration = random.randint(180000, 360000)  # 3-6 min
            title_variants = ["Greatest Hits", "Best Of", "Anthology", "Collection",
                              "Essential", "Classics", "Live", "Acoustic", "Deluxe",
                              "Original", "Remastered", "Sessions", "Tribute"]
            title = f"{artist.title()} - {random.choice(title_variants)} Vol.{i // len(artists) + 1}"

            await session.execute(text("""
                INSERT IGNORE INTO tracks
                (track_id, title, artist_name, duration_ms, play_count, status)
                VALUES (:track_id, :title, :artist, :duration, 0, 1)
            """), {
                "track_id": track_id, "title": title,
                "artist": artist.title(), "duration": duration,
            })

            # Random acoustic features based on genre tendencies
            feature_defaults = {
                "Rock": (0.6, 0.8, 130), "Pop": (0.7, 0.6, 120),
                "Hip-Hop": (0.8, 0.7, 95), "Electronic": (0.7, 0.8, 128),
                "Jazz": (0.4, 0.3, 120), "Classical": (0.2, 0.2, 100),
                "R&B": (0.6, 0.5, 100), "Latin": (0.8, 0.7, 110),
            }
            d, e, t = feature_defaults.get(genre, (0.5, 0.5, 120))
            await session.execute(text("""
                INSERT IGNORE INTO track_features
                (track_id, danceability, energy, tempo, valence, acousticness)
                VALUES (:track_id, :danceability, :energy, :tempo, :valence, :acousticness)
            """), {
                "track_id": track_id,
                "danceability": round(random.gauss(d, 0.15), 3),
                "energy": round(random.gauss(e, 0.15), 3),
                "tempo": round(random.gauss(t, 20), 1),
                "valence": round(random.uniform(0.1, 0.9), 3),
                "acousticness": round(random.uniform(0.01, 0.6), 3),
            })

            await session.execute(text("""
                INSERT IGNORE INTO track_tags (track_id, tag_id) VALUES (:track_id, :tag_id)
            """), {"track_id": track_id, "tag_id": tag_id})

            genre_tracks.setdefault(genre, []).append(track_id)
            created += 1

        total_created += created
        if created > 0:
            logger.info(f"  Created {created} tracks for genre '{genre}' (had {existing})")

    if total_created > 0:
        await session.flush()
        logger.info(f"Total synthetic tracks created: {total_created}")


async def _load_tracks_from_db(session) -> tuple[dict, dict, list]:
    """Load track-genre mapping from MySQL."""
    result = await session.execute(text("""
        SELECT t.track_id, t.duration_ms, tg.tag_name
        FROM tracks t
        LEFT JOIN track_tags tt ON t.track_id = tt.track_id
        LEFT JOIN tags tg ON tt.tag_id = tg.tag_id
        WHERE t.status = 1
    """))
    rows = result.fetchall()

    genre_tracks: dict[str, list[str]] = {}
    track_durations: dict[str, int] = {}
    for track_id, duration_ms, tag_name in rows:
        if track_id not in track_durations:
            track_durations[track_id] = duration_ms or 30000
        if tag_name:
            genre_tracks.setdefault(tag_name, []).append(track_id)

    all_track_ids = list(track_durations.keys())
    return genre_tracks, track_durations, all_track_ids


async def _clear_old_data(session):
    """Remove old synthetic / lastfm users and their interactions."""
    for prefix in ("synth_user_%", "lastfm_user_%"):
        result = await session.execute(
            text("SELECT user_id FROM users WHERE username LIKE :prefix"),
            {"prefix": prefix},
        )
        user_ids = [row[0] for row in result.fetchall()]
        if user_ids:
            # Delete interactions
            for uid in user_ids:
                await session.execute(
                    text("DELETE FROM user_interactions WHERE user_id = :uid"),
                    {"uid": uid},
                )
            # Delete users
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
    logger.info("Last.FM 1K Data Generator")
    logger.info(f"Target: {NUM_TARGET_USERS} users, ~200K+ interactions")
    logger.info("=" * 60)

    # 1. Download / cache
    tsv_path = _download_lastfm_1k()

    # 2. Extract user profiles
    profiles = _extract_user_profiles(tsv_path)
    if not profiles:
        logger.error("No valid user profiles extracted. Check ARTIST_GENRE_MAP coverage.")
        return

    # 3. Select users with genre diversity
    selected = _select_users(profiles, NUM_TARGET_USERS)

    # 4. Connect to DB and load tracks
    engine = create_async_engine(DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        genre_tracks, track_durations, all_track_ids = await _load_tracks_from_db(session)
        if not all_track_ids:
            logger.error("No tracks found in database. Run seed_data.py first.")
            await engine.dispose()
            return

        logger.info(f"Track catalog: {len(all_track_ids)} tracks across {len(genre_tracks)} genres")
        for g, tracks in sorted(genre_tracks.items()):
            logger.info(f"  {g}: {len(tracks)} tracks")

        # Ensure each genre has enough tracks for realistic interactions
        logger.info("Ensuring minimum track coverage per genre...")
        await _ensure_genre_tracks(session, genre_tracks)

        # Reload after expansion
        all_track_ids = list(track_durations.keys())
        for tids in genre_tracks.values():
            for tid in tids:
                if tid not in track_durations:
                    track_durations[tid] = 30000  # default for synthetic tracks
        logger.info(f"Expanded catalog: {len(all_track_ids)} tracks total")

        # 5. Clear old data
        logger.info("Clearing old synthetic / lastfm data...")
        await _clear_old_data(session)
        await session.commit()

        # 6. Generate and insert users + interactions
        total_interactions = 0
        batch_interactions = []

        logger.info(f"Generating {len(selected)} users with realistic interactions...")
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

            interactions = _generate_interactions_for_user(
                prefs, genre_tracks, all_track_ids, track_durations,
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
        logger.info("=" * 60)

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(generate())
