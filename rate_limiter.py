import asyncio
import time
from typing import Dict, Any
from collections import deque
import logging

logger = logging.getLogger(__name__)

class RateLimiter:
    def __init__(self, max_requests_per_minute: int = 60, backoff_factor: float = 2.0):
        self.max_requests_per_minute = max_requests_per_minute
        self.backoff_factor = backoff_factor
        self.request_times = deque()
        self.consecutive_errors = 0
        self.base_delay = 60 / max_requests_per_minute  # Base delay between requests
        
        # Adaptive rate limiting
        self.success_streak = 0
        self.current_delay = self.base_delay
        
        self._lock = asyncio.Lock()
    
    async def wait_if_needed(self):
        """Wait if we're hitting rate limits"""
        async with self._lock:
            now = time.time()
            
            # Remove old request times (older than 1 minute)
            while self.request_times and now - self.request_times[0] > 60:
                self.request_times.popleft()
            
            # Check if we're at the limit
            if len(self.request_times) >= self.max_requests_per_minute:
                sleep_time = 60 - (now - self.request_times[0])
                if sleep_time > 0:
                    logger.info(f"Rate limit reached, sleeping for {sleep_time:.2f} seconds")
                    await asyncio.sleep(sleep_time)
            
            # Apply adaptive delay
            if self.current_delay > 0:
                await asyncio.sleep(self.current_delay)
            
            # Record this request
            self.request_times.append(now)
    
    def record_success(self):
        """Record a successful request"""
        self.consecutive_errors = 0
        self.success_streak += 1
        
        # Gradually decrease delay on successful requests
        if self.success_streak > 10:
            self.current_delay = max(self.base_delay, self.current_delay * 0.9)
            self.success_streak = 0
    
    def record_error(self, error_type: str = "unknown"):
        """Record an error and increase delay"""
        self.consecutive_errors += 1
        self.success_streak = 0
        
        # Increase delay exponentially
        self.current_delay = min(
            self.base_delay * (self.backoff_factor ** self.consecutive_errors),
            30  # Max 30 seconds delay
        )
        
        logger.warning(f"Error recorded ({error_type}), new delay: {self.current_delay:.2f}s")
    
    def reset_rate_limiting(self):
        """Reset rate limiting state"""
        self.consecutive_errors = 0
        self.success_streak = 0
        self.current_delay = self.base_delay
        self.request_times.clear()
        logger.info("Rate limiting reset")

class BrowserPool:
    def __init__(self, pool_size: int = 3, pages_per_browser: int = 2):
        self.pool_size = pool_size
        self.pages_per_browser = pages_per_browser
        self.browsers = []
        self.page_pools = []
        self.available_pages = asyncio.Queue()
        self.rate_limiter = RateLimiter()
    
    async def initialize(self, playwright):
        """Initialize browser pool"""
        for i in range(self.pool_size):
            browser = await playwright.chromium.launch(
                headless=False,
                args=[
                    '--no-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-blink-features=AutomationControlled',
                    '--disable-extensions',
                    '--disable-plugins',
                ]
            )
            
            context = await browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            )
            
            # Create multiple pages per browser
            pages = []
            for j in range(self.pages_per_browser):
                page = await context.new_page()
                pages.append(page)
                await self.available_pages.put((browser, page))
            
            self.browsers.append(browser)
            self.page_pools.append((context, pages))
    
    async def get_page(self):
        """Get an available page from the pool"""
        return await self.available_pages.get()
    
    async def return_page(self, browser_page_tuple):
        """Return a page to the pool"""
        await self.available_pages.put(browser_page_tuple)
    
    async def close_all(self):
        """Close all browsers in the pool"""
        for browser in self.browsers:
            await browser.close()
        self.browsers.clear()
        self.page_pools.clear()