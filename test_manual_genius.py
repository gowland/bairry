"""
Manual testing script for Genius API integration.
Tests real API calls and lyrics fetching.

Note: Requires GENIUS_API_TOKEN environment variable to be set.
Get your token at https://genius.com/api-clients

Usage:
    python test_manual_genius.py
"""
import os
import sys
from src.genius_integration import GeniusIntegration, LyricsNotFoundError, RateLimitError


def test_genius_integration():
    """Test Genius integration with real songs."""
    
    # Check if API token is set
    api_token = os.getenv("GENIUS_API_TOKEN")
    if not api_token:
        print("❌ GENIUS_API_TOKEN environment variable not set")
        print("   Get your token at https://genius.com/api-clients")
        return False
    
    print(f"✓ Using Genius API token: {api_token[:10]}...")
    print()
    
    try:
        genius = GeniusIntegration(api_token=api_token)
    except ValueError as e:
        print(f"❌ Failed to initialize: {e}")
        return False
    
    # Test songs with known good data
    test_songs = [
        ("Hello", "Adele"),
        ("Blinding Lights", "The Weeknd"),
        ("Shape of You", "Ed Sheeran"),
        ("Bad Guy", "Billie Eilish"),
        ("Rolling in the Deep", "Adele"),
    ]
    
    results = []
    
    for title, artist in test_songs:
        print(f"Testing: '{title}' by {artist}")
        
        try:
            # Test search
            song_data = genius.search_song(title, artist)
            
            if song_data is None:
                print(f"  ❌ Not found on Genius")
                results.append(False)
                continue
            
            print(f"  ✓ Found: {song_data['title']} by {song_data['artist']}")
            
            # Test lyrics fetching
            lyrics = genius.fetch_lyrics(song_data["url"])
            
            if lyrics is None or len(lyrics.strip()) == 0:
                print(f"  ❌ Failed to fetch lyrics")
                results.append(False)
                continue
            
            lyrics_preview = lyrics[:100].replace('\n', ' ')
            print(f"  ✓ Fetched {len(lyrics)} chars: {lyrics_preview}...")
            
            # Test caching (second call should use cache)
            lyrics_cached = genius.get_lyrics(title, artist)
            if lyrics_cached == lyrics:
                print(f"  ✓ Cache works correctly")
            else:
                print(f"  ⚠ Cache returned different lyrics")
            
            results.append(True)
            print()
            
        except RateLimitError as e:
            print(f"  ❌ Rate limit hit: {e}")
            results.append(False)
            break  # Stop testing if rate limited
        except LyricsNotFoundError as e:
            print(f"  ❌ Error: {e}")
            results.append(False)
        except Exception as e:
            print(f"  ❌ Unexpected error: {e}")
            results.append(False)
        
        print()
    
    # Summary
    passed = sum(results)
    total = len(results)
    
    print("=" * 60)
    print(f"SUMMARY: {passed}/{total} tests passed")
    
    if passed == total:
        print("✓ All tests passed!")
        return True
    else:
        print(f"❌ {total - passed} test(s) failed")
        return False


if __name__ == "__main__":
    success = test_genius_integration()
    sys.exit(0 if success else 1)
