import asyncio
import logging
from pathlib import Path
from playwright.async_api import async_playwright
from typing import List, Dict, Any, Optional
import json
from datetime import datetime
import signal
import sys

from config import ScrapingConfig
from database import DatabaseManager
from login_manager import LoginManager
from image_scraper import ImageScraper
from pagination_handler import PaginationHandler
from rate_limiter import RateLimiter, BrowserPool

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('shotdeck_scraper.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class ShotdeckScraper:
    def __init__(self, config: ScrapingConfig):
        self.config = config
        self.db_manager = DatabaseManager(config.database_url)
        self.login_manager = LoginManager(config.email, config.password)
        self.image_scraper = ImageScraper(config.images_directory)
        self.pagination_handler = PaginationHandler()
        self.rate_limiter = RateLimiter(config.max_requests_per_minute, config.backoff_factor)
        self.browser_pool = BrowserPool(config.concurrent_browsers, config.concurrent_pages_per_browser)
        
        # Statistics
        self.stats = {
            'pages_scraped': 0,
            'images_found': 0,
            'images_downloaded': 0,
            'errors': 0,
            'start_time': None,
            'existing_ids': set()
        }
        
        # Graceful shutdown handling
        self.should_stop = False
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle graceful shutdown"""
        logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        self.should_stop = True
    
    async def initialize(self):
        """Initialize all components"""
        logger.info("Initializing Shotdeck scraper...")
        
        await self.db_manager.initialize()
        await self.image_scraper.initialize()
        
        # Load existing image IDs to avoid duplicates
        self.stats['existing_ids'] = await self.db_manager.get_existing_ids()
        logger.info(f"Found {len(self.stats['existing_ids'])} existing images in database")
        
        self.stats['start_time'] = datetime.now()
    
    async def scrape_page(self, browser, page) -> List[Dict[str, Any]]:
        """Scrape a single page for images"""
        try:
            await self.rate_limiter.wait_if_needed()
            
            # Ensure we're logged in
            if not await self.login_manager.ensure_logged_in(page):
                raise Exception("Failed to maintain login session")
            
            # Extract image data from current page
            image_data = await self.image_scraper.extract_image_data(page)
            
            # Filter out existing images
            new_images = []
            for img in image_data:
                if img['shotdeck_id'] not in self.stats['existing_ids']:
                    new_images.append(img)
                    self.stats['existing_ids'].add(img['shotdeck_id'])
            
            logger.info(f"Found {len(new_images)} new images on current page")
            
            # Get detailed information for each new image
            detailed_images = []
            for img_data in new_images:
                if self.should_stop:
                    break
                
                try:
                    # Get additional metadata from detail page
                    detailed_info = await self.image_scraper.get_detailed_image_info(
                        page, img_data['shotdeck_id']
                    )
                    
                    # Merge data
                    img_data.update(detailed_info)
                    detailed_images.append(img_data)
                    
                    # Save to database immediately
                    await self.db_manager.save_image_record(img_data)
                    
                    await asyncio.sleep(self.config.request_delay)
                    
                except Exception as e:
                    logger.error(f"Error processing image {img_data['shotdeck_id']}: {e}")
                    self.rate_limiter.record_error("detail_extraction")
                    continue
            
            self.stats['images_found'] += len(detailed_images)
            self.rate_limiter.record_success()
            
            return detailed_images
            
        except Exception as e:
            logger.error(f"Error scraping page: {e}")
            self.rate_limiter.record_error("page_scraping")
            self.stats['errors'] += 1
            return []
    
    async def download_images_batch(self, image_data_list: List[Dict[str, Any]]):
        """Download images in batches"""
        if not self.config.download_images:
            return
        
        download_tasks = []
        for img_data in image_data_list:
            if self.should_stop:
                break
            
            task = self.download_single_image(img_data)
            download_tasks.append(task)
        
        if download_tasks:
            results = await asyncio.gather(*download_tasks, return_exceptions=True)
            
            # Process results
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error(f"Download failed: {result}")
                elif result:
                    self.stats['images_downloaded'] += 1
                    # Update database with local path
                    await self.db_manager.update_download_status(
                        image_data_list[i]['shotdeck_id'], 
                        result, 
                        True
                    )
    
    async def download_single_image(self, img_data: Dict[str, Any]) -> Optional[str]:
        """Download a single image"""
        try:
            local_path = await self.image_scraper.download_image(
                img_data['image_url'], 
                img_data['shotdeck_id']
            )
            return local_path
        except Exception as e:
            logger.error(f"Failed to download {img_data['shotdeck_id']}: {e}")
            await self.db_manager.update_download_status(
                img_data['shotdeck_id'], 
                None, 
                False
            )
            return None
    
    async def scrape_all_pages(self):
        """Main scraping loop"""
        async with async_playwright() as playwright:
            await self.browser_pool.initialize(playwright)
            
            try:
                # Get initial page to determine total pages
                browser, page = await self.browser_pool.get_page()
                
                await page.goto(f"{self.config.base_url}/welcome/login", wait_until='networkidle')
                
                # Login on the first page
                if not await self.login_manager.login(page):
                    raise Exception("Failed to login to Shotdeck")
                
                await page.goto(self.config.browse_url, wait_until='networkidle')
                
                # Determine total pages
                logger.info("total")
                total_pages = await self.pagination_handler.scrap_images(page)
                if total_pages:
                    logger.info(f"Detected {total_pages} total pages to scrape")
                else:
                    logger.warning("Could not determine total pages, will scrape until no more pages")
                
                await self.browser_pool.return_page((browser, page))
                
                # Main scraping loop
                current_page = 1
                consecutive_failures = 0
                max_consecutive_failures = 5
                
                while not self.should_stop and consecutive_failures < max_consecutive_failures:
                    try:
                        # Get available page from pool
                        browser, page = await self.browser_pool.get_page()
                        
                        # Navigate to current page
                        if current_page > 1:
                            success = await self.pagination_handler.navigate_to_page(page, current_page)
                            if not success:
                                logger.error(f"Failed to navigate to page {current_page}")
                                consecutive_failures += 1
                                await self.browser_pool.return_page((browser, page))
                                continue
                        
                        # Scrape current page
                        logger.info(f"Scraping page {current_page}...")
                        image_data = await self.scrape_page(browser, page)
                        
                        if image_data:
                            # Download images in batch
                            await self.download_images_batch(image_data)
                            consecutive_failures = 0
                        else:
                            consecutive_failures += 1
                        
                        self.stats['pages_scraped'] += 1
                        
                        # Check if we should continue
                        has_next = await self.pagination_handler.has_next_page(page)
                        await self.browser_pool.return_page((browser, page))
                        
                        if not has_next:
                            logger.info("No more pages to scrape")
                            break
                        
                        current_page += 1
                        
                        # Print progress
                        if current_page % 10 == 0:
                            await self.print_progress()
                        
                    except Exception as e:
                        logger.error(f"Error on page {current_page}: {e}")
                        consecutive_failures += 1
                        self.stats['errors'] += 1
                        
                        # Wait before retrying
                        await asyncio.sleep(5)
                
                if consecutive_failures >= max_consecutive_failures:
                    logger.error("Too many consecutive failures, stopping scraper")
                
            finally:
                await self.browser_pool.close_all()
    
    async def print_progress(self):
        """Print current progress statistics"""
        elapsed = datetime.now() - self.stats['start_time']
        
        logger.info(f"""
        === SCRAPING PROGRESS ===
        Pages scraped: {self.stats['pages_scraped']}
        Images found: {self.stats['images_found']}
        Images downloaded: {self.stats['images_downloaded']}
        Errors: {self.stats['errors']}
        Elapsed time: {elapsed}
        Rate: {self.stats['images_found'] / elapsed.total_seconds() * 60:.1f} images/minute
        ========================
        """)
    
    async def cleanup(self):
        """Cleanup resources"""
        logger.info("Cleaning up resources...")
        
        await self.image_scraper.close()
        await self.db_manager.close()
        
        # Final statistics
        await self.print_progress()
        
        logger.info("Scraping completed!")

async def main():
    """Main entry point"""
    # Load configuration
    config = ScrapingConfig()
    
    # Validate required settings
    if not config.email or not config.password:
        logger.error("Please set SHOTDECK_EMAIL and SHOTDECK_PASSWORD environment variables")
        return
    
    # Create scraper instance
    scraper = ShotdeckScraper(config)
    
    try:
        # Initialize and start scraping
        await scraper.initialize()
        await scraper.scrape_all_pages()
        
    except KeyboardInterrupt:
        logger.info("Scraping interrupted by user")
    except Exception as e:
        logger.error(f"Scraping failed: {e}")
    finally:
        await scraper.cleanup()

if __name__ == "__main__":
    asyncio.run(main())