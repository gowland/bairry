# Bairry - Song Matching Web Service

A web service that matches songs to users based on genre and lyrical similarity.

## System Overview

### Core Concepts

1. **Songs**: Identified by title + artist (may contain typos)
2. **Artists**: Have genres (fetched from MusicBrainz)
3. **Users**: Have accumulated genres and lyrics from their song library
4. **Scoring**: For each new song, compute similarity scores for all users based on:
   - Genre match (song's artist genres vs. user's total genres)
   - Lyrical similarity (song's lyrics vs. user's total lyrics - semantic similarity)

---

## Architecture Components

### 1. Data Layer

#### Entities
- **User**
  - `id`: UUID
  - `created_at`: Timestamp
  - `accumulated_genres`: weighted map of genre → frequency (int)

- **Song**
  - `id`: UUID
  - `title`: string
  - `artist`: string (original, may contain typos)
  - `matched_artist_id`: MusicBrainz ID (nullable until resolved)
  - `embedding`: vector[1536] (from song lyrics; Sentence Transformers default dimension)

- **Artist**
  - `musicbrainz_id`: string (unique)
  - `name`: string (canonical)
  - `genres`: Set<string> (from MusicBrainz)

- **UserSongLibrary** (Junction/Pivot table)
  - `user_id`: UUID (FK)
  - `song_id`: UUID (FK)
  - `added_at`: Timestamp

- **UserCluster** (Per-user semantic clusters)
  - `id`: UUID
  - `user_id`: UUID (FK)
  - `cluster_index`: int (0, 1, 2, ... per user)
  - `centroid_embedding`: vector[1536] (aggregated/averaged from member songs)
  - `created_at`: Timestamp
  - `updated_at`: Timestamp

- **SongClusterMembership** (Which cluster each song belongs to)
  - `song_id`: UUID (FK)
  - `cluster_id`: UUID (FK)

- **SongSimilarityScore** (Computed scores for a new song against a user)
  - `song_id`: UUID (FK)
  - `user_id`: UUID (FK)
  - `genre_score`: float (0-1)
  - `lyric_score`: float (0-1) [from best-matching cluster]
  - `matched_cluster_id`: UUID (FK to UserCluster, which cluster scored highest)
  - `combined_score`: float (0.6 * genre + 0.4 * lyric)
  - `computed_at`: Timestamp

#### Database Schema
- PostgreSQL (or similar RDBMS)
- Normalized design with appropriate indices on:
  - `users.id`, `songs.id`, `artists.musicbrainz_id`
  - Foreign keys with cascading deletes where appropriate
  - Indices on frequently queried fields (e.g., `song_id` + `user_id` for scores)

---

### 2. External Integrations

#### MusicBrainz Integration
- **Purpose**: Resolve artist names and retrieve canonical genres
- **Responsibility**:
  - Fuzzy matching on artist names (handle typos)
  - Fetch genres for matched artists
  - Cache results to minimize API calls
- **Pattern**: Client library or HTTP adapter
- **Rate Limiting**: Implement backoff and caching

#### Lyrics Service
- **Purpose**: Fetch song lyrics and translate to English if needed
- **Options**:
  - Genius API (requires API key, good coverage)
  - LyricFind API (premium)
  - Local database with user-submitted lyrics
  - Fallback to None if unavailable
- **Translation**: Use a translation API (Google Translate, DeepL) or local model
- **Caching**: Store fetched lyrics to avoid re-fetching

#### Semantic Similarity Engine
- **Purpose**: Compare lyrics semantically (not just keyword matching)
- **Options**:
  - Pre-computed embeddings (e.g., Sentence Transformers)
  - Vector database (Pinecone, Weaviate, Milvus) or PostgreSQL pgvector
  - LLM-based embeddings (OpenAI, local models)
- **Pattern**: Use a pre-trained model to generate embeddings, store in vector DB or DB columns
- **Computation**: Cosine similarity or similar distance metric

---

### 3. Processing Layer

#### Song Ingestion Pipeline
1. Accept song title + artist (strings)
2. Validate inputs (non-empty, reasonable length)
3. Normalize inputs (trim, lowercase for comparison)
4. Resolve artist via MusicBrainz (fuzzy matching)
5. Fetch lyrics
6. Translate lyrics to English
7. Generate lyric embeddings
8. Store embedding in database (discard lyrics)

