"""
Generate a movie dataset with synopses, reviews, and posters.

Usage:
    cd backend && source .venv/bin/activate
    python scripts/generate_movie_dataset.py --tmdb-api-key YOUR_KEY
"""

import argparse
import json
import os
import time

import requests

# TMDB movie IDs for our 20 movies
MOVIES = [
    {"tmdb_id": 17473, "slug": "the_room"},
    {"tmdb_id": 687163, "slug": "project_hail_mary"},
    {"tmdb_id": 50546, "slug": "just_go_with_it"},
    {"tmdb_id": 238, "slug": "the_godfather"},
    {"tmdb_id": 680, "slug": "pulp_fiction"},
    {"tmdb_id": 496243, "slug": "parasite"},
    {"tmdb_id": 155, "slug": "the_dark_knight"},
    {"tmdb_id": 157336, "slug": "interstellar"},
    {"tmdb_id": 419430, "slug": "get_out"},
    {"tmdb_id": 244786, "slug": "whiplash"},
    {"tmdb_id": 376867, "slug": "moonlight"},
    {"tmdb_id": 129, "slug": "spirited_away"},
    {"tmdb_id": 536869, "slug": "cats"},
    {"tmdb_id": 526896, "slug": "morbius"},
    {"tmdb_id": 297761, "slug": "suicide_squad"},
    {"tmdb_id": 912649, "slug": "venom_the_last_dance"},
    {"tmdb_id": 1072790, "slug": "anyone_but_you"},
    {"tmdb_id": 693134, "slug": "dune_part_two"},
    {"tmdb_id": 278, "slug": "the_shawshank_redemption"},
]

TMDB_BASE = "https://api.themoviedb.org/3"
TMDB_IMG_BASE = "https://image.tmdb.org/t/p/w500"

OUTPUT_DIR = os.path.join(
    os.path.dirname(__file__),
    "..",
    "..",
    "study_files",
    "dataset",
    "movie_dataset",
)


def fetch_movie_details(tmdb_id: int, api_key: str) -> dict:
    """Fetch movie details + credits from TMDB."""
    # Movie details
    url = f"{TMDB_BASE}/movie/{tmdb_id}"
    params = {"api_key": api_key, "language": "en-US"}
    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()
    details = resp.json()

    # Credits (for director)
    credits_url = f"{TMDB_BASE}/movie/{tmdb_id}/credits"
    resp = requests.get(credits_url, params=params, timeout=15)
    resp.raise_for_status()
    credits = resp.json()

    director = None
    for crew in credits.get("crew", []):
        if crew.get("job") == "Director":
            director = crew.get("name")
            break

    details["director"] = director
    return details


def download_poster(poster_path: str, slug: str, output_dir: str) -> str | None:
    """Download poster image from TMDB CDN."""
    if not poster_path:
        print(f"  No poster available for {slug}")
        return None

    url = f"{TMDB_IMG_BASE}{poster_path}"
    posters_dir = os.path.join(output_dir, "posters")
    os.makedirs(posters_dir, exist_ok=True)
    filepath = os.path.join(posters_dir, f"{slug}.jpg")

    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    with open(filepath, "wb") as f:
        f.write(resp.content)

    return filepath


def build_synopsis(details: dict) -> str:
    """Build a synopsis text file from TMDB movie details."""
    title = details.get("title", "Unknown")
    year = (details.get("release_date") or "")[:4]
    director = details.get("director") or "Unknown"
    overview = details.get("overview") or "No overview available."
    genres = ", ".join(g["name"] for g in details.get("genres", []))
    release_date = details.get("release_date") or "Unknown"
    rating = details.get("vote_average", 0)
    runtime = details.get("runtime") or "Unknown"

    return (
        f"**{title}** ({year})\n"
        f"Directed by {director}\n"
        f"\n"
        f"{overview}\n"
        f"\n"
        f"**Genres:** {genres}\n"
        f"**Release Date:** {release_date}\n"
        f"**Runtime:** {runtime} min\n"
        f"**Rating:** {rating}/10"
    )


def save_synopsis(details: dict, slug: str, output_dir: str):
    """Save synopsis to a text file."""
    synopses_dir = os.path.join(output_dir, "synopses")
    os.makedirs(synopses_dir, exist_ok=True)
    filepath = os.path.join(synopses_dir, f"{slug}.txt")

    content = build_synopsis(details)
    with open(filepath, "w") as f:
        f.write(content)


