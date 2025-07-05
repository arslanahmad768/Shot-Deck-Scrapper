import asyncio
from playwright.async_api import Page
from typing import List, Optional
import logging
import pandas as pd
import re
import time

CSV_FILE = "image_metadata.csv"
logger = logging.getLogger(__name__)

class PaginationHandler:
    def __init__(self, max_pages: Optional[int] = None):
        self.max_pages = max_pages
        self.current_page = 1
        self.total_pages = None

    
    async def scrap_images(self, page: Page):
        """Scrap images from the page"""
        try:
            print("Scrapping.....")
            all_data = []
            seen_columns = set()
            image_containers = await page.query_selector_all('div.outerimage.jg-entry.entry-visible')
            print("total container...", len(image_containers))
            time.sleep(5)

            for container in image_containers:
                image_data = {}

                # Extract image src
                img = await container.query_selector('img.still')
                if img:
                    src = await img.get_attribute('src')
                    if src:
                        image_data["Image URL"] = src

                # Click image
                link = await container.query_selector('a.gallerythumb')
                if link:
                    await link.click()
                    await page.wait_for_timeout(1000)

                    # Extract metadata
                    metadata = await self.extract_metadata_from_modal(page)
                    time.sleep(5)
                    image_data.update(metadata)
                    seen_columns.update(image_data.keys())

                    # Close modal
                    try:
                        close_btn = await page.wait_for_selector('#shotModal button.close', timeout=3000)
                        await close_btn.click()
                        await page.wait_for_timeout(500)
                    except Exception as e:
                        print("Error closing modal:", e)

                    all_data.append(image_data)
                    print("All data...", len(all_data))
                    time.sleep(5)


            # Save to CSV
            df = pd.DataFrame(all_data)
            df.to_csv(CSV_FILE, index=False)
            print(f"Saved {len(df)} records to {CSV_FILE}")


        
        except Exception as e:
            logger.error(f"Error detecting total pages: {e}")
        return None
    
    async def extract_metadata_from_modal(self, page):
        metadata = {}
        try:
            # Wait for modal and metadata block
            await page.wait_for_selector("#shotModal .detail-group", timeout=3000)
            detail_groups = await page.query_selector_all("#shotModal .detail-group")

            for group in detail_groups:
                label_elem = await group.query_selector("p.detail-type")
                value_elem = await group.query_selector("div.details")

                if label_elem and value_elem:
                    label = (await label_elem.inner_text()).strip(":").strip()
                    value_links = await value_elem.query_selector_all("a")
                    if value_links:
                        values = [await a.inner_text() for a in value_links]
                        metadata[label] = ", ".join(values)
                    else:
                        span = await value_elem.query_selector("span")
                        metadata[label] = await span.inner_text() if span else await value_elem.inner_text()
        except Exception as e:
            print("Error extracting metadata:", e)
        return metadata
                
    
    async def get_total_pages(self, page: Page) -> Optional[int]:
        """Detect total number of pages"""
        try:
            # Common pagination selectors
            pagination_selectors = [
                '.pagination .page-item:last-child a',
                '.pagination a:last-child',
                '.pager .last',
                '.page-numbers:last-child',
                '[data-total-pages]'
            ]
            
            for selector in pagination_selectors:
                element = await page.query_selector(selector)
                if element:
                    # Try to get page number from text
                    text = await element.text_content()
                    if text and text.isdigit():
                        self.total_pages = int(text)
                        return self.total_pages
                    
                    # Try to get from href
                    href = await element.get_attribute('href')
                    if href:
                        page_match = re.search(r'page[=\/](\d+)', href)
                        if page_match:
                            self.total_pages = int(page_match.group(1))
                            return self.total_pages
            
            # Try to extract from JavaScript or page source
            total_from_js = await page.evaluate("""
                () => {
                    // Look for common pagination variables
                    if (window.totalPages) return window.totalPages;
                    if (window.pagination && window.pagination.total) return window.pagination.total;
                    
                    // Look in the DOM for page indicators
                    const pageInfo = document.querySelector('.page-info, .pagination-info');
                    if (pageInfo) {
                        const match = pageInfo.textContent.match(/of\\s+(\\d+)/);
                        if (match) return parseInt(match[1]);
                    }
                    
                    return null;
                }
            """)
            
            if total_from_js:
                self.total_pages = total_from_js
                return self.total_pages
                
        except Exception as e:
            logger.error(f"Error detecting total pages: {e}")
        
        return None
    
    async def navigate_to_page(self, page: Page, page_number: int) -> bool:
        """Navigate to a specific page number"""
        try:
            # Construct URL with page parameter
            current_url = page.url
            
            # Common URL patterns for pagination
            if '?' in current_url:
                base_url = current_url.split('?')[0]
                new_url = f"{base_url}?page={page_number}"
            else:
                new_url = f"{current_url}?page={page_number}"
            
            # Alternative URL patterns
            if '/page/' in current_url:
                new_url = re.sub(r'/page/\d+', f'/page/{page_number}', current_url)
            
            await page.goto(new_url, wait_until='networkidle')
            
            # Verify we're on the correct page
            await page.wait_for_selector('.image-card, .still-card, .grid-item', timeout=10000)
            
            self.current_page = page_number
            logger.info(f"Navigated to page {page_number}")
            return True
            
        except Exception as e:
            logger.error(f"Error navigating to page {page_number}: {e}")
            return False
    
    async def has_next_page(self, page: Page) -> bool:
        """Check if there's a next page available"""
        try:
            # Check for next button
            next_selectors = [
                '.pagination .next:not(.disabled)',
                '.pagination .page-item:last-child:not(.disabled) a',
                '.pager .next:not(.disabled)',
                'a[rel="next"]'
            ]
            
            for selector in next_selectors:
                element = await page.query_selector(selector)
                if element:
                    # Check if it's not disabled
                    classes = await element.get_attribute('class') or ''
                    if 'disabled' not in classes:
                        return True
            
            # Check if current page is less than total pages
            if self.total_pages and self.current_page < self.total_pages:
                return True
            
            # Check for load more functionality
            load_more = await page.query_selector('.load-more, .show-more, [data-load-more]')
            if load_more:
                is_visible = await load_more.is_visible()
                return is_visible
                
        except Exception as e:
            logger.error(f"Error checking for next page: {e}")
        
        return False
    
    async def go_to_next_page(self, page: Page) -> bool:
        """Navigate to the next page"""
        try:
            # Try clicking next button first
            next_selectors = [
                '.pagination .next:not(.disabled) a',
                '.pagination .page-item:last-child:not(.disabled) a',
                '.pager .next:not(.disabled) a',
                'a[rel="next"]'
            ]
            
            for selector in next_selectors:
                element = await page.query_selector(selector)
                if element:
                    await element.click()
                    await page.wait_for_load_state('networkidle')
                    self.current_page += 1
                    logger.info(f"Clicked next button, now on page {self.current_page}")
                    return True
            
            # Try load more button
            load_more = await page.query_selector('.load-more, .show-more, [data-load-more]')
            if load_more and await load_more.is_visible():
                await load_more.click()
                await page.wait_for_timeout(2000)  # Wait for content to load
                logger.info("Clicked load more button")
                return True
            
            # Fallback: navigate to next page number
            return await self.navigate_to_page(page, self.current_page + 1)
            
        except Exception as e:
            logger.error(f"Error going to next page: {e}")
            return False
    
    def should_continue(self) -> bool:
        """Check if we should continue scraping based on max_pages setting"""
        if self.max_pages is None:
            return True
        return self.current_page <= self.max_pages