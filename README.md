
# AlphaSense Saved Search Exporter

Automate the export of saved searches from [AlphaSense](https://research.alpha-sense.com/) using headless browser automation with Selenium.


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
- `--max-results`: Maximum number of results per search (default 100)
- `--no-headless`: Run browser in GUI mode
- `--output-dir`: Directory for exported files (default `./exports`)
- `--debug`: Enable debug-level logging

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
```

---

## 📁 Project Structure

```
.
├── main.py            # Main CLI entry point
├── scraper.py         # AlphaSenseScraper class (Selenium automation)
├── config.py          # YAML config loader
├── logger.py          # Logging setup/utilities
├── requirements.txt   # Python package dependencies
├── config.yaml        # Config for browser and AlphaSense URLs
├── saved_searches.csv # CSV of saved search names/IDs
└── README.md          # This file
```

---

## ⚙️ How It Works

1. **Loads configuration** and credentials.
2. **Initializes Selenium** browser with provided options (headless by default).
3. **Logs in** to AlphaSense securely.
4. **Reads `saved_searches.csv`** and iterates through each search.
5. **Navigates** to each saved search page, waits for result rows.
6. **Exports results** in blocks, handling dynamic/virtualized content robustly.
7. **Prints and logs** detailed row-level data for transparency.

---

## 🛠️ Development Notes

- Uses `webdriver-manager` to simplify ChromeDriver installation.
- For debugging, set `--debug` to see all log output.
- Selenium options and waits are adjustable in `config.yaml`.

---