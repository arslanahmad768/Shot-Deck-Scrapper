# Shotdeck Image Scraper

A high-performance, production-ready web scraper for extracting images and metadata from Shotdeck.com using Playwright and Python.

## Features

- **Scalable Architecture**: Multi-browser, multi-page concurrent scraping
- **Smart Rate Limiting**: Adaptive rate limiting to avoid detection and bans
- **Robust Error Handling**: Retry logic, graceful failure recovery
- **Database Storage**: Comprehensive metadata storage with SQLite/PostgreSQL support
- **Image Downloads**: Parallel image downloading with deduplication
- **Login Management**: Automatic session management and re-authentication
- **Progress Tracking**: Real-time statistics and logging
- **Graceful Shutdown**: Safe interruption handling to preserve data

## Requirements

- Python 3.8+
- Shotdeck.com account credentials
- Sufficient disk space for images (potentially several GB)

## Installation

1. **Install Python dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Install Playwright browsers:**
   ```bash
   playwright install chromium
   ```

3. **Configure environment:**
   ```bash
   cp .env.example .env
   # Edit .env with your Shotdeck credentials
   ```

## Configuration

Edit `.env` file with your settings:

```env
# Required: Shotdeck login credentials
SHOTDECK_EMAIL=your_email@example.com
SHOTDECK_PASSWORD=your_password

# Optional: Database URL (defaults to SQLite)
DATABASE_URL=sqlite:///shotdeck_data.db

# Optional: Limit pages (remove for unlimited scraping)
MAX_PAGES=100
```

### Advanced Configuration

Edit `config.py` for fine-tuning:

- **Performance**: Adjust concurrent browsers and request delays
- **Rate Limiting**: Configure request limits and backoff strategies
- **Storage**: Customize download directories and database settings
- **Browser Settings**: Modify user agents and viewport settings

## Usage

### Basic Usage

```bash
python run_scraper.py
```

### Direct Execution

```bash
python main_scraper.py
```

### Running with Custom Settings

You can modify `config.py` or override settings programmatically:

```python
from config import ScrapingConfig
from main_scraper import ShotdeckScraper

# Custom configuration
config = ScrapingConfig()
config.concurrent_browsers = 5
config.max_requests_per_minute = 120
config.download_images = False  # Only scrape metadata

scraper = ShotdeckScraper(config)
await scraper.initialize()
await scraper.scrape_all_pages()
```

## Architecture

### Components

1. **MainScraper**: Orchestrates the entire scraping process
2. **LoginManager**: Handles authentication and session management
3. **ImageScraper**: Extracts image data and handles downloads
4. **PaginationHandler**: Manages page navigation and detection
5. **RateLimiter**: Implements adaptive rate limiting
6. **BrowserPool**: Manages multiple browser instances
7. **DatabaseManager**: Handles data persistence

### Data Flow

```
Login → Navigate Pages → Extract Images → Download Files → Store Metadata
  ↓         ↓              ↓               ↓              ↓
Session   Pagination    Image URLs      Local Files    Database
```

## Database Schema

The scraper creates the following database structure:

```sql
CREATE TABLE images (
    id INTEGER PRIMARY KEY,
    shotdeck_id VARCHAR(100) UNIQUE,
    title VARCHAR(500),
    description TEXT,
    image_url VARCHAR(1000),
    thumbnail_url VARCHAR(1000),
    local_path VARCHAR(1000),
    tags JSON,
    metadata JSON,
    film_title VARCHAR(500),
    director VARCHAR(200),
    cinematographer VARCHAR(200),
    year INTEGER,
    genre VARCHAR(100),
    created_at TIMESTAMP,
    downloaded BOOLEAN DEFAULT FALSE,
    download_attempts INTEGER DEFAULT 0
);
```

## Performance Optimizations

### Concurrency
- Multiple browser instances running in parallel
- Multiple pages per browser for efficient resource usage
- Asynchronous image downloads with semaphore limiting

### Rate Limiting
- Adaptive delays based on success/failure rates
- Request time tracking to stay within limits
- Exponential backoff on errors

### Memory Management
- Streaming data processing to avoid memory buildup
- Automatic cleanup of browser resources
- Efficient image handling with temporary storage

### Error Recovery
- Automatic retry logic with configurable attempts
- Session restoration on authentication failures
- Graceful handling of network timeouts

## Monitoring and Logging

The scraper provides comprehensive logging:

- **Progress Statistics**: Real-time scraping metrics
- **Error Tracking**: Detailed error logs with stack traces
- **Performance Metrics**: Request rates and timing information
- **Status Updates**: Page navigation and download progress

### Log Files

- `shotdeck_scraper.log`: Complete scraping log
- Console output: Real-time progress updates

## Ethical Considerations

### Rate Limiting
- Respects server resources with configurable delays
- Implements exponential backoff on errors
- Monitors response times to adjust load

### Terms of Service
- **Important**: Review Shotdeck's Terms of Service before scraping
- Ensure compliance with their robots.txt
- Consider reaching out for permission for large-scale scraping

### Data Usage
- Only scrape data for legitimate purposes
- Respect copyright and intellectual property rights
- Don't redistribute scraped content without permission

## Troubleshooting

### Common Issues

1. **Login Failures**
   ```bash
   # Check credentials in .env file
   # Verify account is not locked
   # Try logging in manually first
   ```

2. **Rate Limiting**
   ```bash
   # Increase delays in config.py
   # Reduce concurrent_browsers setting
   # Check for IP-based restrictions
   ```

3. **Memory Issues**
   ```bash
   # Reduce concurrent downloads
   # Enable periodic cleanup
   # Monitor system resources
   ```

4. **Database Errors**
   ```bash
   # Check database permissions
   # Verify disk space
   # Test database connection
   ```

### Performance Tuning

For optimal performance:

1. **Network**: Ensure stable, fast internet connection
2. **Storage**: Use SSD for database and image storage
3. **Memory**: Monitor RAM usage, adjust concurrency as needed
4. **CPU**: Multi-core systems can handle more concurrent browsers

## Legal Disclaimer

This tool is provided for educational and research purposes. Users are responsible for:

- Complying with Shotdeck's Terms of Service
- Respecting rate limits and server resources
- Ensuring lawful use of scraped data
- Obtaining necessary permissions for commercial use

The authors assume no responsibility for misuse of this tool.

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.