#### Similarity Scoring Pipeline (Finalized with Clustering)
1. Accept new song (title + artist; will be resolved and embedded)
2. Resolve song's artist via MusicBrainz fuzzy matching
3. Fetch song's lyrics and generate embedding
4. For each user:
   a. **Genre Score**: Weighted Jaccard similarity
      - Song's artist genres vs. user's accumulated genres (weighted by frequency)
      - Example: if user's library has 5 songs with "Jazz" and 2 with "Pop"
      - Song with genres ["Jazz", "Funk"] scores higher than one with ["Pop", "Rock"]
   b. **Lyric Score**: Compare against user's semantic clusters
      - Find user's closest cluster centroid using cosine similarity
      - Use that centroid's similarity as the lyric score
      - Store matched cluster ID for transparency
   c. **Combined Score**: Weighted average
      - `combined_score = 0.6 * genre_score + 0.4 * lyric_score`
5. Store scores in database
6. Return ranked list of users with all three scores

---

### 4. API Layer

#### REST Endpoints (Initial)

**Songs**
- `POST /api/songs` - Create/ingest new song
  - Request: `{ title: string, artist: string }`
  - Response: `{ song_id: UUID, status: "created"|"already_exists", genres: string[] }`
  
- `GET /api/songs/{id}` - Retrieve song details
  
- `GET /api/songs/{id}/scores` - Get similarity scores for a song

**Users**
- `POST /api/users` - Create new user
  - Response: `{ user_id: UUID }`

- `POST /api/users/{id}/library` - Add song to user's library
  - Request: `{ song_id: UUID }`
  - Side effect: Update user's accumulated genres/lyrics

- `GET /api/users/{id}/genres` - Get user's accumulated genres
- `GET /api/users/{id}/profile` - Get full user profile

**Scoring**
- `POST /api/score` - Score a new song against all users
  - Request: `{ title: string, artist: string }`
  - Response: `{ song_id: UUID, scores: [{ user_id: UUID, genre_score: float, lyric_score: float, matched_cluster_id: UUID, combined_score: float }] }`
  - Note: `combined_score = 0.6 * genre_score + 0.4 * lyric_score`; `matched_cluster_id` shows which semantic cluster the song matched

---

### 5. Service Architecture

#### Core Services (Logical Layers)

**SongService**
- Manages song CRUD, ingestion, resolution
- Orchestrates: artist resolution, lyrics fetching, embedding generation

**UserService**
- Manages user CRUD
- Manages user library and accumulated metadata
- Updates accumulated genres (weighted) on library changes
- Triggers clustering pipeline on library changes

**ClusteringService**
- Computes KMeans clusters on user's song embeddings
- Generates cluster centroids
- Updates cluster membership
- Hyperparameter: `num_clusters = max(1, min(5, len(user_songs) // 50))`

