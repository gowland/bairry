#!/usr/bin/env python3
"""
Manual testing script for MusicBrainz integration.
Tests artist resolution with various artist names.
"""
import sys
from src.musicbrainz_integration import get_musicbrainz

def test_artist(artist_name: str) -> None:
    """Test resolving a single artist."""
    print(f"\n{'='*70}")
    print(f"Testing: {artist_name}")
    print('='*70)
    
    mb = get_musicbrainz()
    
    try:
        result = mb.resolve_artist(artist_name)
        
        if result:
            print(f"✓ Found!")
            print(f"  Primary artist: {artist_name}")
            print(f"  Canonical name: {result['canonical_name']}")
            print(f"  MusicBrainz ID: {result['musicbrainz_id']}")
            print(f"  Genres ({len(result['genres'])}): {', '.join(result['genres'][:10])}")
            if len(result['genres']) > 10:
                print(f"             ... and {len(result['genres']) - 10} more")
        else:
            print(f"✗ Not found (no match above confidence threshold)")
    
    except Exception as e:
        print(f"✗ Error: {type(e).__name__}: {e}")


def main():
    """Run manual tests."""
    artists = [
        "Papa Roach",
        "Lil Nas X",
        "Scorpions",
        "Jay-Z & Linkin Park",
        "Band Marino",
    ]
    
    print("\n" + "="*70)
    print("MUSICBRAINZ INTEGRATION MANUAL TESTS")
    print("="*70)
    
    for artist in artists:
        test_artist(artist)
    
    print("\n" + "="*70)
    print("Tests complete!")
    print("="*70 + "\n")


if __name__ == "__main__":
    main()
