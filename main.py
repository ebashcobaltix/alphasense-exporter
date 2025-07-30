import os
import csv
import sys
import json
import argparse
import logging
from dotenv import load_dotenv


from config import Config
from logger import setup_logging
from scraper import AlphaSenseScraper


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
            scraper.logger.error("❌ Login failed!")
            sys.exit(1)

        scraper.logger.info("✅ Login successful!")

        searches = {}
        with open('saved_searches.csv', newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                search_name = row['search_name']
                search_id = row['search_id']
                searches[search_name] = search_id

        
        for name, id in searches.items():
            print(f"📤 Exporting saved search: Name: {name}, ID: {id}")
            results = scraper.export_saved_search(
                search_id=id,
                max_results=args.max_results,
                output_dir=args.output_dir,
            )

            if results:
                scraper.logger.info(f"✅ Export completed: {len(results)} files extracted")
                scraper.logger.info(json.dumps(results, indent=2))
            else:
                scraper.logger.error("❌ No results found for export")

    except Exception as e:
        scraper.logger.error(f"❌ Error during export: {e}")
        sys.exit(1)
    finally:
        scraper.close()


if __name__ == '__main__':
    main()
