"""
External integration services for MusicBrainz, Genius, and other APIs.
"""
import logging
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Tuple
from functools import lru_cache
import time

import musicbrainzngs as mb
import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

# Configure MusicBrainz client
mb.set_useragent("Bairry", "0.1.0", "https://github.com/gowland/bairry")


class RateLimitError(Exception):
    """Raised when an API rate limit is hit."""
    pass


class APIError(Exception):
    """Raised when an API request fails."""
    pass


class ArtistNotFoundError(APIError):
    """Raised when an artist cannot be found."""
    pass


class RetrySession(requests.Session):
    """Session with automatic retry logic for rate limiting."""
    
    def __init__(
        self,
        retries: int = 3,
        backoff_factor: float = 1.0,
        status_forcelist: tuple = (429, 500, 502, 503, 504),
    ):
        super().__init__()
        self.retries = retries
        self.backoff_factor = backoff_factor
        
        retry_strategy = Retry(
            total=retries,
            backoff_factor=backoff_factor,
            status_forcelist=status_forcelist,
            allowed_methods=["GET", "POST"],
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.mount("http://", adapter)
        self.mount("https://", adapter)


class MusicBrainzIntegration:
    """
    Handles artist resolution and genre fetching from MusicBrainz.
    
    Features:
    - Fuzzy artist name matching
    - Multi-artist format parsing (feat., x, vs, etc.)
    - Genre fetching from MusicBrainz
    - Local caching to minimize API calls
    """
    
    # Delimiters for multi-artist formats
    MULTI_ARTIST_DELIMITERS = [
        " featuring ", " feat. ", " ft. ",
        " x ", " vs ", " vs. ",
        ", ", " and ", " & ",
        " (", ")",  # Parentheses (e.g., "Artist (feat. Other)")
    ]
    
    def __init__(self):
        """Initialize MusicBrainz integration."""
        self.session = RetrySession()
    
    def parse_artist_string(self, artist_string: str) -> str:
        """
        Parse multi-artist format and extract primary artist.
        
        Handles formats like:
        - "John Doe featuring Bill Smith"
        - "John Doe x Bill Smith"
        - "John Doe vs Bill Smith"
        - "John Doe, Bill Smith"
        - "John Doe (Bill Smith)"
        
        Args:
            artist_string: Raw artist string that may contain multiple artists
            
        Returns:
            Primary (leftmost) artist name
        """
        # Start with the full string
        result = artist_string.strip()
        
        # Split on delimiters and take the first part
        for delimiter in self.MULTI_ARTIST_DELIMITERS:
            if delimiter.lower() in result.lower():
                # Split case-insensitively
                idx = result.lower().find(delimiter.lower())
                result = result[:idx]
        
        # Clean up parentheses if they exist
        if "(" in result:
            result = result.split("(")[0]
        
        return result.strip()
    
    def resolve_artist(
        self,
        artist_name: str,
        confidence_threshold: float = 0.8,
    ) -> Optional[Dict]:
        """
        Resolve artist name to MusicBrainz artist and fetch genres.
        
        Args:
            artist_name: Artist name to resolve
            confidence_threshold: Minimum confidence (0-1) to accept match
            
        Returns:
            Dict with keys: musicbrainz_id, canonical_name, genres
            Returns None if no match found above threshold
            
        Raises:
            RateLimitError: If MusicBrainz rate limit is hit
            APIError: If MusicBrainz API fails
        """
        try:
            # Parse multi-artist format
            primary_artist = self.parse_artist_string(artist_name)
            
            logger.info(f"Resolving artist: {primary_artist}")
            
            # Search for artist on MusicBrainz
            results = mb.search_artists(primary_artist, limit=5)
            
            if not results.get("artist-list"):
                logger.warning(f"No MusicBrainz match for: {primary_artist}")
                return None
            
            # Find best match by name similarity
            best_match = None
            best_score = 0.0
            
            for artist in results["artist-list"]:
                # Simple heuristic: exact match scores highest, partial match lower
                canonical_name = artist.get("name", "")
                score = self._calculate_match_score(primary_artist, canonical_name)
                
                logger.debug(f"  Candidate: {canonical_name} (score: {score:.2f})")
                
                if score > best_score:
                    best_score = score
                    best_match = artist
            
            if best_score < confidence_threshold:
                logger.warning(
                    f"Best match for {primary_artist} scored {best_score:.2f}, "
                    f"below threshold {confidence_threshold}"
                )
                return None
            
            # Fetch full artist details including genres
            musicbrainz_id = best_match["id"]
            logger.info(f"Found MusicBrainz ID: {musicbrainz_id}")
            
            artist_detail = mb.get_artist_by_id(
                musicbrainz_id,
                includes=["tags"]
            )
            
            artist_data = artist_detail["artist"]
            
            # Extract genres from tags (MusicBrainz uses tags instead of genres)
            genres = self._extract_genres_from_tags(artist_data)
            
            return {
                "musicbrainz_id": musicbrainz_id,
                "canonical_name": artist_data.get("name", canonical_name),
                "genres": genres,
            }
        
        except mb.ResponseError as e:
            if "429" in str(e) or "rate limit" in str(e).lower():
                logger.error(f"MusicBrainz rate limit hit: {e}")
                raise RateLimitError(f"MusicBrainz rate limit: {e}")
            else:
                logger.error(f"MusicBrainz API error: {e}")
                raise APIError(f"MusicBrainz API error: {e}")
        except Exception as e:
            logger.error(f"Unexpected error resolving artist: {e}")
            raise APIError(f"Unexpected error: {e}")
    
    def _calculate_match_score(self, query: str, candidate: str) -> float:
        """
        Calculate similarity score between query and candidate artist names.
        
        Simple heuristic:
        - Exact match (case-insensitive): 1.0
        - Starts with query: 0.9
        - Query is substring: 0.7
        - Levenshtein distance < 20%: 0.5
        - Otherwise: 0.0
        
        Args:
            query: Original artist name query
            candidate: MusicBrainz candidate name
            
        Returns:
            Similarity score (0.0 to 1.0)
        """
        query_lower = query.lower()
        candidate_lower = candidate.lower()
        
        # Exact match
        if query_lower == candidate_lower:
            return 1.0
        
        # Starts with
        if candidate_lower.startswith(query_lower):
            return 0.9
        
        # Is substring
        if query_lower in candidate_lower:
            return 0.7
        
        # Levenshtein distance (simple implementation)
        distance = self._levenshtein_distance(query_lower, candidate_lower)
        max_len = max(len(query_lower), len(candidate_lower))
        
        if max_len == 0:
            return 1.0
        
        similarity = 1.0 - (distance / max_len)
        
        if similarity >= 0.8:  # 80% match
            return similarity * 0.5  # 0.4 to 0.5 score
        
        return 0.0
    
    @staticmethod
    def _levenshtein_distance(s1: str, s2: str) -> int:
        """Compute Levenshtein distance between two strings."""
        if len(s1) < len(s2):
            s1, s2 = s2, s1
        
        if len(s2) == 0:
            return len(s1)
        
        previous_row = range(len(s2) + 1)
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                # j+1 instead of j since previous_row and current_row are one character longer
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row
        
        return previous_row[-1]
    
    @staticmethod
    def _extract_genres_from_tags(artist_data: Dict) -> List[str]:
        """
        Extract genre tags from MusicBrainz artist data.
        
        MusicBrainz returns tags instead of formal genres.
        We filter for tags that look like genres (lowercase, no numbers).
        
        Args:
            artist_data: Artist dict from MusicBrainz API
            
        Returns:
            List of genre strings
        """
        genres = []
        
        # Check for tags-list
        tags = artist_data.get("tag-list", [])
        
        for tag_item in tags:
            # Each tag is a dict with "name" and optionally "count"
            tag_name = tag_item.get("name", "").lower().strip()
            
            # Filter: skip empty, skip obvious non-genres (short jargon)
            if tag_name and len(tag_name) > 2:
                genres.append(tag_name)
        
        # If no tags, try genre field (some MusicBrainz versions)
        if not genres:
            genre_field = artist_data.get("genre", "")
            if genre_field:
                genres = [g.strip().lower() for g in genre_field.split(";")]
        
        # Remove duplicates and sort
        genres = sorted(list(set(genres)))
        
        return genres


# Module-level instance for convenience
_mb_instance: Optional[MusicBrainzIntegration] = None


def get_musicbrainz() -> MusicBrainzIntegration:
    """Get or create singleton MusicBrainz integration instance."""
    global _mb_instance
    if _mb_instance is None:
        _mb_instance = MusicBrainzIntegration()
    return _mb_instance
