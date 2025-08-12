# AlphaSense Saved Search Exporter  

Automate the export of saved searches from [AlphaSense](https://research.alpha-sense.com/) using headless browser automation with Selenium. Features intelligent data collection, caching, and bundle export capabilities.

## 📦 Setup Instructions  

### 1. Clone and Install Dependencies  
```bash
git clone https://github.com/your-org/alphasense-exporter.git
cd alphasense-exporter

python3 -m venv venv
source venv/bin/activate    # On Windows: venv\Scripts\activate

pip install -r requirements.txt
```

### 2. Configure Environment  
Copy and edit the provided `config.yaml` for browser/user settings.   

Set your AlphaSense credentials via environment variables or a `.env` file:  
```
ALPHASENSE_USERNAME=your-email@example.com
ALPHASENSE_PASSWORD=yourpassword
```

Or pass them as command-line arguments.

---

## 📝 Usage

### Export All Saved Searches in `saved_searches.csv`:

```bash
python main.py --no-headless
```

**Optional Arguments:**
- `--search-id`: Specific AlphaSense search ID to export
- `--export-first N`: Export only first N documents (simple method) 
- `--full-export`: Collect all data then export in bundles (advanced method)
- `--resume-cache FILE`: Resume export from cached data file
- `--max-results`: Maximum number of results per search (default 100)
- `--bundle-size`: Number of documents per export bundle (default 20)
- `--no-headless`: Run browser in GUI mode
- `--output-dir`: Directory for exported files (default `./exports`)
- `--debug`: Enable debug-level logging
- `--list-cache`: Show all available cache files

---

## 🔧 Configuration  

All advanced settings are stored in `config.yaml`:

```yaml
browser:
  window_size:
    width: 1920
    height: 1080
  user_agent: "CustomAgent/1.0"
  timeout: 30
  implicit_wait: 10

alphasense:
  base_url: "https://research.alpha-sense.com"

scraping:
  download_dir: "./exports"
  max_scroll_attempts: 30
  bundle_size: 20
```

---

## 📁 Project Structure  

```
.
├── main.py            # Main CLI entry point
├── scraper.py         # AlphaSenseScraper class with intelligent data collection
├── config.py          # YAML config loader
├── logger.py          # Logging setup/utilities
├── requirements.txt   # Python package dependencies
├── config.yaml        # Config for browser and AlphaSense URLs
├── saved_searches.csv # CSV of saved search names/IDs
├── cache/             # Directory for cached search data
│   └── search_*.json  # Cached search results for resumable exports
├── exports/           # Directory for downloaded files
└── README.md          # This file
```

---

## ⚙️ How It Works  

1. **Loads configuration** and credentials.
2. **Initializes Selenium** browser with provided options (headless by default).
3. **Logs in** to AlphaSense securely.
4. **Reads `saved_searches.csv`** and iterates through each search.
5. **Navigates** to each saved search page, waits for result rows.
6. **Collects all data** using intelligent scrolling with multiple strategies to handle dynamic content.
7. **Caches collected data** to JSON files for resumable exports.
8. **Exports results** in configurable bundles, handling virtualized content robustly.
9. **Tracks progress** and handles failures gracefully with partial export recovery.

### Two-Phase Export Process:
- **Phase 1**: Scroll through results, collect metadata, cache to file
- **Phase 2**: Load cached data, select checkboxes in bundles, export downloads

---

## 🛠️ Development Notes  

- Uses `webdriver-manager` to simplify ChromeDriver installation.
- Features intelligent scrolling strategies for AlphaSense's dynamic content loading.
- Robust checkbox selection with multiple fallback methods for UI reliability.
- Bundle-based processing prevents timeouts on large exports.
- Caching system enables resumable exports for interrupted processes.
- For debugging, set `--debug` to see all log output and `--no-headless` for visible browser.
- Selenium options and waits are adjustable in `config.yaml`.

---