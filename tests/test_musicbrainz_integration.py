"""
Tests for MusicBrainz integration.
"""
import pytest
from src.musicbrainz_integration import MusicBrainzIntegration


class TestArtistParsing:
    """Tests for multi-artist format parsing."""
    
    def test_parse_single_artist(self):
        """Test parsing a single artist name."""
        mb = MusicBrainzIntegration()
        result = mb.parse_artist_string("John Doe")
        assert result == "John Doe"
    
    def test_parse_featuring(self):
        """Test parsing 'featuring' format."""
        mb = MusicBrainzIntegration()
        result = mb.parse_artist_string("John Doe featuring Bill Smith")
        assert result == "John Doe"
    
    def test_parse_feat_abbreviated(self):
        """Test parsing 'feat.' format."""
        mb = MusicBrainzIntegration()
        result = mb.parse_artist_string("John Doe feat. Bill Smith")
        assert result == "John Doe"
    
    def test_parse_ft_abbreviated(self):
        """Test parsing 'ft.' format."""
        mb = MusicBrainzIntegration()
        result = mb.parse_artist_string("John Doe ft. Bill Smith")
        assert result == "John Doe"
    
    def test_parse_x_format(self):
        """Test parsing 'x' format (collaboration)."""
        mb = MusicBrainzIntegration()
        result = mb.parse_artist_string("John Doe x Bill Smith")
        assert result == "John Doe"
    
    def test_parse_vs_format(self):
        """Test parsing 'vs' format (battle)."""
        mb = MusicBrainzIntegration()
        result = mb.parse_artist_string("John Doe vs Bill Smith")
        assert result == "John Doe"
    
    def test_parse_vs_abbreviated_format(self):
        """Test parsing 'vs.' format."""
        mb = MusicBrainzIntegration()
        result = mb.parse_artist_string("John Doe vs. Bill Smith")
        assert result == "John Doe"
    
    def test_parse_comma_format(self):
        """Test parsing comma-separated format."""
        mb = MusicBrainzIntegration()
        result = mb.parse_artist_string("John Doe, Bill Smith")
        assert result == "John Doe"
    
    def test_parse_and_format(self):
        """Test parsing 'and' format."""
        mb = MusicBrainzIntegration()
        result = mb.parse_artist_string("John Doe and Bill Smith")
        assert result == "John Doe"
    
    def test_parse_ampersand_format(self):
        """Test parsing '&' format."""
        mb = MusicBrainzIntegration()
        result = mb.parse_artist_string("John Doe & Bill Smith")
        assert result == "John Doe"
    
    def test_parse_parentheses_format(self):
        """Test parsing parentheses format."""
        mb = MusicBrainzIntegration()
        result = mb.parse_artist_string("John Doe (Bill Smith)")
        assert result == "John Doe"
    
    def test_parse_case_insensitive(self):
        """Test that parsing is case-insensitive."""
        mb = MusicBrainzIntegration()
        result = mb.parse_artist_string("John Doe FEATURING Bill Smith")
        assert result == "John Doe"
    
    def test_parse_with_whitespace(self):
        """Test parsing with extra whitespace."""
        mb = MusicBrainzIntegration()
        result = mb.parse_artist_string("  John Doe feat. Bill Smith  ")
        assert result == "John Doe"


class TestMatchScore:
    """Tests for artist name matching scoring."""
    
    def test_exact_match(self):
        """Test exact match scores 1.0."""
        mb = MusicBrainzIntegration()
        score = mb._calculate_match_score("John Doe", "John Doe")
        assert score == 1.0
    
    def test_exact_match_case_insensitive(self):
        """Test exact match is case-insensitive."""
        mb = MusicBrainzIntegration()
        score = mb._calculate_match_score("john doe", "John Doe")
        assert score == 1.0
    
    def test_starts_with_match(self):
        """Test 'starts with' match scores 0.9."""
        mb = MusicBrainzIntegration()
        score = mb._calculate_match_score("John", "John Doe")
        assert score == 0.9
    
    def test_substring_match(self):
        """Test substring match scores 0.7."""
        mb = MusicBrainzIntegration()
        score = mb._calculate_match_score("Doe", "John Doe")
        assert score == 0.7
    
    def test_no_match(self):
        """Test completely different names score 0.0."""
        mb = MusicBrainzIntegration()
        score = mb._calculate_match_score("Alice", "Bob")
        assert score == 0.0
    
    def test_high_similarity_low_score(self):
        """Test similar but not exact match gets reasonable score."""
        mb = MusicBrainzIntegration()
        # "Jon Doe" vs "John Doe" should be somewhat close
        score = mb._calculate_match_score("Jon Doe", "John Doe")
        assert 0.3 < score < 0.7  # Should be moderate


