import logging
import os
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

import requests
from dotenv import dotenv_values, load_dotenv
from pkg_resources import working_set
from pymongo import MongoClient

LOG_FILE = "log.txt"

if Path(LOG_FILE).exists():
    Path(LOG_FILE).write_text("", encoding="utf-8")
if Path("rlog.txt").exists():
    Path("rlog.txt").unlink()

logging.basicConfig(
    format="[%(asctime)s] [%(levelname)s] - %(message)s",
    datefmt="%d-%b-%y %I:%M:%S %p",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()],
    level=logging.INFO,
)
log = logging.getLogger(__name__)


def run_command(args):
    """Run a command without a shell, so config values cannot become shell code."""
    return subprocess.run(
        args,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )


# Optional remote config download. A failed download does not overwrite a
# working local config file or prevent environment-based deployment.
config_url = os.environ.get("CONFIG_FILE_URL", "").strip()
if config_url:
    try:
        parsed_config_url = urlsplit(config_url)
        if parsed_config_url.scheme not in ("https", "http") or not parsed_config_url.netloc:
            raise ValueError("CONFIG_FILE_URL must be an HTTP(S) URL")
        response = requests.get(config_url, timeout=(10, 30))
        response.raise_for_status()
        Path("config.env.tmp").write_bytes(response.content)
        Path("config.env.tmp").replace("config.env")
        log.info("Downloaded remote configuration.")
    except Exception as exc:
        Path("config.env.tmp").unlink(missing_ok=True)
        log.error("CONFIG_FILE_URL failed (%s). Using existing environment/config.", type(exc).__name__)

# Keep deployment-platform variables authoritative; use config.env as fallback.
load_dotenv("config.env", override=False)

if os.environ.get("_____REMOVE_THIS_LINE_____"):
    log.error("Remove the template guard line from config.env before deploying.")
    raise SystemExit(1)

bot_token = os.environ.get("BOT_TOKEN", "").strip()
if not bot_token:
    log.error("BOT_TOKEN is missing. Set it in config.env or deployment environment.")
    raise SystemExit(1)

bot_id = bot_token.split(":", 1)[0]
database_url = os.environ.get("DATABASE_URL", "").strip()

if database_url:
    try:
        with MongoClient(
            database_url,
            serverSelectionTimeoutMS=10000,
            connectTimeoutMS=10000,
        ) as conn:
            db = conn.kpsmlx
            old_config = db.settings.deployConfig.find_one({"_id": bot_id})
            config_dict = db.settings.config.find_one({"_id": bot_id})

            if old_config is not None:
                old_config.pop("_id", None)

            current_config = dict(dotenv_values("config.env"))
            if config_dict is not None and (
                old_config is None or old_config == current_config
            ):
                upstream_repo = config_dict.get("UPSTREAM_REPO")
                upstream_branch = config_dict.get("UPSTREAM_BRANCH")
                upgrade_packages = config_dict.get("UPDATE_PACKAGES", "False")

                if upstream_repo:
                    os.environ["UPSTREAM_REPO"] = upstream_repo
                if upstream_branch:
                    os.environ["UPSTREAM_BRANCH"] = upstream_branch
                os.environ["UPGRADE_PACKAGES"] = upgrade_packages
    except Exception as exc:
        log.error("MongoDB configuration lookup failed (%s).", type(exc).__name__)
        raise SystemExit(1)

if os.environ.get("UPGRADE_PACKAGES", "False").lower() == "true":
    package_names = sorted({dist.project_name for dist in working_set})
    try:
        subprocess.run(
            ["uv", "pip", "install", "--system", *package_names],
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        log.error("Package upgrade failed (%s).", type(exc).__name__)
        raise SystemExit(1)

upstream_repo = os.environ.get(
    "UPSTREAM_REPO", "https://github.com/Tamilupdates/KPSML-X"
).strip()
upstream_branch = os.environ.get("UPSTREAM_BRANCH", "kpsmlx").strip()

# Accept normal HTTPS/SSH Git URLs; reject malformed values before invoking Git.
parsed_repo = urlsplit(upstream_repo)
if (
    parsed_repo.scheme not in ("https", "http", "ssh", "git")
    or not parsed_repo.netloc
    or not upstream_branch
):
    log.error("UPSTREAM_REPO or UPSTREAM_BRANCH is invalid.")
    raise SystemExit(1)

try:
    run_command(["git", "check-ref-format", "--branch", upstream_branch])

    git_dir = Path(".git")
    if git_dir.is_dir():
        shutil.rmtree(git_dir)
    elif git_dir.exists():
        git_dir.unlink()

    run_command(["git", "init", "-q"])
    run_command(["git", "config", "user.email", "bot-updater@localhost"])
    run_command(["git", "config", "user.name", "bot-updater"])
    run_command(["git", "add", "-A"])
    run_command(["git", "commit", "-m", "deployment snapshot", "-q"])
    run_command(["git", "remote", "add", "origin", upstream_repo])
    run_command(["git", "fetch", "--depth=1", "origin", upstream_branch])
    run_command(["git", "reset", "--hard", "FETCH_HEAD"])

    # Do not print the remote URL: private URLs may contain access credentials.
    log.info("Successfully updated from upstream branch: %s", upstream_branch)
except (OSError, subprocess.CalledProcessError) as exc:
    log.error("Upstream update failed (%s). Bot startup cancelled.", type(exc).__name__)
    raise SystemExit(1)
