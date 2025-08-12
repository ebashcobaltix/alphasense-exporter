import os
import csv
import sys
import json
import argparse
import logging
import time
import zipfile
import shutil
from pathlib import Path
from dotenv import load_dotenv


from config import Config
from logger import setup_logging
from scraper import AlphaSenseScraper


def unzip_and_flatten(download_dir: Path):
    """Unzip all ZIPs in download_dir, move extracted files into download_dir (no subfolders), then remove ZIPs/temp."""
    download_dir = Path(download_dir).resolve()
    download_dir.mkdir(parents=True, exist_ok=True)

    for zpath in download_dir.glob("*.zip"):
        try:
            temp_dir = download_dir / f".extract_{int(time.time()*1000)}"
            temp_dir.mkdir(parents=True, exist_ok=True)

            with zipfile.ZipFile(zpath, 'r') as zf:
                zf.extractall(temp_dir)

            for p in temp_dir.rglob("*"):
                if not p.is_file():
                    continue
                if any(part.startswith("__MACOSX") for part in p.parts):
                    continue

                target = download_dir / p.name
                if target.exists():
                    stem, suf = target.stem, target.suffix
                    i = 2
                    while True:
                        candidate = download_dir / f"{stem} ({i}){suf}"
                        if not candidate.exists():
                            target = candidate
                            break
                        i += 1
                shutil.move(str(p), str(target))

            shutil.rmtree(temp_dir, ignore_errors=True)
            zpath.unlink(missing_ok=True)
            print(f"📂 Unzipped and flattened: {zpath.name}")
        except Exception as e:
            print(f"Failed to extract {zpath.name}: {e}")


def main():
    parser = argparse.ArgumentParser(description="Export a saved AlphaSense search")

    load_dotenv()

    parser.add_argument('--username', default=os.getenv('ALPHASENSE_USERNAME'), help='AlphaSense username (or set ALPHASENSE_USERNAME env var)')
    parser.add_argument('--password', default=os.getenv('ALPHASENSE_PASSWORD'), help='AlphaSense password (or set ALPHASENSE_PASSWORD env var)')
    parser.add_argument('--max-results', type=int, default=100, help='Max results to export')
    parser.add_argument('--no-headless', action='store_true', help='Run in GUI mode (not headless)')
    parser.add_argument('--output-dir', default='./exports', help='Output directory for exports')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')

    args = parser.parse_args()

    config = Config('config.yaml')
    scraper = AlphaSenseScraper(config, headless=not args.no_headless)

    try:
        if not scraper.login(args.username, args.password):
            scraper.logger.error("Login failed!")
            sys.exit(1)

        scraper.logger.info("Login successful!")

        searches = {}
        with open('saved_searches.csv', newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                search_name = row['search_name']
                search_id = row['search_id']
                searches[search_name] = search_id

        scraper.export_first_n_in_search(search_id="33f44ae2-0467-4f79-ab72-54e18a430ca8", n=20, output_dir="./exports")

        # unzip + flatten into ./exports 
        unzip_and_flatten(Path("./exports"))
        
        # for name, id in searches.items():
        #     print(f"Exporting saved search: Name: {name}, ID: {id}")
        #     results = scraper.export_saved_search(
        #         search_id=id,
        #         max_results=args.max_results,
        #         output_dir=args.output_dir,
        #     )
        #
        #     if results:
        #         scraper.logger.info(f"Export completed: {len(results)} files extracted")
        #         scraper.logger.info(json.dumps(results, indent=2))
        #     else:
        #         scraper.logger.error("No results found for export")

    except Exception as e:
        scraper.logger.error(f"Error during export: {e}")
        sys.exit(1)
    finally:
        scraper.close()


if __name__ == '__main__':
    main()