class TestLevenshteinDistance:
    """Tests for Levenshtein distance calculation."""
    
    def test_identical_strings(self):
        """Test identical strings have distance 0."""
        mb = MusicBrainzIntegration()
        distance = mb._levenshtein_distance("abc", "abc")
        assert distance == 0
    
    def test_one_insertion(self):
        """Test single character insertion."""
        mb = MusicBrainzIntegration()
        distance = mb._levenshtein_distance("abc", "abcd")
        assert distance == 1
    
    def test_one_deletion(self):
        """Test single character deletion."""
        mb = MusicBrainzIntegration()
        distance = mb._levenshtein_distance("abcd", "abc")
        assert distance == 1
    
    def test_one_substitution(self):
        """Test single character substitution."""
        mb = MusicBrainzIntegration()
        distance = mb._levenshtein_distance("abc", "abd")
        assert distance == 1
    
    def test_completely_different(self):
        """Test completely different strings."""
        mb = MusicBrainzIntegration()
        distance = mb._levenshtein_distance("abc", "xyz")
        assert distance == 3
    
    def test_empty_string(self):
        """Test with empty string."""
        mb = MusicBrainzIntegration()
        distance = mb._levenshtein_distance("abc", "")
        assert distance == 3


class TestGenreExtraction:
    """Tests for genre extraction from MusicBrainz tags."""
    
    def test_extract_genres_from_tags(self):
        """Test extracting genres from tag-list."""
        artist_data = {
            "tag-list": [
                {"name": "rock", "count": 100},
                {"name": "pop", "count": 80},
                {"name": "alternative", "count": 60},
            ]
        }
        genres = MusicBrainzIntegration._extract_genres_from_tags(artist_data)
        assert "rock" in genres
        assert "pop" in genres
        assert "alternative" in genres
        assert len(genres) == 3
    
    def test_extract_genres_case_normalized(self):
        """Test that genres are normalized to lowercase."""
        artist_data = {
            "tag-list": [
                {"name": "Rock", "count": 100},
                {"name": "POP", "count": 80},
            ]
        }
        genres = MusicBrainzIntegration._extract_genres_from_tags(artist_data)
        assert "rock" in genres
        assert "pop" in genres
        assert "Rock" not in genres
        assert "POP" not in genres
    
    def test_extract_genres_skip_short_tags(self):
        """Test that very short tags are skipped."""
        artist_data = {
            "tag-list": [
                {"name": "rock", "count": 100},
                {"name": "a", "count": 5},  # Too short
                {"name": "pop", "count": 80},
            ]
        }
        genres = MusicBrainzIntegration._extract_genres_from_tags(artist_data)
        assert "rock" in genres
        assert "pop" in genres
        assert "a" not in genres
    
    def test_extract_genres_remove_duplicates(self):
        """Test that duplicates are removed."""
        artist_data = {
            "tag-list": [
                {"name": "rock", "count": 100},
                {"name": "rock", "count": 50},  # Duplicate
                {"name": "pop", "count": 80},
            ]
        }
        genres = MusicBrainzIntegration._extract_genres_from_tags(artist_data)
        assert genres.count("rock") == 1
        assert len(genres) == 2
    
    def test_extract_genres_empty_tags(self):
        """Test with empty tag list."""
        artist_data = {"tag-list": []}
        genres = MusicBrainzIntegration._extract_genres_from_tags(artist_data)
        assert genres == []
    
    def test_extract_genres_no_tags(self):
        """Test with no tag-list field."""
        artist_data = {}
        genres = MusicBrainzIntegration._extract_genres_from_tags(artist_data)
        assert genres == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
