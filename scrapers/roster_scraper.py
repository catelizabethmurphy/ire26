#!/usr/bin/env python3
"""
NCAA Men's Basketball Roster Scraper
=====================================
Scrapes player names and social media handles from college athletic roster pages.
Handles Sidearm Sports, custom WordPress, and other common NCAA site platforms.

Usage:
    python roster_scraper.py                         # uses team_roster_links.csv in same directory
    python roster_scraper.py --input my_links.csv    # custom input file
    python roster_scraper.py --output results.csv    # custom output file
    python roster_scraper.py --delay 3               # 3 second delay between requests (default: 2)

Requirements:
    pip install requests beautifulsoup4 lxml pandas

    For JS-rendered Sidearm NextGen sites (auto-detected):
    pip install playwright && playwright install chromium
    (Falls back to Selenium if Playwright unavailable: pip install selenium)
"""

import argparse
import csv
import json
import logging
import os
import re
import sys
import time
from typing import Optional
from urllib.parse import urljoin, urlparse

import pandas as pd
import requests
from bs4 import BeautifulSoup, Tag

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# Social platforms we care about
SOCIAL_PATTERNS = {
    "instagram": re.compile(r"instagram\.com/([A-Za-z0-9_.]+)", re.I),
    "twitter":   re.compile(r"(?:twitter\.com|x\.com)/([A-Za-z0-9_]+)", re.I),
    "tiktok":    re.compile(r"tiktok\.com/@([A-Za-z0-9_.]+)", re.I),
    "facebook":  re.compile(r"facebook\.com/([A-Za-z0-9_.]+)", re.I),
}

