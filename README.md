# AlphaSense Saved Search Exporter

**Clean, modular, and fast** automation tool for exporting saved searches from [AlphaSense](https://research.alpha-sense.com/) using intelligent browser automation with Selenium. Features smart data collection, caching, and optimized bundle export capabilities.

## 🚀 Quick Start

### 1. Setup Environment
```bash
git clone <repository-url>
cd alphasense-scraper

python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure Credentials
Create a `.env` file:
```bash
ALPHASENSE_USERNAME=your-email@example.com
ALPHASENSE_PASSWORD=yourpassword

# Optional: For automatic Dropbox uploads
DROPBOX_APP_KEY=your-dropbox-app-key
DROPBOX_APP_SECRET=your-dropbox-app-secret
DROPBOX_ACCESS_TOKEN=your-access-token-if-you-have-one
```

### 3. Setup Dropbox (Optional)
For automatic uploads to Dropbox, you have two options:

**Option A: Using OAuth Flow (Recommended)**
1. Create a Dropbox app at https://www.dropbox.com/developers/apps
2. Get your App Key and App Secret from the app settings
3. Add both to your `.env` file:
   ```
   DROPBOX_APP_KEY=your-app-key
   DROPBOX_APP_SECRET=your-app-secret
   ```
4. On first run, you'll be prompted to authorize via OAuth browser flow
5. The generated access token will be displayed for future use

**Option B: Using Pre-generated Access Token**
1. If you already have a Dropbox access token, add it directly:
   ```
   DROPBOX_ACCESS_TOKEN=your-existing-token
   ```
2. The system will use this token directly (no OAuth flow needed)

**Folder Structure**: Files are organized as `/<TICKER>/Broker Reports/<YYYY-MM-DD>/`

### 4. Prepare Search List
Add your searches to `saved_searches.csv`:
```csv
search_name,search_id
NVIDIA Analysis,abc123def456
Tesla Reports,xyz789ghi012
```

### 5. Run Export
```bash
# Export all searches (first 20 results each)
python main.py

# Export specific search with more results
python main.py --search "NVIDIA Analysis" --max-results 50

# Debug mode with visible browser
python main.py --no-headless --debug
```

## 📖 Usage Guide

### Basic Commands

```bash
# Export all searches (default: 20 results each)
python main.py

# Export specific search
python main.py --search "NVIDIA Analysis"

# Export with more results per search
python main.py --max-results 100

# Full export mode (collect all data, then export in bundles)
python main.py --mode full --max-results 200

# Debug mode with visible browser
python main.py --no-headless --debug

# Custom output directory
python main.py --output-dir "./my-exports"

# Use different CSV file
python main.py --csv-file "./my-searches.csv"
```

### CLI Options

| Option | Description | Default |
|--------|-------------|---------|
| `--username` | AlphaSense username (or use env var) | `$ALPHASENSE_USERNAME` |
| `--password` | AlphaSense password (or use env var) | `$ALPHASENSE_PASSWORD` |
| `--dropbox-app-key` | Dropbox app key (or use env var) | `$DROPBOX_APP_KEY` |
| `--dropbox-app-secret` | Dropbox app secret (or use env var) | `$DROPBOX_APP_SECRET` |
| `--dropbox-token` | Dropbox access token (or use env var) | `$DROPBOX_ACCESS_TOKEN` |
| `--search` | Export only specific search name | All searches |
| `--max-results` | Maximum results per search | 20 |
| `--mode` | Export mode: `simple` or `full` | `simple` |
| `--csv-file` | Path to CSV with searches | `saved_searches.csv` |
| `--output-dir` | Output directory for files | `./exports` |
| `--no-headless` | Run browser in visible mode | Headless |
| `--debug` | Enable debug logging | Info level |

### Export Modes

**Simple Mode** (`--mode simple`)
- Quickly exports first N results
- Best for small datasets or quick testing
- Single-phase process

**Full Mode** (`--mode full`)
- Two-phase process: collect all data, then export in bundles
- Best for large datasets requiring complete coverage
- Supports resumable exports via caching

## 🏗️ Architecture

### Project Structure
```
alphasense-scraper/
├── main.py                    # 🎯 Clean CLI entry point
├── scraper.py                 # 🔧 Main scraper orchestration
├── config.py                  # ⚙️ Configuration management
├── logger.py                  # 📝 Logging utilities
├── handlers/                  # 📦 Specialized handler modules
│   ├── __init__.py            #     Package initialization
│   ├── browser_manager.py     # 🌐 Browser setup & navigation
│   ├── ui_handler.py          # 🖱️ UI interactions & element manipulation
│   ├── file_handler.py        # 📁 Download detection & ZIP extraction
│   ├── cache_manager.py       # 💾 Data caching & persistence
│   └── dropbox_handler.py     # ☁️ Dropbox OAuth & uploads
├── config.yaml                # ⚙️ Browser & system configuration
├── saved_searches.csv         # 📊 Search names and IDs
├── cache/                     # 💾 Cached search data
│   └── search_*.json          #     JSON cache files
├── exports/                   # 📦 Downloaded & extracted files
└── requirements.txt           # 📋 Python dependencies
```

### Handler Modules

**🌐 BrowserManager** (`handlers/browser_manager.py`)
- Browser initialization and configuration
- Login handling and session management
- Navigation and page loading

**🖱️ UIHandler** (`handlers/ui_handler.py`)
- Scrolling and element interaction
- Checkbox selection with multiple fallback strategies
- Export button detection and clicking

**📁 FileHandler** (`handlers/file_handler.py`)
- Smart download detection (ZIP files only)
- Automatic extraction and folder organization
- Cleanup of temporary files and system folders

**💾 CacheManager** (`handlers/cache_manager.py`)
- JSON data persistence for resumable exports
- Search name resolution from CSV
- Cache file management and listing

**☁️ DropboxHandler** (`handlers/dropbox_handler.py`)
- OAuth authentication flow with Dropbox
- Automatic ticker extraction from search names
- Organized folder structure: `/<TICKER>/Broker Reports/<YYYY-MM-DD>/`
- Bulk folder uploads with progress tracking

## ⚙️ Configuration

All settings are in `config.yaml`:

```yaml
browser:
  window_size:
    width: 1920
    height: 1080
  user_agent: "Mozilla/5.0..."
  timeout: 30
  implicit_wait: 10

alphasense:
  base_url: "https://research.alpha-sense.com"

scraping:
  download_dir: "./exports"
  output_dir: "./exports"
  max_scroll_attempts: 30
  bundle_size: 20
```

## 🔄 How It Works

### Simple Mode Process
1. **Initialize**: Load config, setup browser, login to AlphaSense
2. **Navigate**: Go to each saved search page
3. **Select**: Choose first N results using smart checkbox selection
4. **Export**: Click export button and wait for ZIP download
5. **Extract**: Automatically extract and organize files

### Full Mode Process
1. **Phase 1 - Data Collection**:
   - Navigate to search page
   - Scroll through all results using multiple strategies
   - Extract metadata from each row
   - Cache data to JSON file for resumability

2. **Phase 2 - Bundle Export**:
   - Load cached data
   - Process in configurable bundles (default: 20)
   - Select checkboxes for each bundle
   - Export and extract automatically

### Key Optimizations
- ⚡ **Reduced delays**: From 800ms to 200ms for UI interactions
- 🎯 **Smart retries**: Intelligent retry logic instead of fixed delays
- 🔍 **ZIP-only detection**: Only monitors for completed ZIP files
- 📦 **Bundle processing**: Prevents timeouts on large exports
- 🧠 **Multiple scrolling strategies**: Handles different page states

## 🛠️ Development

### Running in Debug Mode
```bash
python main.py --no-headless --debug --search "Test Search"
```

### Common Issues & Solutions

**Login failures**: 
- Check credentials in `.env` file
- Verify AlphaSense account access

**Download not detected**:
- Ensure download directory exists and is writable
- Check that ZIP files are completing (not partial downloads)

**Checkbox selection fails**:
- Try with visible browser (`--no-headless`)
- Check debug logs for specific UI element issues

**Large exports timing out**:
- Use full mode with smaller bundle sizes
- Leverage caching to resume interrupted exports

### Testing
```bash
# Test with single search and visible browser
python main.py --search "Test" --max-results 5 --no-headless --debug

# Test full workflow
python main.py --mode full --max-results 50 --debug
```

## 📊 Output Structure

Exported files are organized as:
```
exports/
├── SearchName_20250812_143022/          # Simple mode
│   ├── document1.pdf
│   ├── document2.pdf
│   └── ...
└── SearchName_bundle1_20250812_143022/  # Full mode bundles
    ├── document1.pdf
    ├── document2.pdf
    └── ...
```

Cache files for resumable exports:
```
cache/
├── search_abc123_20250812_143022.json
├── search_xyz789_20250812_144503.json
└── ...
```
