"""Saving and loading the nation, with dated snapshots for rewinding."""
import gzip
import json
import os
import shutil

from .model import world_to_dict, world_from_dict

STATE_FILE = "world.json.gz"
EVENTS_FILE = "events.db"
SNAP_DIR = "snapshots"


def state_path(data_dir):
    return os.path.join(data_dir, STATE_FILE)


def events_path(data_dir):
    return os.path.join(data_dir, EVENTS_FILE)


def exists(data_dir):
    return os.path.exists(state_path(data_dir))


def save(world, data_dir):
    os.makedirs(data_dir, exist_ok=True)
    tmp = state_path(data_dir) + ".tmp"
    with gzip.open(tmp, "wt", encoding="utf-8") as f:
        json.dump(world_to_dict(world), f, separators=(",", ":"))
    os.replace(tmp, state_path(data_dir))   # never leaves a half-written save


def load(data_dir):
    with gzip.open(state_path(data_dir), "rt", encoding="utf-8") as f:
        return world_from_dict(json.load(f))


def snapshot(world, data_dir, keep=60):
    """Copy the current save into snapshots/, keeping the newest `keep`."""
    snaps = os.path.join(data_dir, SNAP_DIR)
    os.makedirs(snaps, exist_ok=True)
    dest = os.path.join(snaps, f"day-{world.day:07d}.json.gz")
    shutil.copy2(state_path(data_dir), dest)
    files = sorted(f for f in os.listdir(snaps) if f.startswith("day-"))
    for old in files[:-keep]:
        os.remove(os.path.join(snaps, old))
    return dest