# Strings that signal a coach/staff row — case-insensitive match
STAFF_KEYWORDS = [
    "head coach", "assistant coach", "coach", "director", "manager",
    "trainer", "coordinator", "analyst", "grad assistant", "video",
    "student manager", "staff", "operations", "support", "strength",
    "equipment", "athletic trainer", "sports medicine",
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("roster_scraper")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def is_staff(text: str) -> bool:
    """Return True if the text looks like a coach / staff label."""
    low = text.lower().strip()
    return any(kw in low for kw in STAFF_KEYWORDS)


def extract_social_handles(element: Tag) -> dict[str, str]:
    """Pull social handles from all <a> tags inside an element."""
    handles: dict[str, str] = {}
    for a_tag in element.find_all("a", href=True):
        href = a_tag["href"]
        for platform, pattern in SOCIAL_PATTERNS.items():
            m = pattern.search(href)
            if m:
                handle = m.group(1).strip().rstrip("/")
                if not _is_valid_handle(handle, platform):
                    continue
                handles[platform] = handle
    return handles


def _is_valid_handle(handle: str, platform: str) -> bool:
    """Validate a social media handle."""
    if not handle:
        return False
    low = handle.lower()
    # Reject known junk values
    if low in ("", "share", "intent", "home", "s", "p", "l", "explore",
               "about", "help", "settings", "login", "signup", "search",
               "https", "http", "www", "url", "link", "profile", "user",
               "page", "pages", "watch", "channel", "hashtag", "stories"):
        return False
    # Min length: real handles are at least 2 chars
    if len(handle) < 2:
        return False
    # Max length: platform-specific
    max_len = 15 if platform == "twitter" else 30
    if len(handle) > max_len:
        return False
    return True


def clean_name(raw: str) -> str:
    """Normalize whitespace and strip jersey numbers / common prefixes from a player name."""
    name = re.sub(r"\s+", " ", raw).strip()              # collapse whitespace

    # Strip common link-text prefixes (case-insensitive)
    # Handles: "Full Bio 5 Collin Chandler", "View Profile Collin Chandler", "Bio: Collin Chandler"
    name = re.sub(r"^(?:Full\s+Bio|View\s+(?:Full\s+)?(?:Bio|Profile)|Bio\s*:?)\s*", "", name, flags=re.I)

    # Strip leading jersey number: "#5 ", "5 ", "05 "
    name = re.sub(r"^\s*#?\d{1,3}\s+", "", name)

    # Strip trailing jersey number: "Collin Chandler 5"
    name = re.sub(r"\s+#?\d{1,3}\s*$", "", name)

    name = re.sub(r"\s*-\s*$", "", name).strip()          # trailing dash
    return name


def is_valid_player_name(name: str) -> bool:
    """Return False for names that are clearly not real player names."""
    if not name or len(name) < 3:
        return False
    low = name.lower().strip()
    # Reject "Jersey Number X", "Photo", "Headshot", navigation items, etc.
    REJECT_NAMES = {
        "photo", "headshot", "no image", "placeholder", "roster",
        "print", "download", "pdf", "schedule", "news", "stats",
        "coaches", "staff", "coaching staff", "support staff",
        "sort", "filter", "search", "loading", "go",
    }
    if low in REJECT_NAMES:
        return False
    if low.startswith("jersey number") or low.startswith("jersey "):
        return False
    if low.startswith("roster for ") or low.startswith("schedule for "):
        return False
    # Must contain at least one letter
    if not re.search(r"[a-zA-Z]", name):
        return False
    return True


def is_staff_url(url: str) -> bool:
    """Return True if the URL looks like a coach/staff bio, not a player bio."""
    low = url.lower()
    return any(x in low for x in [
        "/staff/", "/coach/", "/coache", "/coaches/", "/support-staff/",
        "/coaching-staff/", "/staff-directory/",
    ])


def extract_social_from_bio_page(session: requests.Session, bio_url: str) -> dict[str, str]:
    """Follow a player's bio link and scrape social handles from that page."""
    handles: dict[str, str] = {}
    try:
        r = session.get(bio_url, headers=HEADERS, timeout=15)
        if r.status_code != 200:
            return handles
        soup = BeautifulSoup(r.text, "lxml")

        # --- Strategy: look in player-specific content areas first ---
        # Sidearm bio pages put player socials inside these containers:
        PLAYER_SECTIONS = [
            ".sidearm-roster-player-social",       # Sidearm dedicated social block
            ".sidearm-roster-player-details",       # Sidearm player details
            ".sidearm-roster-player-bio",           # Sidearm bio section
            '[class*="player-social"]',             # Generic player social
            '[class*="player-details"]',            # Generic player details
            '[class*="player-info"]',               # Generic player info
            "#main-content",                        # WMT main content area
            "main",                                 # Semantic main
            '[role="main"]',                        # ARIA main
            "article",                              # Article container
        ]

        search_scope = None
        for sel in PLAYER_SECTIONS:
            found = soup.select_one(sel)
            if found:
                search_scope = found
                break

        if search_scope is None:
            search_scope = soup  # fallback to whole page (less reliable)

        for a_tag in search_scope.find_all("a", href=True):
            href = a_tag["href"]
            for platform, pattern in SOCIAL_PATTERNS.items():
                if platform in handles:
                    continue
                m = pattern.search(href)
                if m:
                    handle = m.group(1).strip().rstrip("/")
                    if _is_valid_handle(handle, platform):
                        handles[platform] = handle

        # --- Filter out likely team accounts ---
        # Team accounts tend to appear identically across all players on a roster.
        # We can't detect that here (single page), but we can filter handles that
        # match known team account patterns (e.g., all the same sport suffix)
        handles = _filter_team_accounts(handles, bio_url)

    except Exception as e:
        log.debug(f"  Bio page fetch failed ({bio_url}): {e}")
    return handles


def _filter_team_accounts(handles: dict[str, str], bio_url: str) -> dict[str, str]:
    """
    Heuristic: filter out handles that are likely team/department accounts.
    Team accounts often contain sport abbreviations or the school name pattern.
    """
    # Common team-account substrings (case-insensitive)
    TEAM_PATTERNS = [
        "baseball", "bsb", "softball", "football", "soccer", "volleyball",
        "swimming", "tennis", "golf", "track", "lacrosse", "rowing",
        "gymnastics", "wrestling", "hockey", "mbb", "wbb",
    ]

    # If the bio URL is for basketball, flag handles that contain other-sport terms
    url_lower = bio_url.lower()
    is_basketball = "basketball" in url_lower or "mbball" in url_lower or "bball" in url_lower

    filtered = {}
    for platform, handle in handles.items():
        handle_lower = handle.lower()

        # Skip if it looks like a generic team/school account
        # (ends with BSB, Baseball, MBB, etc. and doesn't look like a person's name)
        is_team = False
        if is_basketball:
            # For basketball players, handles ending in non-basketball sport terms are suspect
            for tp in TEAM_PATTERNS:
                if handle_lower.endswith(tp) or handle_lower == tp:
                    is_team = True
                    break

        if not is_team:
            filtered[platform] = handle

    return filtered


# ---------------------------------------------------------------------------
# Parser: Sidearm Sports (covers ~90% of D1 sites)
# ---------------------------------------------------------------------------

def parse_sidearm(soup: BeautifulSoup, base_url: str, session: requests.Session,
                  follow_bios: bool = True) -> list[dict]:
    """
    Parse a Sidearm Sports roster page.
    These use .sidearm-roster-player containers with structured data inside.
    """
    players = []

    containers = soup.select(".sidearm-roster-player")
    if not containers:
        # Some Sidearm sites use a table layout
        containers = soup.select(".sidearm-roster-players tr, .sidearm-roster-players li")

    for el in containers:
        # --- Skip coaches/staff ---
        full_text = el.get_text(" ", strip=True)
        if is_staff(full_text):
            continue

        # --- Player name ---
        name_el = (
            el.select_one(".sidearm-roster-player-name h3 a")
            or el.select_one(".sidearm-roster-player-name h3")
            or el.select_one(".sidearm-roster-player-name a")
            or el.select_one(".sidearm-roster-player-name")
            or el.select_one("a[href*='/roster/']")  # fallback bio link text
        )
        if not name_el:
            continue

        raw_name = name_el.get_text(" ", strip=True)
        name = clean_name(raw_name)
        if not is_valid_player_name(name):
            continue

        # --- Position check: skip if position text is staff-like ---
        pos_el = el.select_one(".sidearm-roster-player-position, .sidearm-roster-player-position-short")
        if pos_el and is_staff(pos_el.get_text()):
            continue

        # --- Social handles from roster card ---
        handles = extract_social_handles(el)

        # --- Bio link (for deeper social scraping) ---
        bio_link = None
        if name_el.name == "a" and name_el.get("href"):
            bio_link = urljoin(base_url, name_el["href"])
        else:
            a_parent = el.select_one("a[href*='/roster/']") or el.select_one("a[href*='/bio/']")
            if a_parent:
                bio_link = urljoin(base_url, a_parent["href"])

        # Follow bio page if we don't have socials yet
        if follow_bios and not handles and bio_link and not is_staff_url(bio_link):
            handles = extract_social_from_bio_page(session, bio_link)

        # Skip if the bio URL is a staff/coach page
        if bio_link and is_staff_url(bio_link):
            continue

        # Filter out likely team accounts from handles
        handles = _filter_team_accounts(handles, bio_link or url)

        players.append({
            "player_name": name,
            "bio_url": bio_link or "",
            **{f"{p}_handle": handles.get(p, "") for p in SOCIAL_PATTERNS},
        })

    return players


# ---------------------------------------------------------------------------
# Parser: WMT Digital (Virginia, Arkansas, Vanderbilt, etc.)
# ---------------------------------------------------------------------------

def detect_wmt(soup: BeautifulSoup) -> bool:
    """Return True if the page appears to be a WMT Digital / wmt.digital site."""
    # Check for WMT footer branding or meta
    if soup.find("a", href=lambda h: h and "wmt.digital" in h):
        return True
    if soup.find("meta", attrs={"content": lambda c: c and "wmt" in c.lower()}):
        return True
    # Virginia-style: imgproxy URLs with storage.googleapis.com
    if soup.find("img", src=lambda s: s and "imgproxy" in s):
        return True
    # Arkansas-style: WordPress theme with arkansasTheme or similar WMT patterns
    if soup.find("link", href=lambda h: h and "wmt" in h.lower()):
        return True
    return False


def parse_wmt(soup: BeautifulSoup, base_url: str, session: requests.Session,
              follow_bios: bool = True) -> list[dict]:
    """
    Parse WMT Digital roster pages.
    These come in two flavors:
      - Card layout (Virginia/BYU-style): player cards with h3 name links and inline social links
      - Table layout (Arkansas-style): standard HTML table with name column
    
    WMT player bio links follow patterns like:
      /sports/mbball/roster/player/malik-thomas
      /roster/darius-acuff-jr/
    Nav links look like:
      /sports/baseball/roster          (sport-level roster page)
      /sports/baseball/roster#coaches  (anchor to coaches section)
    """
    players = []

    # --- Collect all links containing /roster/ ---
    all_roster_links = soup.find_all("a", href=lambda h: h and "/roster/" in h)

    # --- Filter to only genuine player bio links ---
    base_path = urlparse(base_url).path.rstrip("/")  # e.g. /sports/mens-basketball/roster

    seen_urls = set()
    player_links = []
    for a_tag in all_roster_links:
        href = a_tag.get("href", "")
        full_url = urljoin(base_url, href)
        parsed = urlparse(full_url)
        path = parsed.path.rstrip("/")

        # Skip the roster page itself
        if path == base_path:
            continue

        # Skip URLs with query strings (print=true, etc.) — player bios don't have these
        if parsed.query:
            continue

        # Skip obvious non-player paths
        if any(x in href.lower() for x in ["/coache", "/support-staff/", "/staff/", "/season/", "/#", "#coaches"]):
            continue

        # Also use the general staff-URL detector
        if is_staff_url(full_url):
            continue

        # KEY FILTER: Player bio links have MORE path segments than a sport roster page.
        # Sport roster pages: /sports/baseball/roster (3 segments)
        # Player bios:        /sports/mbball/roster/player/name (5 segments)
        #                     /roster/player-slug (2 segments, but slug isn't a sport name)
        #
        # Strategy: the link must either:
        #   a) contain /roster/player/ explicitly, OR
        #   b) be a child path of the CURRENT roster page (same base path + extra segments), OR
        #   c) start with /roster/ and have a slug that looks like a person name (contains hyphen)
        is_player_bio = False

        # (a) Explicit /roster/player/ pattern (Virginia, BYU)
        if "/roster/player/" in path:
            is_player_bio = True
        # (b) Child of current roster path (e.g., base is /sports/mbball/roster, link is /sports/mbball/roster/player/x)
        elif path.startswith(base_path + "/"):
            extra = path[len(base_path)+1:]
            # Must have meaningful content after the base path
            if extra and not extra.startswith("#"):
                is_player_bio = True
        # (c) Direct /roster/slug pattern (Arkansas: /roster/darius-acuff-jr/)
        elif re.match(r"^/roster/[a-z0-9]", path, re.I):
            slug = path.split("/roster/")[1].split("/")[0]
            # Player slugs typically contain hyphens (first-last) and are longer than sport abbreviations
            if "-" in slug and len(slug) > 4:
                is_player_bio = True

        if not is_player_bio:
            continue
        if full_url in seen_urls:
            continue

        name_text = a_tag.get_text(" ", strip=True)
        if not name_text or len(name_text) < 2:
            continue
        if is_staff(name_text):
            continue

        seen_urls.add(full_url)
        player_links.append((a_tag, full_url, name_text))

    if player_links:
        # --- Pre-index: collect ALL social links on the page for name-based matching ---
        # WMT sites label social links like "Robert Wright III Twitter Opens in a new window"
        # So we can match social links to players by checking if the link text contains the player name
        all_social_links = []
        for a_tag_s in soup.find_all("a", href=True):
            href = a_tag_s["href"]
            for platform, pattern in SOCIAL_PATTERNS.items():
                m = pattern.search(href)
                if m:
                    handle = m.group(1).strip().rstrip("/")
                    if _is_valid_handle(handle, platform):
                        link_text = a_tag_s.get_text(" ", strip=True).lower()
                        all_social_links.append((platform, handle, link_text, a_tag_s))

        for a_tag, bio_url, raw_name in player_links:
            name = clean_name(raw_name)
            if not is_valid_player_name(name):
                continue

            handles = {}

            # --- Strategy 1: Match social links by player name in link text ---
            # WMT labels socials like "AJ Dybantsa Twitter Opens in a new window"
            name_lower = name.lower()
            # Try full name first, then last name
            name_parts = name_lower.split()
            last_name = name_parts[-1] if name_parts else ""
            first_name = name_parts[0] if name_parts else ""

            for platform, handle, link_text, _ in all_social_links:
                if platform in handles:
                    continue
                # Match if the link text contains the player's full name or last name
                if name_lower in link_text or (last_name and len(last_name) > 2 and last_name in link_text and first_name in link_text):
                    handles[platform] = handle

            # --- Strategy 2: If no name-matched socials, try limited parent walk (max 3 levels) ---
            if not handles:
                parent = a_tag.parent
                for _ in range(3):
                    if parent is None:
                        break
                    # Check if this parent contains ANY other player bio links — if so, stop
                    sibling_player_links = [
                        l for l in parent.find_all("a", href=lambda h: h and ("/roster/player/" in h if h else False))
                        if l.get("href") != a_tag.get("href")
                    ]
                    if sibling_player_links:
                        break  # we've gone above the card boundary
                    handles = extract_social_handles(parent)
                    if handles:
                        break
                    parent = parent.parent

            # Follow bio page if needed
            if follow_bios and not handles and bio_url:
                handles = extract_social_from_bio_page(session, bio_url)

            players.append({
                "player_name": name,
                "bio_url": bio_url,
                **{f"{p}_handle": handles.get(p, "") for p in SOCIAL_PATTERNS},
            })

    # Deduplicate by name (some pages link the same player multiple times)
    if players:
        seen_names = set()
        deduped = []
        for p in players:
            key = p["player_name"].lower()
            if key not in seen_names:
                seen_names.add(key)
                deduped.append(p)
        players = deduped

    return players


# ---------------------------------------------------------------------------
# Parser: Generic table-based roster
# ---------------------------------------------------------------------------

def parse_table_roster(soup: BeautifulSoup, base_url: str, session: requests.Session,
                       follow_bios: bool = True) -> list[dict]:
    """
    Fallback parser for sites that render the roster as an HTML <table>.
    Identifies the name column heuristically.
    """
    players = []
    tables = soup.select("table")

    for table in tables:
        headers = [th.get_text(strip=True).lower() for th in table.select("thead th, thead td, tr:first-child th, tr:first-child td")]

        # Find name column index
        name_idx = None
        for i, h in enumerate(headers):
            if any(kw in h for kw in ("name", "player", "athlete")):
                name_idx = i
                break
        if name_idx is None:
            continue  # not a roster table

        rows = table.select("tbody tr") or table.select("tr")[1:]  # skip header row
        for row in rows:
            cells = row.select("td, th")
            if len(cells) <= name_idx:
                continue

            full_text = row.get_text(" ", strip=True)
            if is_staff(full_text):
                continue

            name_cell = cells[name_idx]
            name_link = name_cell.select_one("a")
            raw_name = name_cell.get_text(" ", strip=True)
            name = clean_name(raw_name)
            if not is_valid_player_name(name):
                continue

            handles = extract_social_handles(row)

            bio_link = ""
            if name_link and name_link.get("href"):
                bio_link = urljoin(base_url, name_link["href"])

            if follow_bios and not handles and bio_link:
                handles = extract_social_from_bio_page(session, bio_link)

            players.append({
                "player_name": name,
                "bio_url": bio_link,
                **{f"{p}_handle": handles.get(p, "") for p in SOCIAL_PATTERNS},
            })

        if players:
            break  # found a valid roster table

    return players


# ---------------------------------------------------------------------------
# Parser: Generic card/div-based roster (WordPress themes, custom sites)
# ---------------------------------------------------------------------------

def parse_generic_roster(soup: BeautifulSoup, base_url: str, session: requests.Session,
                         follow_bios: bool = True) -> list[dict]:
    """
    Broad heuristic parser for non-Sidearm sites.
    Looks for repeated card-like structures containing player names.
    """
    players = []

    # Common selectors for player cards across various CMS themes
    CARD_SELECTORS = [
        ".roster-player",
        ".player-card",
        ".roster__player",
        ".s-person-card",
        '[class*="roster"] [class*="player"]',
        '[class*="roster"] li',
        '[class*="roster"] article',
        ".person-card",
        ".team-member",
        ".roster-item",
        ".player",
    ]

    cards = []
    for sel in CARD_SELECTORS:
        cards = soup.select(sel)
        if cards:
            break

    if not cards:
        return players

    for card in cards:
        full_text = card.get_text(" ", strip=True)
        if is_staff(full_text):
            continue

        # Try common name selectors
        name_el = None
        for sel in [
            "h3 a", "h3", "h4 a", "h4", "h2 a", "h2",
            '[class*="name"] a', '[class*="name"]',
            ".title a", ".title",
            "a[href*='roster']", "a[href*='bio']",
        ]:
            name_el = card.select_one(sel)
            if name_el:
                break

        if not name_el:
            continue

        raw_name = name_el.get_text(" ", strip=True)
        name = clean_name(raw_name)
        if not is_valid_player_name(name):
            continue

        handles = extract_social_handles(card)

        bio_link = ""
        if name_el.name == "a" and name_el.get("href"):
            bio_link = urljoin(base_url, name_el["href"])

        if follow_bios and not handles and bio_link:
            handles = extract_social_from_bio_page(session, bio_link)

        players.append({
            "player_name": name,
            "bio_url": bio_link,
            **{f"{p}_handle": handles.get(p, "") for p in SOCIAL_PATTERNS},
        })

    return players


# ---------------------------------------------------------------------------
# Parser: Sidearm NextGen API (for JS-rendered sites)
# ---------------------------------------------------------------------------

def parse_sidearm_api(base_url: str, session: requests.Session) -> list[dict]:
    """
    Try to fetch roster data from Sidearm NextGen's internal JSON API.
    These sites serve roster data via endpoints like:
      {domain}/services/responsive-roster.ashx?path=mbball
      {domain}/api/roster/players?path=mbball
    
    The 'path' param is the sport identifier (e.g., mbball, mbball, wbball).
    """
    parsed = urlparse(base_url)
    domain = f"{parsed.scheme}://{parsed.netloc}"

    # Extract sport path from URL — e.g., /sports/mens-basketball/roster → mbball or mens-basketball
    url_path = parsed.path.rstrip("/")
    path_parts = url_path.split("/")

    # Try to find the sport segment
    sport_paths = []
    if "sports" in path_parts:
        idx = path_parts.index("sports")
        if idx + 1 < len(path_parts):
            sport_paths.append(path_parts[idx + 1])  # e.g., "mens-basketball"

    # Also try common Sidearm sport abbreviations
    sport_abbrevs = {
        "mens-basketball": ["mbball", "mbask"],
        "womens-basketball": ["wbball", "wbask"],
        "football": ["football", "fball"],
        "baseball": ["baseball", "bsb"],
    }
    for sp in sport_paths:
        if sp in sport_abbrevs:
            sport_paths.extend(sport_abbrevs[sp])

    # Also try path=mens-basketball directly
    if not sport_paths:
        sport_paths = ["mbball", "mens-basketball"]

    # Try various API endpoints
    api_patterns = [
        "{domain}/services/responsive-roster.ashx?path={path}",
        "{domain}/services/responsive-roster.ashx?path={path}&year=2025-26",
        "{domain}/api/roster/players?path={path}",
    ]

    for path in sport_paths:
        for pattern in api_patterns:
            api_url = pattern.format(domain=domain, path=path)
            try:
                resp = session.get(api_url, headers={**HEADERS, "Accept": "application/json"}, timeout=10)
                if resp.status_code != 200:
                    continue

                # Check if it's JSON
                try:
                    data = resp.json()
                except (ValueError, json.JSONDecodeError):
                    # Might be HTML — try parsing as HTML table
                    if "<table" in resp.text.lower() or "<tr" in resp.text.lower():
                        soup = BeautifulSoup(resp.text, "lxml")
                        players = _parse_sidearm_api_html(soup, base_url, session)
                        if players:
                            log.info(f"  Sidearm API (HTML): {api_url} → {len(players)} players")
                            return players
                    continue

                # Parse JSON response
                players = _parse_sidearm_api_json(data, base_url, session)
                if players:
                    log.info(f"  Sidearm API (JSON): {api_url} → {len(players)} players")
                    return players

            except requests.RequestException:
                continue

    return []


def _parse_sidearm_api_json(data, base_url: str, session: requests.Session) -> list[dict]:
    """Parse Sidearm NextGen JSON roster response."""
    players = []

    # The JSON structure varies but commonly has a list of player objects
    player_list = []
    if isinstance(data, list):
        player_list = data
    elif isinstance(data, dict):
        # Try common keys
        for key in ["players", "roster", "data", "athletes", "items", "section_players"]:
            if key in data and isinstance(data[key], list):
                player_list = data[key]
                break
        # Some responses nest players under sections
        if not player_list and "sections" in data:
            for section in data.get("sections", []):
                if isinstance(section, dict):
                    for key in ["players", "items", "data"]:
                        if key in section and isinstance(section[key], list):
                            player_list.extend(section[key])

    for p in player_list:
        if not isinstance(p, dict):
            continue

        # Extract name
        name = ""
        for nk in ["full_name", "fullname", "name", "display_name", "playerName"]:
            if nk in p and p[nk]:
                name = str(p[nk]).strip()
                break
        if not name:
            first = p.get("first_name", p.get("firstName", p.get("first", "")))
            last = p.get("last_name", p.get("lastName", p.get("last", "")))
            if first and last:
                name = f"{first} {last}"

        if not name or not is_valid_player_name(clean_name(name)):
            continue

        # Skip coaches/staff
        position = str(p.get("position", p.get("pos", p.get("position_short", "")))).lower()
        if is_staff(position) or is_staff(name):
            continue

        # Extract social handles
        handles = {}
        social_data = p.get("social", p.get("social_media", p.get("socials", {})))
        if isinstance(social_data, dict):
            for platform in SOCIAL_PATTERNS:
                val = social_data.get(platform, "")
                if val and _is_valid_handle(str(val), platform):
                    handles[platform] = str(val)
        elif isinstance(social_data, list):
            for item in social_data:
                if isinstance(item, dict):
                    platform = str(item.get("platform", item.get("type", ""))).lower()
                    handle = str(item.get("handle", item.get("username", item.get("url", ""))))
                    # If it's a full URL, extract handle
                    for plat, pat in SOCIAL_PATTERNS.items():
                        m = pat.search(handle)
                        if m and _is_valid_handle(m.group(1), plat):
                            handles[plat] = m.group(1)

        # Extract bio URL
        bio_url = p.get("bio_url", p.get("url", p.get("link", p.get("rosterBioUrl", ""))))
        if bio_url and not bio_url.startswith("http"):
            bio_url = urljoin(base_url, bio_url)

        # If no socials from JSON, try bio page
        if not handles and bio_url and not is_staff_url(bio_url):
            handles = extract_social_from_bio_page(session, bio_url)

        players.append({
            "player_name": clean_name(name),
            "bio_url": bio_url or "",
            **{f"{p_name}_handle": handles.get(p_name, "") for p_name in SOCIAL_PATTERNS},
        })

    return players


def _parse_sidearm_api_html(soup: BeautifulSoup, base_url: str, session: requests.Session) -> list[dict]:
    """Parse Sidearm's HTML roster response (some API endpoints return HTML fragments)."""
    # Try the standard table and Sidearm parsers on the HTML fragment
    players = parse_sidearm(soup, base_url, session, follow_bios=True)
    if not players:
        players = parse_table_roster(soup, base_url, session, follow_bios=True)
    return players


# ---------------------------------------------------------------------------
# Parser: ESPN fallback (for sites where all other methods fail)
# ---------------------------------------------------------------------------

def parse_espn_fallback(team: str, session: requests.Session) -> list[dict]:
    """
    Scrape roster from ESPN as a last resort.
    Returns player names with empty social handles.
    ESPN serves server-rendered HTML — always works.
    """
    # Search ESPN for the team's roster page
    search_query = team.replace("St.", "State").replace(".", "")
    espn_search_url = f"https://www.espn.com/mens-college-basketball/team/roster/_/id/"

    # We need the ESPN team ID. Try searching ESPN's site.
    try:
        search_url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/teams?limit=200"
        r = session.get(search_url, headers=HEADERS, timeout=15)
        if r.status_code == 200:
            try:
                data = r.json()
                teams_list = data.get("sports", [{}])[0].get("leagues", [{}])[0].get("teams", [])
                # Find matching team
                team_lower = team.lower().replace("st.", "state").replace(".", "")
                espn_id = None
                for t in teams_list:
                    t_info = t.get("team", t)
                    names_to_check = [
                        t_info.get("displayName", "").lower(),
                        t_info.get("shortDisplayName", "").lower(),
                        t_info.get("name", "").lower(),
                        t_info.get("location", "").lower(),
                    ]
                    if any(team_lower in n or n in team_lower for n in names_to_check if n):
                        espn_id = t_info.get("id")
                        break

                if not espn_id:
                    log.debug(f"  ESPN: couldn't find team ID for '{team}'")
                    return []

                # Fetch roster page
                roster_url = f"https://www.espn.com/mens-college-basketball/team/roster/_/id/{espn_id}"
                rr = session.get(roster_url, headers=HEADERS, timeout=15)
                if rr.status_code != 200:
                    return []

                soup = BeautifulSoup(rr.text, "lxml")

                # ESPN roster is in a table
                players = []
                for row in soup.select("table tbody tr"):
                    cells = row.select("td")
                    if len(cells) < 2:
                        continue
                    # Name is typically in the second cell (first is photo)
                    name_cell = cells[1]
                    name_link = name_cell.select_one("a")
                    if name_link:
                        raw_name = name_link.get_text(strip=True)
                    else:
                        raw_name = name_cell.get_text(strip=True)

                    # Strip jersey number from name
                    name = clean_name(raw_name)
                    if not is_valid_player_name(name):
                        continue
                    if is_staff(name):
                        continue

                    players.append({
                        "player_name": name,
                        "bio_url": "",
                        **{f"{p}_handle": "" for p in SOCIAL_PATTERNS},
                    })

                if players:
                    log.info(f"  ESPN fallback → {len(players)} players (no social handles)")
                return players

            except (ValueError, KeyError, IndexError) as e:
                log.debug(f"  ESPN API parse error: {e}")
                return []
    except requests.RequestException as e:
        log.debug(f"  ESPN fallback failed: {e}")

    return []


# ---------------------------------------------------------------------------
# Dispatcher: pick the right parser for each page
# ---------------------------------------------------------------------------

def scrape_roster(team: str, url: str, session: requests.Session,
                  follow_bios: bool = True) -> list[dict]:
    """Fetch a roster page and dispatch to the correct parser."""
    try:
        r = session.get(url, headers=HEADERS, timeout=20, allow_redirects=True)
        r.raise_for_status()
    except requests.RequestException as e:
        log.error(f"  [{team}] Request failed: {e}")
        return []

    soup = BeautifulSoup(r.text, "lxml")

    MIN_ROSTER = 5  # basketball rosters have at least ~8 players; flag anything below 5

    # --- Detect JS-rendered pages (Sidearm NextGen uses Angular templates) ---
    page_text = r.text
    page_lower = page_text.lower()
    is_js_rendered = (
        "{{ roster.title }}" in page_text
        or "{{ template.label }}" in page_text
        or ("sidearm" in page_lower and "ng-app" in page_lower)
        # Sidearm NextGen: has sidearm branding but no actual rendered roster content
        or ("sidearm" in page_lower and "nextgen" in page_lower)
        or ("sidearm.nextgen" in page_lower)
        # Has sidearm indicators but roster section is empty (Angular not rendered)
        or ("sidearm" in page_lower
            and len(soup.select(".sidearm-roster-player")) == 0
            and ("roster" in page_lower))
    )

    # --- If JS-rendered, don't follow bio pages (they'll also be JS-rendered → garbage data) ---
    if is_js_rendered:
        follow_bios = False
        log.debug(f"  [{team}] JS-rendered detected — disabling bio page following")

    # --- Try parsers in order of specificity ---

    # 0) If JS-rendered, try Sidearm API first (no browser needed), then Playwright/Selenium
    if is_js_rendered:
        # Try the JSON/HTML API endpoint first — fastest and most reliable
        log.info(f"  [{team}] JS-rendered page detected — trying Sidearm API...")
        api_players = parse_sidearm_api(url, session)
        if api_players and len(api_players) >= MIN_ROSTER:
            log.info(f"  [{team}] Sidearm API → {len(api_players)} players")
            return api_players

        # Fall back to browser rendering
        log.info(f"  [{team}] Sidearm API didn't work — trying browser rendering...")
        rendered_soup = render_with_selenium(url)
        if rendered_soup:
            for parser_name, parser_fn in [
                ("Sidearm+Selenium", parse_sidearm),
                ("Table+Selenium", parse_table_roster),
                ("WMT+Selenium", parse_wmt),
                ("Generic+Selenium", parse_generic_roster),
            ]:
                sel_players = parser_fn(rendered_soup, url, session, follow_bios=True)
                if sel_players and len(sel_players) >= MIN_ROSTER:
                    log.info(f"  [{team}] {parser_name} → {len(sel_players)} players")
                    return sel_players
        log.warning(f"  [{team}] Selenium didn't yield enough players — falling back to static parsers")

    # 1) Sidearm (most NCAA D1 sites — works when content is server-rendered)
    players = parse_sidearm(soup, url, session, follow_bios)
    if players and len(players) >= MIN_ROSTER:
        log.info(f"  [{team}] Sidearm parser → {len(players)} players")
        return players

    # 2) WMT Digital (Virginia, BYU, Clemson, Arkansas, etc.)
    wmt_players = parse_wmt(soup, url, session, follow_bios)
    if wmt_players and len(wmt_players) >= MIN_ROSTER:
        log.info(f"  [{team}] WMT parser → {len(wmt_players)} players")
        return wmt_players

    # 3) HTML table roster
    table_players = parse_table_roster(soup, url, session, follow_bios)
    if table_players and len(table_players) >= MIN_ROSTER:
        log.info(f"  [{team}] Table parser → {len(table_players)} players")
        return table_players

    # 4) Generic card/div layout
    generic_players = parse_generic_roster(soup, url, session, follow_bios)
    if generic_players and len(generic_players) >= MIN_ROSTER:
        log.info(f"  [{team}] Generic parser → {len(generic_players)} players")
        return generic_players

    # 5) Last resort: if all parsers returned < 2 real players and JS wasn't detected,
    #    try Selenium anyway (some sites are JS-rendered without obvious signals)
    best_static_count = max(
        len(players) if players else 0,
        len(wmt_players) if wmt_players else 0,
        len(table_players) if table_players else 0,
        len(generic_players) if generic_players else 0,
    )
    if not is_js_rendered and best_static_count < 2:
        log.info(f"  [{team}] All parsers found < 2 players — trying Selenium as last resort...")
        rendered_soup = render_with_selenium(url)
        if rendered_soup:
            for parser_name, parser_fn in [
                ("Sidearm+Selenium", parse_sidearm),
                ("WMT+Selenium", parse_wmt),
                ("Table+Selenium", parse_table_roster),
                ("Generic+Selenium", parse_generic_roster),
            ]:
                sel_players = parser_fn(rendered_soup, url, session, follow_bios)
                if sel_players and len(sel_players) >= MIN_ROSTER:
                    log.info(f"  [{team}] {parser_name} → {len(sel_players)} players")
                    return sel_players

    # 6) If all parsers returned too few, pick the best non-empty result
    all_results = [
        ("Sidearm", players),
        ("WMT", wmt_players),
        ("Table", table_players),
        ("Generic", generic_players),
    ]
    best_name, best = max(all_results, key=lambda x: len(x[1]) if x[1] else 0)
    if best:
        log.warning(f"  [{team}] {best_name} parser → {len(best)} players (below {MIN_ROSTER} threshold — check manually)")
        return best

    log.warning(f"  [{team}] No players found — may need a custom parser or Selenium")
    return []


def render_with_selenium(url: str) -> Optional[BeautifulSoup]:
    """
    Use Playwright (preferred) or Selenium to render a JS-heavy page.
    Returns a BeautifulSoup object of the rendered HTML, or None on failure.

    Install: pip install playwright && playwright install chromium
    """
    # --- Try Playwright first ---
    try:
        from playwright.sync_api import sync_playwright
        return _render_playwright(url)
    except ImportError:
        pass

    # --- Fall back to Selenium ---
    try:
        from selenium import webdriver
        return _render_selenium(url)
    except ImportError:
        pass

    log.warning("  Neither Playwright nor Selenium installed.")
    log.warning("  Run: pip install playwright && playwright install chromium")
    log.warning("  Or:  pip install selenium")
    return None


def _render_playwright(url: str) -> Optional[BeautifulSoup]:
    """Render with Playwright (faster, more reliable than Selenium)."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=HEADERS["User-Agent"],
                viewport={"width": 1920, "height": 1080},
            )
            page = context.new_page()

            # Block unnecessary resources to speed up loading
            page.route("**/*.{png,jpg,jpeg,gif,svg,ico,woff,woff2,ttf,eot}", lambda route: route.abort())
            page.route("**/ads**", lambda route: route.abort())
            page.route("**/analytics**", lambda route: route.abort())
            page.route("**/doubleclick**", lambda route: route.abort())
            page.route("**/google-analytics**", lambda route: route.abort())
            page.route("**/scorecardresearch**", lambda route: route.abort())

            log.info(f"  Playwright: loading {url}")
            page.goto(url, wait_until="domcontentloaded", timeout=30000)

            # Wait for roster content to appear
            roster_loaded = False
            selectors_to_try = [
                ".sidearm-roster-player",
                ".sidearm-roster-player-name",
                "table.sidearm-roster tbody tr",
            ]

            for sel in selectors_to_try:
                try:
                    page.wait_for_selector(sel, timeout=15000)
                    roster_loaded = True
                    log.info(f"  Playwright: roster loaded (matched '{sel}')")
                    break
                except Exception:
                    continue

            if not roster_loaded:
                log.info(f"  Playwright: no roster selector matched, waiting 5s...")
                page.wait_for_timeout(5000)

            # Small extra wait for social links
            page.wait_for_timeout(1000)

            rendered_html = page.content()
            log.info(f"  Playwright: page source length = {len(rendered_html)}")

            rendered_soup = BeautifulSoup(rendered_html, "lxml")
            player_els = rendered_soup.select(".sidearm-roster-player")
            log.info(f"  Playwright: found {len(player_els)} .sidearm-roster-player elements")

            browser.close()
            return rendered_soup

    except Exception as e:
        log.warning(f"  Playwright rendering failed: {e}")
        return None


def _render_selenium(url: str) -> Optional[BeautifulSoup]:
    """Fallback: render with Selenium."""
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
    except ImportError:
        return None

    try:
        opts = Options()
        opts.add_argument("--headless=new")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--disable-gpu")
        opts.add_argument("--window-size=1920,1080")
        opts.add_argument(f"user-agent={HEADERS['User-Agent']}")
        prefs = {
            "profile.managed_default_content_settings.images": 2,
            "profile.managed_default_content_settings.media_stream": 2,
        }
        opts.add_experimental_option("prefs", prefs)
        opts.page_load_strategy = "eager"

        driver = webdriver.Chrome(options=opts)
        driver.set_page_load_timeout(30)

        try:
            driver.get(url)
        except Exception:
            log.info(f"  Selenium: page load timed out, continuing...")

        roster_loaded = False
        for sel in [".sidearm-roster-player", ".sidearm-roster-player-name"]:
            try:
                WebDriverWait(driver, 20).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, sel))
                )
                roster_loaded = True
                break
            except Exception:
                continue

        if not roster_loaded:
            time.sleep(8)

        rendered_html = driver.page_source
        driver.quit()
        return BeautifulSoup(rendered_html, "lxml")

    except Exception as e:
        log.warning(f"  Selenium rendering failed: {e}")
        try:
            driver.quit()
        except Exception:
            pass
        return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    # Resolve project root relative to this script's location (scrapers/ → project root)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    data_dir = os.path.join(project_root, "data", "rosters")

    parser = argparse.ArgumentParser(description="Scrape NCAA roster pages for player social handles")
    parser.add_argument("--input",  default=os.path.join(data_dir, "team_roster_links.csv"), help="CSV with team,roster_url columns")
    parser.add_argument("--output", default=os.path.join(data_dir, "roster_social_handles.csv"), help="Output CSV path")
    parser.add_argument("--delay",  type=float, default=2.0, help="Seconds between requests (be polite)")
    parser.add_argument("--no-bios", action="store_true", help="Skip following individual bio pages (faster but fewer socials)")
    parser.add_argument("--teams", nargs="*", help="Only scrape these teams (e.g. --teams Duke Arizona)")
    args = parser.parse_args()

    # --- Load input ---
    if not os.path.exists(args.input):
        log.error(f"Input file not found: {args.input}")
        sys.exit(1)

    df_input = pd.read_csv(args.input)
    # Normalize column names
    df_input.columns = [c.strip().lower() for c in df_input.columns]

    if "team" not in df_input.columns or "roster_url" not in df_input.columns:
        log.error("Input CSV must have 'team' and 'roster_url' columns")
        sys.exit(1)

    # Drop empty rows
    df_input = df_input.dropna(subset=["roster_url"])
    df_input = df_input[df_input["roster_url"].str.strip().astype(bool)]

    if args.teams:
        mask = df_input["team"].str.lower().isin([t.lower() for t in args.teams])
        df_input = df_input[mask]

    log.info(f"Loaded {len(df_input)} teams from {args.input}")

    # --- Scrape ---
    session = requests.Session()
    all_rows = []
    failed_teams = []

    # Create output directory for per-team CSVs
    team_output_dir = os.path.join(os.path.dirname(args.output) or ".", "teams")
    os.makedirs(team_output_dir, exist_ok=True)

    columns = [
        "team", "player_name",
        "instagram_handle", "twitter_handle", "tiktok_handle", "facebook_handle",
        "bio_url",
    ]

    for i, row in df_input.iterrows():
        team = row["team"].strip()
        url = row["roster_url"].strip()

        # --- Generate team filename ---
        safe_name = team.lower()
        safe_name = re.sub(r"[''`()]", "", safe_name)
        safe_name = re.sub(r"[^a-z0-9]+", "_", safe_name)
        safe_name = safe_name.strip("_")
        team_csv_path = os.path.join(team_output_dir, f"{safe_name}.csv")

        # --- Skip if already scraped (delete the file to re-scrape) ---
        if os.path.exists(team_csv_path):
            log.info(f"[{i+1}/{len(df_input)}] Skipping {team} — {team_csv_path} already exists")
            # Load existing data into combined output
            try:
                existing = pd.read_csv(team_csv_path)
                all_rows.extend(existing.to_dict("records"))
            except Exception:
                pass
            continue

        log.info(f"[{i+1}/{len(df_input)}] Scraping {team} — {url}")

        players = scrape_roster(team, url, session, follow_bios=not args.no_bios)

        if not players:
            failed_teams.append(team)

        team_rows = []
        for p in players:
            team_rows.append({"team": team, **p})

        # --- Deduplicate by player name within this team ---
        seen_names = set()
        deduped_rows = []
        for tr in team_rows:
            key = tr["player_name"].lower().strip()
            if key not in seen_names:
                seen_names.add(key)
                deduped_rows.append(tr)
        team_rows = deduped_rows

        # --- Post-process: detect contaminated handles ---
        # If the same handle appears for multiple players, it's a team account — clear it
        # Also detect shared suffixes (e.g., "ally.wright17" appended to multiple handles)
        for platform_col in ["instagram_handle", "twitter_handle", "tiktok_handle", "facebook_handle"]:
            handle_counts: dict[str, int] = {}
            for tr in team_rows:
                h = tr.get(platform_col, "")
                if h:
                    handle_counts[h] = handle_counts.get(h, 0) + 1
            # Clear any handle that appears for 3+ players (it's a team account)
            for tr in team_rows:
                h = tr.get(platform_col, "")
                if h and handle_counts.get(h, 0) >= 3:
                    tr[platform_col] = ""

        # --- Write per-team CSV ---
        if team_rows:
            df_team = pd.DataFrame(team_rows)
            for col in columns:
                if col not in df_team.columns:
                    df_team[col] = ""
            df_team[columns].to_csv(team_csv_path, index=False)
            log.info(f"  → Saved {team_csv_path} ({len(team_rows)} players)")

        all_rows.extend(team_rows)

        if i < len(df_input) - 1:
            time.sleep(args.delay)

    # --- Combined output ---
    df_out = pd.DataFrame(all_rows)

    # Ensure all columns exist
    for col in columns:
        if col not in df_out.columns:
            df_out[col] = ""

    df_out = df_out[columns]
    df_out.to_csv(args.output, index=False)

    # --- Summary ---
    total_players = len(df_out)
    with_ig = df_out["instagram_handle"].astype(bool).sum()
    with_tw = df_out["twitter_handle"].astype(bool).sum()
    with_any = df_out[["instagram_handle", "twitter_handle", "tiktok_handle", "facebook_handle"]].astype(bool).any(axis=1).sum()

    log.info(f"\n{'='*60}")
    log.info(f"DONE — {total_players} players across {len(df_input) - len(failed_teams)} teams")
    log.info(f"  Instagram handles found: {with_ig}")
    log.info(f"  Twitter/X handles found:  {with_tw}")
    log.info(f"  Any social found:         {with_any}")
    log.info(f"  Combined output: {args.output}")
    log.info(f"  Per-team CSVs:   {team_output_dir}/")

    if failed_teams:
        log.warning(f"\nFailed/empty teams ({len(failed_teams)}): {', '.join(failed_teams)}")
        failed_path = os.path.join(os.path.dirname(args.output), "failed_teams.txt")
        with open(failed_path, "w") as f:
            for t in failed_teams:
                f.write(t + "\n")
        log.info(f"  Failed teams written to {failed_path}")


if __name__ == "__main__":
    main()