**SimilarityService**
- Computes weighted genre scores (based on user's genre frequency)
- Computes lyric scores (cosine similarity against closest cluster centroid)
- Combines scores (60% genre, 40% lyric)
- Caches intermediate results

**ExternalIntegrationService**
- Wrapper around MusicBrainz, Genius API, Translation API
- Handles rate limiting, exponential backoff, circuit breaker
- Caching layer to minimize API calls
- Decouples external dependencies from business logic

**EmbeddingService**
- Generates embeddings for lyrics using local Sentence Transformers
- Caches embeddings

---

### 6. Technology Stack (Recommendations)

**Backend Framework**
- Python: FastAPI (modern, async, type hints)
- Node.js: NestJS or Express with TypeScript
- Go: Echo or Gin (high performance)

**Database** (PostgreSQL + pgvector)
- **Primary DB**: PostgreSQL (RDBMS, strong consistency, native vector support)
  - Local deployment: Docker container or local install
  - Schema: 7 tables (Users, Songs, Artists, UserSongLibrary, UserClusters, SongClusterMembership, SimilarityScores)
  - pgvector extension: Vectors stored as native type, cosine similarity indexing
  - Vector indices: IVFFLAT or HNSW for fast similarity search
- **Caching**: Redis (optional, for API responses and rate limiting)

**Why PostgreSQL over SQLite?**
- ✅ Native vector type and similarity operators (pgvector extension)
- ✅ Efficient vector indexing (IVFFLAT, HNSW)
- ✅ ACID compliance with better concurrent write handling
- ✅ SQL-based weighted aggregations (genre frequencies)
- ✅ Easily scales from local to server deployment later
- ✅ Still lightweight for local-only use (Docker: `docker run -p 5432:5432 postgres:15`)

**ML/Embeddings**
- Sentence Transformers (local, pre-trained model, no API calls)
- Clustering: Scikit-learn KMeans

**External APIs**
- MusicBrainz (free, fuzzy artist matching)
- Genius.com (free with API key, lyrics fetching)
- Google Translate (free tier, translation to English)

**Async/Queuing** (for long-running tasks)
- Celery + Redis (Python) OR Bull (Node.js)
- Batch ingestion with exponential backoff

**Monitoring/Logging**
- Structured logging
- Error tracking

---

### 7. Implementation Details

#### Lyric Clustering Strategy
Instead of a single mega-embedding per user, we cluster the user's songs into semantic groups:
- **Compute clusters** on each user library update using K-means
- **Number of clusters**: `num_clusters = max(1, min(5, len(user_songs) // 50))`
  - E.g.: 50 songs → 1 cluster, 250 songs → 5 clusters, 2000 songs → 5 clusters (max)
- **Store cluster centroids** as embeddings
- **Score new song**: Compare against all cluster centroids, use **highest-scoring cluster** for lyric similarity
- **Benefits**: 
  - Captures user's diverse musical tastes (e.g., sad indie, energetic pop, jazz)
  - More nuanced scoring than single aggregate
  - Reduces noise; song matches best cluster match better than worst
  - Scales well even with 2000 songs/user

#### Artist Name Parsing
Before MusicBrainz fuzzy matching, normalize and parse artist strings:
- **Handle multiple artist formats**:
  - `John Doe featuring Bill Smith`
  - `John Doe feat. Bill Smith` or `John Doe ft. Bill Smith`
  - `John Doe x Bill Smith`
  - `John Doe vs Bill Smith` or `John Doe vs. Bill Smith`
  - `John Doe, Bill Smith`
  - `John Doe and Bill Smith` or `John Doe & Bill Smith`
  - `John Doe (Bill Smith)`
- **Primary artist**: Take leftmost artist as primary
- **Fallback**: If MusicBrainz fails on primary, try secondary artists
- **Rationale**: Most genres belong to the primary/first-listed artist

#### MusicBrainz Fuzzy Matching
- Use MusicBrainz library's built-in fuzzy search
- Accept best match above a confidence threshold (suggest: 80%)
- If no match, log warning and mark artist as unresolved (skip genres, score from lyrics only)
- Cache all results (never query MusicBrainz twice for same artist)

#### Rate Limiting & Caching Strategy
Given batch loading (20 users × 250 songs = 5000 API calls):
- **API Response Cache**: Redis with TTL (e.g., 30 days for artist/genre, 90 days for lyrics)
- **Batch Processing**: 
  - Process in batches of ~50 songs per second
  - Implement exponential backoff: 1s, 2s, 4s, 8s, 16s retry delays
  - Circuit breaker: if 3 consecutive failures, pause and notify admin
- **Local Fallback**: 
  - If lyrics unavailable, score can still be computed from genres
  - Store `lyrics_available` flag for transparency
- **Admin Queue**: Ingest jobs queued and run asynchronously; admin UI shows progress

#### Weighted Genre Scoring
Example calculation:
```
User's library (accumulated genres with frequency):
  - Jazz: 5 songs
  - Pop: 2 songs
  - Funk: 3 songs

New song's artist genres: [Jazz, Soul]

Weighted genre score = Jaccard similarity
  Intersection: {Jazz, Soul} ∩ {Jazz, Pop, Funk} = {Jazz}
  Union: {Jazz, Soul} ∪ {Jazz, Pop, Funk} = {Jazz, Soul, Pop, Funk}
  Score = 1 / 4 = 0.25

OR with frequency weighting:
  Intersection weight: 5 (Jazz)
  Union weight: 5 + 2 + 3 + (new Soul = 0) = 10
  Score = 5 / 10 = 0.5
```
**Recommendation**: Use frequency-weighted Jaccard for better user preference modeling

#### Lyric Similarity Scoring
```
User's clusters and centroids:
  - Cluster 0 (sad indie): 40 songs, centroid embedding C0
  - Cluster 1 (energetic pop): 60 songs, centroid embedding C1
  - Cluster 2 (jazz): 50 songs, centroid embedding C2

New song embedding: E

Lyric scores:
  - cos_sim(E, C0) = 0.72
  - cos_sim(E, C1) = 0.55
  - cos_sim(E, C2) = 0.89 ← best match

Final lyric_score = 0.89
matched_cluster_id = Cluster 2
```

---

## Design Decisions (Finalized)

✅ **Database**: PostgreSQL 15+ with pgvector extension (local deployment)
✅ **Vector Indexing**: IVFFLAT or HNSW for efficient similarity search  
✅ **Tech Stack**: Language/framework agnostic (Python/FastAPI recommended)  
✅ **Score Response**: Separate `genre_score`, `lyric_score`, `matched_cluster_id`, + `combined_score`  
✅ **Score Weights**: 60% genre, 40% lyric  
✅ **Lyrics Provider**: Genius.com (free API)  
✅ **Embeddings**: Local Sentence Transformers (privacy, no API calls)  
✅ **Translation**: Google Translate free tier; translate at ingestion  
✅ **Genre Weighting**: Frequency-weighted Jaccard similarity  
✅ **Lyric Clustering**: K-means per user (1-5 clusters); score against best cluster  
✅ **Artist Parsing**: Fuzzy matching on primary artist; handle multiple formats (feat., x, vs, etc.)  
✅ **Scaling**: 100 users max, 2000 songs/user, admin-heavy workload  
✅ **Rate Limiting**: Exponential backoff, Redis caching, circuit breaker  
✅ **Offline/Privacy**: Local-only; no compliance concerns
When user adds a song to their library:
- Add song embedding to user's collection
- Re-cluster (incremental or full recomputation)
- Update cluster centroids in database
- This happens server-side; admin doesn't wait for clustering

---

## Technology Stack (Specific Recommendations)

Since tech is flexible, here are two solid options:

### Option A: Python + FastAPI (Recommended for ML workloads)
- **Framework**: FastAPI (async, type hints, auto-docs)
- **ORM**: SQLAlchemy with Alembic migrations
- **Database**: PostgreSQL 15+ with pgvector extension
- **Vector queries**: psycopg2-binary or SQLAlchemy with pgvector integration
- **Embeddings**: Sentence Transformers (local)
- **Clustering**: Scikit-learn (KMeans)
- **Task Queue**: Celery + Redis (for async ingestion)
- **Translation**: Google Translate library (free, local)
- **API Clients**: Musicbrainzngs, Genius (PyPI)
- **Caching**: Redis
- **Pros**: Excellent ML ecosystem, fast development, type hints, pgvector integration seamless
- **Cons**: Python deployment

### Option B: Node.js + TypeScript + NestJS
- **Framework**: NestJS (strong typing, modular)
- **ORM**: TypeORM or Prisma
- **Database**: PostgreSQL 15+ with pgvector extension
- **Vector queries**: typeorm-vector or raw queries
- **Embeddings**: Local model via child process (tf.js or Python subprocess)
- **Clustering**: ml-kmeans or call scikit-learn via Python subprocess
- **Task Queue**: Bull (Redis-backed)
- **Translation**: google-translate-api (free, local)
- **API Clients**: musicbrainz-api, genius-api
- **Caching**: Redis or in-memory
- **Pros**: Single language ecosystem, strong typing, modern async
- **Cons**: ML libraries less mature, vector/clustering requires Python subprocess

**Recommendation**: Go with **Option A (Python + FastAPI)** for easier ML integration, especially clustering and vector operations.

---

## PostgreSQL + pgvector Setup

### Local Installation (Docker)

```bash
docker run --name bairry-postgres \
  -e POSTGRES_USER=bairry \
  -e POSTGRES_PASSWORD=bairry \
  -e POSTGRES_DB=bairry \
  -p 5432:5432 \
  -d pgvector/pgvector:pg15
```

To verify the container is running:
```bash
docker ps | grep bairry-postgres
```

To stop/start the container:
```bash
docker stop bairry-postgres
docker start bairry-postgres
```

### Schema Setup

```sql
-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Create tables (simplified schema)
CREATE TABLE users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE artists (
  musicbrainz_id VARCHAR(255) PRIMARY KEY,
  name VARCHAR(255) NOT NULL,
  genres TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[]
);

CREATE TABLE songs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  title VARCHAR(500) NOT NULL,
  artist VARCHAR(500) NOT NULL,
  matched_artist_id VARCHAR(255),
  embedding vector(1536) NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (matched_artist_id) REFERENCES artists(musicbrainz_id)
);

CREATE TABLE user_song_library (
  user_id UUID NOT NULL,
  song_id UUID NOT NULL,
  added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (user_id, song_id),
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  FOREIGN KEY (song_id) REFERENCES songs(id) ON DELETE CASCADE
);

CREATE TABLE user_clusters (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL,
  cluster_index INT NOT NULL,
  centroid_embedding vector(1536) NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  UNIQUE(user_id, cluster_index)
);

CREATE TABLE song_cluster_membership (
  song_id UUID NOT NULL,
  cluster_id UUID NOT NULL,
  PRIMARY KEY (song_id, cluster_id),
  FOREIGN KEY (song_id) REFERENCES songs(id) ON DELETE CASCADE,
  FOREIGN KEY (cluster_id) REFERENCES user_clusters(id) ON DELETE CASCADE
);

CREATE TABLE song_similarity_scores (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  song_id UUID NOT NULL,
  user_id UUID NOT NULL,
  genre_score FLOAT NOT NULL,
  lyric_score FLOAT NOT NULL,
  matched_cluster_id UUID,
  combined_score FLOAT NOT NULL,
  computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (song_id) REFERENCES songs(id) ON DELETE CASCADE,
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  FOREIGN KEY (matched_cluster_id) REFERENCES user_clusters(id) ON DELETE SET NULL,
  UNIQUE(song_id, user_id)
);

-- Vector indices for fast similarity search
CREATE INDEX idx_song_embedding ON songs USING ivfflat (embedding vector_cosine_ops);
CREATE INDEX idx_cluster_centroid ON user_clusters USING ivfflat (centroid_embedding vector_cosine_ops);

-- Other indices for common queries
CREATE INDEX idx_user_clusters_user_id ON user_clusters(user_id);
CREATE INDEX idx_user_library_user_id ON user_song_library(user_id);
```

### Connection String

For Python/SQLAlchemy:
```
postgresql+psycopg2://bairry:bairry@localhost:5432/bairry
```

For Node.js/TypeORM:
```
postgres://bairry:bairry@localhost:5432/bairry
```

### Vector Similarity Queries

**Find closest cluster centroid for a song:**
```sql
SELECT cluster_id, 
       1 - (centroid_embedding <=> $1::vector) as similarity
FROM user_clusters
WHERE user_id = $2
ORDER BY similarity DESC
LIMIT 1;
```

**Compute genre score (frequency-weighted Jaccard):**
```sql
WITH genre_freq AS (
  SELECT genre, COUNT(*) as freq
  FROM (
    SELECT UNNEST(a.genres) as genre
    FROM user_song_library usl
    JOIN songs s ON usl.song_id = s.id
    JOIN artists a ON s.matched_artist_id = a.musicbrainz_id
    WHERE usl.user_id = $1
  ) g
  GROUP BY genre
),
song_genres AS (
  SELECT UNNEST($2::TEXT[]) as genre
)
SELECT COALESCE(SUM(CASE WHEN genre_freq.genre IS NOT NULL THEN freq ELSE 0 END), 0)::FLOAT / 
       (SUM(freq) + ARRAY_LENGTH($2::TEXT[], 1))::FLOAT as weighted_jaccard
FROM song_genres
FULL OUTER JOIN genre_freq ON song_genres.genre = genre_freq.genre;
```

---

## Updated Roadmap

### Phase 1: MVP
- [ ] Data models (User, Song, Artist, UserSongLibrary, Cluster, ClusterCentroid)
- [ ] PostgreSQL schema with clustering tables
- [ ] Artist name parser (handle multiple artist formats)
- [ ] MusicBrainz integration with fuzzy matching + caching
- [ ] Genius API integration for lyrics + caching
- [ ] Translation (Google Translate)
- [ ] Local embeddings (Sentence Transformers)
- [ ] Clustering pipeline (KMeans per user)
- [ ] Genre scoring (weighted by frequency)
- [ ] Lyric scoring (against cluster centroids)
- [ ] Combined scoring API
- [ ] Basic REST endpoints
- [ ] Admin ingestion endpoint (song + user management)
- [ ] Batch processing with backoff

### Phase 2: Polish & Observability
- [ ] Task queue for async ingestion (show progress)
- [ ] Caching layer (Redis)
- [ ] Error handling + retry logic
- [ ] API rate limiting / circuit breaker
- [ ] Logging and error tracking
- [ ] Admin dashboard (users, songs, ingestion progress)

### Phase 3: Optimization (If Needed)
- [ ] Incremental clustering updates
- [ ] Vector DB optimization
- [ ] Advanced fuzzy matching (edit distance tuning)
- [ ] Batch scoring API
- [ ] Performance profiling and optimization

---

## Notes

- **Typo Handling**: MusicBrainz fuzzy matching should handle most artist typos; consider Levenshtein distance or similar for fallback
- **Embedding Updates**: Consider incremental updates vs. full recomputation when user library changes
- **Rate Limiting**: External APIs will require backoff; implement exponential backoff + circuit breaker pattern
- **Testing**: Need robust test fixtures for external API mocking
