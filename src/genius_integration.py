"""
Genius API integration for fetching song lyrics.
Includes caching and error handling with exponential backoff.
"""
import logging
import os
import hashlib
import json
from typing import Optional, Dict, Tuple
from functools import lru_cache
import time

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


class RateLimitError(Exception):
    """Raised when the Genius API rate limit is hit."""
    pass


class LyricsNotFoundError(Exception):
    """Raised when lyrics cannot be found for a song."""
    pass


class GeniusIntegration:
    """
    Fetches song lyrics from Genius API.
    
    Requirements:
    - GENIUS_API_TOKEN environment variable with valid Genius API token
    - Implements caching to minimize API calls
    - Handles rate limiting with exponential backoff
    """
    
    BASE_URL = "https://api.genius.com"
    CACHE_DIR = ".cache/genius"
    MAX_RETRIES = 3
    BACKOFF_FACTOR = 1.0
    
    def __init__(self, api_token: Optional[str] = None):
        """
        Initialize Genius API integration.
        
        Args:
            api_token: Genius API token (defaults to GENIUS_API_TOKEN env var)
            
        Raises:
            ValueError: If no API token provided and GENIUS_API_TOKEN not set
        """
        self.api_token = api_token or os.getenv("GENIUS_API_TOKEN")
        if not self.api_token:
            raise ValueError(
                "Genius API token not provided. Set GENIUS_API_TOKEN environment variable "
                "or pass api_token parameter. Get one at https://genius.com/api-clients"
            )
        
        self._session = self._create_session()
        self._ensure_cache_dir()
    
    def _create_session(self) -> requests.Session:
        """Create HTTP session with retry logic."""
        session = requests.Session()
        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "User-Agent": "Bairry/0.1.0 (+https://github.com/gowland/bairry)"
        }
        session.headers.update(headers)
        
        retry_strategy = Retry(
            total=self.MAX_RETRIES,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST"],
            backoff_factor=self.BACKOFF_FACTOR,
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        return session
    
    def _ensure_cache_dir(self) -> None:
        """Ensure cache directory exists."""
        os.makedirs(self.CACHE_DIR, exist_ok=True)
    
    def _get_cache_key(self, song_title: str, artist_name: str) -> str:
        """Generate cache key from song and artist."""
        cache_str = f"{song_title}:{artist_name}".lower()
        return hashlib.md5(cache_str.encode()).hexdigest()
    
    def _read_cache(self, cache_key: str) -> Optional[Dict]:
        """Read lyrics from cache."""
        cache_file = os.path.join(self.CACHE_DIR, f"{cache_key}.json")
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to read cache file {cache_file}: {e}")
        return None
    
    def _write_cache(self, cache_key: str, data: Dict) -> None:
        """Write lyrics to cache."""
        cache_file = os.path.join(self.CACHE_DIR, f"{cache_key}.json")
        try:
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"Failed to write cache file {cache_file}: {e}")
    
    def search_song(self, song_title: str, artist_name: str) -> Optional[Dict]:
        """
        Search for a song on Genius.
        
        Args:
            song_title: Song title
            artist_name: Artist name (can be parsed from "feat." format)
            
        Returns:
            Song data dict with 'url' and 'title' if found, None otherwise
            
        Raises:
            RateLimitError: If API rate limit is hit
        """
        # Extract primary artist if multi-artist format
        primary_artist = self._extract_primary_artist(artist_name)
        
        try:
            response = self._session.get(
                f"{self.BASE_URL}/search",
                params={
                    "q": f"{song_title} {primary_artist}",
                    "per_page": 5,
                }
            )
            
            if response.status_code == 429:
                raise RateLimitError("Genius API rate limit exceeded")
            
            response.raise_for_status()
            
            data = response.json()
            hits = data.get("response", {}).get("hits", [])
            
            # Find best match (first result is usually best)
            for hit in hits:
                song = hit.get("result", {})
                return {
                    "url": song.get("url"),
                    "title": song.get("title"),
                    "artist": song.get("primary_artist", {}).get("name"),
                }
            
            return None
            
        except RateLimitError:
            raise
        except requests.exceptions.RequestException as e:
            logger.error(f"Error searching Genius for '{song_title}' by '{primary_artist}': {e}")
            raise LyricsNotFoundError(f"Failed to search Genius API: {e}")
        except Exception as e:
            logger.error(f"Unexpected error searching Genius for '{song_title}' by '{primary_artist}': {e}")
            raise LyricsNotFoundError(f"Failed to search Genius API: {e}")
    
    def fetch_lyrics(self, song_url: str) -> Optional[str]:
        """
        Fetch lyrics from Genius song URL using web scraping.
        
        Args:
            song_url: Full URL to Genius song page
            
        Returns:
            Raw lyrics text with newlines preserved, None if extraction fails
            
        Raises:
            LyricsNotFoundError: If lyrics cannot be extracted from page
        """
        try:
            response = requests.get(song_url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Find lyrics containers - Genius uses data-lyrics-container attribute
            lyrics_containers = soup.find_all('div', {'data-lyrics-container': 'true'})
            
            if not lyrics_containers:
                # Fallback: try older structure
                logger.debug(f"No data-lyrics-container found, trying fallback method")
                lyrics_containers = soup.find_all('div', class_='Lyrics__Container__LyricsTextContainer__Content')
            
            if not lyrics_containers:
                raise LyricsNotFoundError(f"Could not find lyrics on page: {song_url}")
            
            # Extract and combine lyrics from all containers
            lyrics_parts = []
            for container in lyrics_containers:
                # Get text and preserve line breaks
                for br in container.find_all('br'):
                    br.replace_with('\n')
                
                text = container.get_text(separator='\n', strip=True)
                if text:
                    lyrics_parts.append(text)
            
            if not lyrics_parts:
                raise LyricsNotFoundError(f"No lyrics text found on page: {song_url}")
            
            # Combine parts and clean up
            lyrics = '\n'.join(lyrics_parts)
            lyrics = '\n'.join(line.strip() for line in lyrics.split('\n') if line.strip())
            
            return lyrics
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching lyrics from {song_url}: {e}")
            raise LyricsNotFoundError(f"Failed to fetch lyrics: {e}")
        except Exception as e:
            logger.error(f"Error parsing lyrics from {song_url}: {e}")
            raise LyricsNotFoundError(f"Failed to parse lyrics: {e}")
    
    def get_lyrics(self, song_title: str, artist_name: str) -> Optional[str]:
        """
        Get lyrics for a song (with caching).
        
        Main entry point - searches Genius, fetches lyrics, caches result.
        
        Args:
            song_title: Song title
            artist_name: Artist name
            
        Returns:
            Lyrics text if found, None if not found
            
        Raises:
            RateLimitError: If rate limit is hit
        """
        # Check cache first
        cache_key = self._get_cache_key(song_title, artist_name)
        cached = self._read_cache(cache_key)
        
        if cached is not None:
            if cached.get("not_found"):
                logger.debug(f"Cache hit (not found): '{song_title}' by '{artist_name}'")
                return None
            
            logger.debug(f"Cache hit: '{song_title}' by '{artist_name}'")
            return cached.get("lyrics")
        
        try:
            # Search for song
            song_data = self.search_song(song_title, artist_name)
            if not song_data:
                logger.info(f"Song not found on Genius: '{song_title}' by '{artist_name}'")
                self._write_cache(cache_key, {"not_found": True})
                return None
            
            # Fetch lyrics from URL
            lyrics = self.fetch_lyrics(song_data["url"])
            
            # Cache the result
            self._write_cache(cache_key, {
                "lyrics": lyrics,
                "url": song_data["url"],
                "title": song_data["title"],
                "artist": song_data["artist"],
            })
            
            logger.info(f"Successfully fetched lyrics: '{song_title}' by '{artist_name}'")
            return lyrics
            
        except RateLimitError:
            raise
        except LyricsNotFoundError as e:
            logger.warning(f"Failed to get lyrics for '{song_title}' by '{artist_name}': {e}")
            self._write_cache(cache_key, {"not_found": True})
            return None
    
    @staticmethod
    def _extract_primary_artist(artist_string: str) -> str:
        """
        Extract primary artist from multi-artist format.
        Handles: "Artist feat. Other", "Artist x Other", "Artist vs Other", etc.
        
        Args:
            artist_string: Full artist string which may include featured artists
            
        Returns:
            Primary artist name
        """
        delimiters = [
            " featuring ",
            " feat. ",
            " ft. ",
            " x ",
            " vs ",
            " vs. ",
            " & ",
            " (feat",
            ", ",
            ", feat",
        ]
        
        artist = artist_string.strip()
        
        for delimiter in delimiters:
            if delimiter.lower() in artist.lower():
                # Split and take first part
                idx = artist.lower().find(delimiter.lower())
                artist = artist[:idx].strip()
                break
        
        return artist
