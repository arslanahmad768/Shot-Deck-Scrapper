import os
from dataclasses import dataclass
from typing import Optional

@dataclass
class ScrapingConfig:
    # Login credentials
    email: str = os.getenv('SHOTDECK_EMAIL', '')
    password: str = os.getenv('SHOTDECK_PASSWORD', '')
    
    # Scraping settings
    base_url: str = 'https://shotdeck.com'
    browse_url: str = 'https://shotdeck.com/browse/stills#/sort/movie_year_desc'
    
    # Performance settings
    concurrent_browsers: int = 3
    concurrent_pages_per_browser: int = 2
    request_delay: float = 1.0  # seconds between requests
    retry_attempts: int = 3
    
    # Storage settings
    download_images: bool = True
    images_directory: str = './downloaded_images'
    database_url: str = os.getenv('DATABASE_URL', 'sqlite:///shotdeck_data.db')
    
    # Browser settings
    headless: bool = False
    user_agent: str = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    viewport_width: int = 1920
    viewport_height: int = 1080
    
    # Rate limiting
    max_requests_per_minute: int = 60
    backoff_factor: float = 2.0