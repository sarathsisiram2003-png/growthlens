from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BASE_DIR / ".env", extra="ignore")

    ee_project: str = ""
    ee_service_account_key: str = ""
    ee_service_account_email: str = ""
    http_user_agent: str = "GrowthLens/0.1 (portfolio project)"

    # LLM intent parsing (Google Gemini). Empty key -> offline preset fallback.
    gemini_api_key: str = ""
    llm_model: str = "gemini-3.5-flash-lite"
    # Set INTENT_USE_LLM=false to parse businesses with keyword presets only (briefs still use the LLM).
    intent_use_llm: bool = True

    h3_resolution: int = 8
    # Before/after satellite imagery (Sentinel-2 annual median composites)
    imagery_start_year: int = 2017
    imagery_end_year: int = 2025
    # Growth history for the time slider (Dynamic World annual mean built-up probability)
    history_start_year: int = 2016
    # Growth window (Dynamic World built-up probability, annual means)
    growth_start_year: int = 2021
    growth_end_year: int = 2024
    # VIIRS monthly radiance trend window (months back from viirs_end)
    viirs_start: str = "2022-01-01"
    viirs_end: str = "2025-01-01"

    data_dir: Path = BASE_DIR / "data"

    @property
    def cache_dir(self) -> Path:
        d = self.data_dir / "cache"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def output_dir(self) -> Path:
        d = self.data_dir / "output"
        d.mkdir(parents=True, exist_ok=True)
        return d


settings = Settings()
