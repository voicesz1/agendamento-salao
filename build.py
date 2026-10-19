"""Prepare assets for Vercel's static CDN."""

from pathlib import Path
import shutil


ROOT = Path(__file__).resolve().parent
source = ROOT / "app" / "static"
public = ROOT / "public"
shutil.copytree(source, public / "static", dirs_exist_ok=True)
shutil.copy2(source / "sw.js", public / "sw.js")
