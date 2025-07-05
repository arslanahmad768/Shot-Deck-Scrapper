import asyncio
import aiohttp
import aiofiles
import os
from pathlib import Path
from playwright.async_api import Page
from typing import List, Dict, Any, Optional
import hashlib
import mimetypes
from urllib.parse import urlparse, urljoin
import logging
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

class ImageScraper:
    def __init__(self, images_directory: str, concurrent_downloads: int = 10):
        self.images_directory = Path(images_directory)
        self.images_directory.mkdir(parents=True, exist_ok=True)
        self.concurrent_downloads = concurrent_downloads
        self.semaphore = asyncio.Semaphore(concurrent_downloads)
        self.session = None
    
    async def initialize(self):
        """Initialize aiohttp session for downloads"""
        connector = aiohttp.TCPConnector(limit=50, limit_per_host=10)
        timeout = aiohttp.ClientTimeout(total=30, connect=10)
        
        self.session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
        )
    
    async def extract_image_data(self, page: Page) -> List[Dict[str, Any]]:
        """Extract image data from the current browse page"""
        try:
            # Wait for images to load
            await page.wait_for_selector('.image-card, .still-card, .grid-item', timeout=10000)
            
            # Execute JavaScript to extract image data
            image_data = await page.evaluate("""
                () => {
                    const images = [];
                    
                    // Common selectors for image containers
                    const containers = document.querySelectorAll('.image-card, .still-card, .grid-item, .photo-item');
                    
                    containers.forEach((container, index) => {
                        try {
                            const img = container.querySelector('img');
                            const link = container.querySelector('a');
                            
                            if (img && img.src) {
                                const data = {
                                    shotdeck_id: link ? link.href.split('/').pop() : `unknown_${index}`,
                                    image_url: img.src,
                                    thumbnail_url: img.src,
                                    title: img.alt || container.querySelector('.title, .caption')?.textContent || '',
                                    description: container.querySelector('.description, .info')?.textContent || '',
                                    tags: [],
                                    metadata: {},
                                    film_title: '',
                                    director: '',
                                    cinematographer: '',
                                    year: null,
                                    genre: ''
                                };
                                
                                // Extract tags if available
                                const tagElements = container.querySelectorAll('.tag, .label, .category');
                                tagElements.forEach(tag => {
                                    if (tag.textContent.trim()) {
                                        data.tags.push(tag.textContent.trim());
                                    }
                                });
                                
                                // Extract metadata from data attributes
                                for (const attr of container.attributes) {
                                    if (attr.name.startsWith('data-')) {
                                        data.metadata[attr.name.replace('data-', '')] = attr.value;
                                    }
                                }
                                
                                // Look for film information
                                const filmInfo = container.querySelector('.film-info, .movie-info');
                                if (filmInfo) {
                                    data.film_title = filmInfo.querySelector('.title')?.textContent || '';
                                    data.director = filmInfo.querySelector('.director')?.textContent || '';
                                    data.year = parseInt(filmInfo.querySelector('.year')?.textContent) || null;
                                }
                                
                                images.push(data);
                            }
                        } catch (e) {
                            console.log('Error extracting image data:', e);
                        }
                    });
                    
                    return images;
                }
            """)
            
            logger.info(f"Extracted {len(image_data)} images from current page")
            return image_data
            
        except Exception as e:
            logger.error(f"Error extracting image data: {e}")
            return []
    
    async def get_detailed_image_info(self, page: Page, shotdeck_id: str) -> Dict[str, Any]:
        """Navigate to image detail page and extract additional metadata"""
        try:
            detail_url = f"https://shotdeck.com/stills/{shotdeck_id}"
            await page.goto(detail_url, wait_until='networkidle')
            
            # Extract detailed information
            detail_data = await page.evaluate("""
                () => {
                    const data = {};
                    
                    // Extract high-resolution image URL
                    const mainImg = document.querySelector('.main-image img, .detail-image img');
                    if (mainImg) {
                        data.image_url = mainImg.src;
                    }
                    
                    // Extract comprehensive metadata
                    const metadataElements = document.querySelectorAll('.metadata dd, .info-item, .detail-item');
                    metadataElements.forEach(el => {
                        const label = el.previousElementSibling?.textContent?.toLowerCase() || '';
                        const value = el.textContent?.trim();
                        if (label && value) {
                            data[label.replace(':', '').trim()] = value;
                        }
                    });
                    
                    // Extract tags
                    const tags = [];
                    document.querySelectorAll('.tag, .keyword, .label').forEach(tag => {
                        tags.push(tag.textContent.trim());
                    });
                    data.tags = tags;
                    
                    return data;
                }
            """)
            
            return detail_data
            
        except Exception as e:
            logger.error(f"Error getting detailed info for {shotdeck_id}: {e}")
            return {}
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    async def download_image(self, image_url: str, shotdeck_id: str) -> Optional[str]:
        """Download image with retry logic"""
        async with self.semaphore:
            try:
                if not self.session:
                    await self.initialize()
                
                # Generate a safe filename
                url_hash = hashlib.md5(image_url.encode()).hexdigest()[:10]
                parsed_url = urlparse(image_url)
                file_extension = os.path.splitext(parsed_url.path)[1] or '.jpg'
                filename = f"{shotdeck_id}_{url_hash}{file_extension}"
                filepath = self.images_directory / filename
                
                # Skip if already downloaded
                if filepath.exists():
                    logger.debug(f"Image already exists: {filename}")
                    return str(filepath)
                
                # Download image
                async with self.session.get(image_url) as response:
                    if response.status == 200:
                        content = await response.read()
                        
                        async with aiofiles.open(filepath, 'wb') as f:
                            await f.write(content)
                        
                        logger.info(f"Downloaded: {filename}")
                        return str(filepath)
                    else:
                        logger.error(f"Failed to download {image_url}: HTTP {response.status}")
                        return None
                        
            except Exception as e:
                logger.error(f"Error downloading {image_url}: {e}")
                raise
    
    async def close(self):
        """Close aiohttp session"""
        if self.session:
            await self.session.close()