def fetch_reviews(tmdb_id: int, api_key: str, max_reviews: int = 4) -> list[dict]:
    """Fetch reviews from TMDB for a movie."""
    reviews = []
    page = 1
    while len(reviews) < max_reviews:
        url = f"{TMDB_BASE}/movie/{tmdb_id}/reviews"
        params = {"api_key": api_key, "language": "en-US", "page": page}
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])
        if not results:
            break
        reviews.extend(results)
        if page >= data.get("total_pages", 1):
            break
        page += 1

    return reviews[:max_reviews]


def save_reviews(reviews: list[dict], slug: str, movie_title: str, output_dir: str) -> int:
    """Save reviews as individual text files. Returns count saved."""
    reviews_dir = os.path.join(output_dir, "reviews")
    os.makedirs(reviews_dir, exist_ok=True)

    saved = 0
    for i, review in enumerate(reviews):
        rating = review.get("author_details", {}).get("rating")
        content = review.get("content", "").strip()
        if not content:
            continue

        # Build review text
        lines = [f"**Review of {movie_title}**"]
        if rating is not None:
            lines.append(f"**Rating: {rating}/10**")
        lines.append("")
        lines.append(content)

        filepath = os.path.join(reviews_dir, f"{slug}_review_{i + 1}.txt")
        with open(filepath, "w") as f:
            f.write("\n".join(lines))
        saved += 1

    return saved


def main():
    parser = argparse.ArgumentParser(description="Generate movie dataset from TMDB")
    parser.add_argument("--tmdb-api-key", required=True, help="TMDB API key")
    parser.add_argument(
        "--output-dir",
        default=os.path.abspath(OUTPUT_DIR),
        help="Output directory for dataset files",
    )
    parser.add_argument(
        "--skip-posters",
        action="store_true",
        help="Skip downloading poster images",
    )
    parser.add_argument(
        "--max-reviews",
        type=int,
        default=4,
        help="Max reviews to fetch per movie (default: 4)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Limit to first N movies (0 = all)",
    )
    args = parser.parse_args()

    output_dir = args.output_dir
    os.makedirs(output_dir, exist_ok=True)

    movies_to_fetch = MOVIES[: args.limit] if args.limit > 0 else MOVIES
    all_details = []
    total_reviews = 0

    print(f"Fetching details for {len(movies_to_fetch)} movies from TMDB...\n")

    for movie in movies_to_fetch:
        tmdb_id = movie["tmdb_id"]
        slug = movie["slug"]

        print(f"Fetching: {slug} (TMDB ID: {tmdb_id})")
        try:
            details = fetch_movie_details(tmdb_id, args.tmdb_api_key)
            details["_slug"] = slug
            all_details.append(details)

            # Save synopsis
            save_synopsis(details, slug, output_dir)
            print(f"  Synopsis saved: synopses/{slug}.txt")

            # Download poster
            if not args.skip_posters:
                poster_path = details.get("poster_path") or ""
                download_poster(poster_path, slug, output_dir)
                print(f"  Poster saved: posters/{slug}.jpg")

            # Fetch and save reviews
            movie_title = details.get("title", slug)
            reviews = fetch_reviews(tmdb_id, args.tmdb_api_key, args.max_reviews)
            saved = save_reviews(reviews, slug, movie_title, output_dir)
            total_reviews += saved
            print(f"  Reviews saved: {saved} (of {len(reviews)} fetched)")

            # Be nice to TMDB API
            time.sleep(0.25)

        except requests.HTTPError as e:
            print(f"  ERROR fetching {slug}: {e}")
            continue

    # Save raw metadata for later use
    metadata_path = os.path.join(output_dir, "_raw_metadata.json")
    with open(metadata_path, "w") as f:
        json.dump(all_details, f, indent=2)
    print(f"\nRaw metadata saved to: {metadata_path}")

    print(f"\nDone! {len(all_details)} movies processed.")
    print(f"  Synopses: {output_dir}/synopses/ ({len(all_details)} files)")
    print(f"  Reviews:  {output_dir}/reviews/ ({total_reviews} files)")
    print(f"  Posters:  {output_dir}/posters/")


if __name__ == "__main__":
    main()
