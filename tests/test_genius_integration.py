"""
Unit tests for Genius API integration.
Tests song search, lyrics fetching, caching, and error handling.
"""
import pytest
import json
import os
import tempfile
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

from src.genius_integration import (
    GeniusIntegration,
    RateLimitError,
    LyricsNotFoundError,
)


class TestGeniusIntegration:
    """Test Genius API integration."""
    
    @pytest.fixture
    def temp_cache_dir(self):
        """Create temporary cache directory for tests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            original_cache_dir = GeniusIntegration.CACHE_DIR
            GeniusIntegration.CACHE_DIR = tmpdir
            yield tmpdir
            GeniusIntegration.CACHE_DIR = original_cache_dir
    
    @pytest.fixture
    def genius(self, temp_cache_dir):
        """Create GeniusIntegration instance with mock token."""
        return GeniusIntegration(api_token="test_token_12345")
    
    def test_init_with_provided_token(self):
        """Test initialization with provided API token."""
        genius = GeniusIntegration(api_token="test_token")
        assert genius.api_token == "test_token"
    
    def test_init_with_env_token(self, monkeypatch):
        """Test initialization with environment variable token."""
        monkeypatch.setenv("GENIUS_API_TOKEN", "env_token_12345")
        genius = GeniusIntegration()
        assert genius.api_token == "env_token_12345"
    
    def test_init_no_token_raises_error(self, monkeypatch):
        """Test that ValueError is raised when no token is available."""
        monkeypatch.delenv("GENIUS_API_TOKEN", raising=False)
        
        with pytest.raises(ValueError, match="Genius API token not provided"):
            GeniusIntegration()
    
    def test_extract_primary_artist_single_name(self):
        """Test extracting primary artist from single name."""
        artist = GeniusIntegration._extract_primary_artist("Adele")
        assert artist == "Adele"
    
    def test_extract_primary_artist_feat_format(self):
        """Test extracting primary artist from 'feat.' format."""
        artist = GeniusIntegration._extract_primary_artist("Adele feat. Drake")
        assert artist == "Adele"
    
    def test_extract_primary_artist_featuring_format(self):
        """Test extracting primary artist from 'featuring' format."""
        artist = GeniusIntegration._extract_primary_artist("Adele featuring Drake")
        assert artist == "Adele"
    
    def test_extract_primary_artist_ft_format(self):
        """Test extracting primary artist from 'ft.' format."""
        artist = GeniusIntegration._extract_primary_artist("Adele ft. Drake")
        assert artist == "Adele"
    
    def test_extract_primary_artist_x_format(self):
        """Test extracting primary artist from 'x' format."""
        artist = GeniusIntegration._extract_primary_artist("Adele x Drake")
        assert artist == "Adele"
    
    def test_extract_primary_artist_vs_format(self):
        """Test extracting primary artist from 'vs' format."""
        artist = GeniusIntegration._extract_primary_artist("Adele vs Drake")
        assert artist == "Adele"
    
    def test_extract_primary_artist_ampersand_format(self):
        """Test extracting primary artist from '&' format."""
        artist = GeniusIntegration._extract_primary_artist("Adele & Drake")
        assert artist == "Adele"
    
    def test_extract_primary_artist_paren_format(self):
        """Test extracting primary artist from parentheses format."""
        artist = GeniusIntegration._extract_primary_artist("Adele (feat Drake)")
        assert artist == "Adele"
    
    def test_extract_primary_artist_comma_format(self):
        """Test extracting primary artist from comma format."""
        artist = GeniusIntegration._extract_primary_artist("Adele, Drake")
        assert artist == "Adele"
    
    def test_extract_primary_artist_case_insensitive(self):
        """Test that extraction is case-insensitive."""
        artist = GeniusIntegration._extract_primary_artist("Adele FEAT. Drake")
        assert artist == "Adele"
    
    def test_get_cache_key_consistent(self):
        """Test that cache key is consistent for same input."""
        genius = GeniusIntegration(api_token="test")
        key1 = genius._get_cache_key("Hello", "Adele")
        key2 = genius._get_cache_key("Hello", "Adele")
        assert key1 == key2
    
    def test_get_cache_key_different_inputs(self):
        """Test that cache key differs for different inputs."""
        genius = GeniusIntegration(api_token="test")
        key1 = genius._get_cache_key("Hello", "Adele")
        key2 = genius._get_cache_key("Goodbye", "Adele")
        assert key1 != key2
    
    def test_cache_write_and_read(self, genius):
        """Test writing and reading from cache."""
        cache_key = "test_key_123"
        data = {"lyrics": "Test lyrics\nLine 2", "title": "Test Song"}
        
        genius._write_cache(cache_key, data)
        retrieved = genius._read_cache(cache_key)
        
        assert retrieved == data
        assert retrieved["lyrics"] == "Test lyrics\nLine 2"
    
    def test_cache_read_nonexistent_returns_none(self, genius):
        """Test that reading nonexistent cache returns None."""
        result = genius._read_cache("nonexistent_key_xyz")
        assert result is None
    
    def test_cache_corrupted_file_returns_none(self, genius):
        """Test that corrupted cache file returns None gracefully."""
        cache_key = "corrupted_key"
        cache_file = os.path.join(genius.CACHE_DIR, f"{cache_key}.json")
        
        # Write corrupted JSON
        with open(cache_file, 'w') as f:
            f.write("{invalid json content")
        
        result = genius._read_cache(cache_key)
        assert result is None
    
    @patch('src.genius_integration.requests.Session.get')
    def test_search_song_success(self, mock_get, genius):
        """Test successful song search."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "response": {
                "hits": [
                    {
                        "result": {
                            "url": "https://genius.com/hello-song",
                            "title": "Hello",
                            "primary_artist": {"name": "Adele"},
                        }
                    }
                ]
            }
        }
        mock_get.return_value = mock_response
        
        result = genius.search_song("Hello", "Adele")
        
        assert result is not None
        assert result["url"] == "https://genius.com/hello-song"
        assert result["title"] == "Hello"
        assert result["artist"] == "Adele"
    
    @patch('src.genius_integration.requests.Session.get')
    def test_search_song_not_found(self, mock_get, genius):
        """Test song search with no results."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"response": {"hits": []}}
        mock_get.return_value = mock_response
        
        result = genius.search_song("Nonexistent Song", "Fake Artist")
        
        assert result is None
    
    @patch('src.genius_integration.requests.Session.get')
    def test_search_song_rate_limit(self, mock_get, genius):
        """Test song search with rate limit error."""
        mock_response = Mock()
        mock_response.status_code = 429
        mock_get.return_value = mock_response
        
        with pytest.raises(RateLimitError):
            genius.search_song("Hello", "Adele")
    
    @patch('src.genius_integration.requests.Session.get')
    def test_search_song_api_error(self, mock_get, genius):
        """Test song search with API error."""
        mock_get.side_effect = Exception("Connection error")
        
        with pytest.raises(LyricsNotFoundError):
            genius.search_song("Hello", "Adele")
    
    @patch('src.genius_integration.requests.get')
    def test_fetch_lyrics_success(self, mock_get, genius):
        """Test successful lyrics fetching."""
        html = """
        <html>
            <div data-lyrics-container="true">
                <div>Verse 1<br/>Line 2</div>
            </div>
            <div data-lyrics-container="true">
                <div>Chorus<br/>Chorus line 2</div>
            </div>
        </html>
        """
        mock_response = Mock()
        mock_response.text = html
        mock_get.return_value = mock_response
        
        lyrics = genius.fetch_lyrics("https://genius.com/hello")
        
        assert lyrics is not None
        assert "Verse 1" in lyrics
        assert "Chorus" in lyrics
    
    @patch('src.genius_integration.requests.get')
    def test_fetch_lyrics_no_container(self, mock_get, genius):
        """Test lyrics fetching when no lyrics container found."""
        html = "<html><body>No lyrics here</body></html>"
        mock_response = Mock()
        mock_response.text = html
        mock_get.return_value = mock_response
        
        with pytest.raises(LyricsNotFoundError):
            genius.fetch_lyrics("https://genius.com/hello")
    
    @patch('src.genius_integration.requests.get')
    def test_fetch_lyrics_timeout(self, mock_get, genius):
        """Test lyrics fetching with timeout."""
        import requests
        mock_get.side_effect = requests.exceptions.Timeout()
        
        with pytest.raises(LyricsNotFoundError):
            genius.fetch_lyrics("https://genius.com/hello")
    
    @patch.object(GeniusIntegration, 'search_song')
    @patch.object(GeniusIntegration, 'fetch_lyrics')
    def test_get_lyrics_success(self, mock_fetch, mock_search, genius):
        """Test successful get_lyrics (full flow)."""
        mock_search.return_value = {
            "url": "https://genius.com/hello",
            "title": "Hello",
            "artist": "Adele"
        }
        mock_fetch.return_value = "Test lyrics\nLine 2"
        
        lyrics = genius.get_lyrics("Hello", "Adele")
        
        assert lyrics == "Test lyrics\nLine 2"
        mock_search.assert_called_once_with("Hello", "Adele")
        mock_fetch.assert_called_once_with("https://genius.com/hello")
    
    @patch.object(GeniusIntegration, 'search_song')
    def test_get_lyrics_song_not_found(self, mock_search, genius):
        """Test get_lyrics when song not found."""
        mock_search.return_value = None
        
        lyrics = genius.get_lyrics("Fake Song", "Fake Artist")
        
        assert lyrics is None
    
    @patch.object(GeniusIntegration, 'search_song')
    def test_get_lyrics_caches_not_found(self, mock_search, genius, temp_cache_dir):
        """Test that get_lyrics caches 'not found' result."""
        mock_search.return_value = None
        
        # First call
        result1 = genius.get_lyrics("Fake Song", "Fake Artist")
        assert result1 is None
        assert mock_search.call_count == 1
        
        # Second call should use cache
        result2 = genius.get_lyrics("Fake Song", "Fake Artist")
        assert result2 is None
        assert mock_search.call_count == 1  # Not called again
    
    @patch.object(GeniusIntegration, 'search_song')
    @patch.object(GeniusIntegration, 'fetch_lyrics')
    def test_get_lyrics_caches_success(self, mock_fetch, mock_search, genius, temp_cache_dir):
        """Test that get_lyrics caches successful results."""
        mock_search.return_value = {
            "url": "https://genius.com/hello",
            "title": "Hello",
            "artist": "Adele"
        }
        mock_fetch.return_value = "Cached lyrics"
        
        # First call
        result1 = genius.get_lyrics("Hello", "Adele")
        assert result1 == "Cached lyrics"
        assert mock_fetch.call_count == 1
        
        # Second call should use cache (reset mocks to verify)
        mock_search.reset_mock()
        mock_fetch.reset_mock()
        
        result2 = genius.get_lyrics("Hello", "Adele")
        assert result2 == "Cached lyrics"
        assert mock_search.call_count == 0  # Not called
        assert mock_fetch.call_count == 0   # Not called
    
    @patch.object(GeniusIntegration, 'search_song')
    def test_get_lyrics_rate_limit_propagates(self, mock_search, genius):
        """Test that RateLimitError propagates from search."""
        mock_search.side_effect = RateLimitError("Rate limited")
        
        with pytest.raises(RateLimitError):
            genius.get_lyrics("Hello", "Adele")
    
    @patch.object(GeniusIntegration, 'search_song')
    @patch.object(GeniusIntegration, 'fetch_lyrics')
    def test_get_lyrics_fetch_error_caches_as_not_found(self, mock_fetch, mock_search, genius):
        """Test that fetch errors are cached as 'not found'."""
        mock_search.return_value = {"url": "https://genius.com/hello", "title": "Hello", "artist": "Adele"}
        mock_fetch.side_effect = LyricsNotFoundError("Failed to fetch")
        
        # First call
        result1 = genius.get_lyrics("Hello", "Adele")
        assert result1 is None
        
        # Second call should use cache
        mock_search.reset_mock()
        mock_fetch.reset_mock()
        
        result2 = genius.get_lyrics("Hello", "Adele")
        assert result2 is None
        assert mock_search.call_count == 0
    
    def test_cache_dir_created_on_init(self, temp_cache_dir):
        """Test that cache directory is created during initialization."""
        genius = GeniusIntegration(api_token="test")
        assert os.path.exists(genius.CACHE_DIR)
