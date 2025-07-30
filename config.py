# config.py
import yaml

class Config:
    def __init__(self, path="config.yaml"):
        with open(path, "r") as f:
            self.settings = yaml.safe_load(f)

    def get(self, key, default=None):
        return self.settings.get(key, default)

    def get_browser_config(self):
        return self.settings.get("browser", {})

    def get_alphasense_config(self):
        return self.settings.get("alphasense", {})

    def __getitem__(self, item):
        return self.settings.get(item)
