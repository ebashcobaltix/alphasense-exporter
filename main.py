#!/usr/bin/env python3
"""
AlphaSense Scraper - Main CLI Entry Point

Clean, modular CLI for exporting saved AlphaSense searches.
"""

import os
import csv
import sys
import argparse
from pathlib import Path
from dotenv import load_dotenv

from config import Config
from logger import setup_logging
from scraper import AlphaSenseScraper


def load_saved_searches(csv_path: str = 'saved_searches.csv') -> dict:
    """Load saved searches from CSV file"""
    searches = {}
    csv_file = Path(csv_path)
    
    if not csv_file.exists():
        print(f"❌ Error: CSV file not found at {csv_path}")
        print("Please ensure you have a saved_searches.csv file with search_name and search_id columns")
        sys.exit(1)
    
    try:
        with open(csv_file, newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                search_name = row.get('search_name', '').strip()
                search_id = row.get('search_id', '').strip()
                if search_name and search_id:
                    searches[search_name] = search_id
                    
        if not searches:
            print(f"❌ Error: No valid searches found in {csv_path}")
            print("Please ensure your CSV has 'search_name' and 'search_id' columns with data")
            sys.exit(1)
            
        return searches
        
    except Exception as e:
        print(f"❌ Error reading CSV file {csv_path}: {e}")
        sys.exit(1)


def setup_cli_args() -> argparse.ArgumentParser:
    """Setup command line argument parser"""
    parser = argparse.ArgumentParser(
        description="Export saved AlphaSense searches",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
            Examples:
            python main.py                           # Export all searches (first 20 results each)
            python main.py --max-results 50         # Export 50 results per search
            python main.py --search "NVIDIA"        # Export only the "NVIDIA" search
            python main.py --no-headless --debug    # Run with visible browser and debug logging
        """
    )

    # Authentication
    parser.add_argument('--username', 
                       default=os.getenv('ALPHASENSE_USERNAME'),
                       help='AlphaSense username (or set ALPHASENSE_USERNAME env var)')
    parser.add_argument('--password', 
                       default=os.getenv('ALPHASENSE_PASSWORD'),
                       help='AlphaSense password (or set ALPHASENSE_PASSWORD env var)')
    
    # Dropbox options
    parser.add_argument('--dropbox-app-key',
                       default=os.getenv('DROPBOX_APP_KEY'),
                       help='Dropbox app key (or set DROPBOX_APP_KEY env var)')
    parser.add_argument('--dropbox-app-secret',
                       default=os.getenv('DROPBOX_APP_SECRET'),
                       help='Dropbox app secret (or set DROPBOX_APP_SECRET env var)')
    parser.add_argument('--dropbox-token',
                       default=os.getenv('DROPBOX_ACCESS_TOKEN'),
                       help='Dropbox access token (or set DROPBOX_ACCESS_TOKEN env var)')
    
    # Export options
    parser.add_argument('--max-results', type=int, default=20,
                       help='Maximum results to export per search (default: 20)')
    parser.add_argument('--search', type=str,
                       help='Export only the specified search name (exports all if not specified)')
    parser.add_argument('--csv-file', default='saved_searches.csv',
                       help='Path to CSV file with saved searches (default: saved_searches.csv)')
    
    # Technical options
    parser.add_argument('--no-headless', action='store_true',
                       help='Run browser in visible mode (default: headless)')
    parser.add_argument('--output-dir', default='./exports',
                       help='Output directory for exported files (default: ./exports)')
    parser.add_argument('--debug', action='store_true',
                       help='Enable debug logging')
    
    # Export mode
    parser.add_argument('--mode', choices=['simple', 'full'], default='simple',
                       help='Export mode: simple (first N) or full (collect all then export in bundles)')

    return parser


def validate_credentials(username: str, password: str) -> None:
    """Validate that credentials are provided"""
    if not username or not password:
        print("❌ Error: Username and password are required")
        print("Provide them via:")
        print("  1. Command line: --username USERNAME --password PASSWORD")
        print("  2. Environment: ALPHASENSE_USERNAME=user ALPHASENSE_PASSWORD=pass")
        print("  3. .env file with ALPHASENSE_USERNAME and ALPHASENSE_PASSWORD")
        sys.exit(1)


def export_single_search(scraper: AlphaSenseScraper, search_name: str, search_id: str, 
                        max_results: int, mode: str) -> bool:
    """Export a single search"""
    scraper.logger.info(f"🔎 Starting export: {search_name} (ID: {search_id})")
    
    try:
        if mode == 'simple':
            success = scraper.export_first_n_in_search(search_id=search_id, n=max_results)
        else:  # full mode
            exported_files = scraper.export_saved_search(search_id=search_id, max_results=max_results)
            success = len(exported_files) > 0
            
        if success:
            scraper.logger.info(f"✅ Successfully exported: {search_name}")
            return True
        else:
            scraper.logger.error(f"❌ Failed to export: {search_name}")
            return False
            
    except Exception as e:
        scraper.logger.error(f"❌ Error exporting {search_name}: {e}")
        return False


def main():
    """Main CLI entry point"""
    load_dotenv()  # Load environment variables from .env file
    
    parser = setup_cli_args()
    args = parser.parse_args()
    
    # Setup logging
    if args.debug:
        setup_logging(level='DEBUG')
    else:
        setup_logging(level='INFO')
    
    # Validate credentials
    validate_credentials(args.username, args.password)
    
    # Load saved searches
    print(f"📄 Loading saved searches from {args.csv_file}...")
    searches = load_saved_searches(args.csv_file)
    print(f"✅ Found {len(searches)} saved searches")
    
    # Filter searches if specific one requested
    if args.search:
        if args.search not in searches:
            print(f"❌ Error: Search '{args.search}' not found in CSV")
            print(f"Available searches: {', '.join(searches.keys())}")
            sys.exit(1)
        searches = {args.search: searches[args.search]}
        print(f"🎯 Filtering to single search: {args.search}")
    
    # Create output directory
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"📁 Output directory: {output_dir.resolve()}")
    
    # Initialize scraper
    print("🚀 Initializing scraper...")
    config = Config('config.yaml')
    scraper = AlphaSenseScraper(
        config, 
        headless=not args.no_headless,
        dropbox_app_key=args.dropbox_app_key,
        dropbox_app_secret=args.dropbox_app_secret,
        dropbox_token=args.dropbox_token
    )
    
    try:
        # Login
        print("🔐 Logging in...")
        if not scraper.login(args.username, args.password):
            print("❌ Login failed!")
            sys.exit(1)
        print("✅ Login successful!")
        
        # Export searches
        successful_exports = 0
        total_searches = len(searches)
        
        print(f"\n📊 Starting export of {total_searches} searches (max {args.max_results} results each, {args.mode} mode)...")
        print("=" * 60)
        
        for i, (search_name, search_id) in enumerate(searches.items(), 1):
            print(f"\n[{i}/{total_searches}] {search_name}")
            if export_single_search(scraper, search_name, search_id, args.max_results, args.mode):
                successful_exports += 1
        
        # Summary
        print("=" * 60)
        print(f"🎉 Export complete!")
        print(f"✅ Successful: {successful_exports}/{total_searches}")
        if successful_exports < total_searches:
            print(f"❌ Failed: {total_searches - successful_exports}/{total_searches}")
        
    except KeyboardInterrupt:
        print("\n⏹️  Export cancelled by user")
        sys.exit(130)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        sys.exit(1)
    finally:
        print("🔒 Closing browser...")
        scraper.close()


if __name__ == '__main__':
    main()