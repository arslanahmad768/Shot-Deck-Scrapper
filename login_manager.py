import asyncio
import time
from playwright.async_api import Page, Browser
from typing import Optional
import logging

logger = logging.getLogger(__name__)

class LoginManager:
    def __init__(self, email: str, password: str):
        self.email = email
        self.password = password
        self.is_logged_in = False
        self.session_cookies = None
    
    async def login(self, page: Page) -> bool:
        """Perform login on Shotdeck"""
        try:
            # Navigate to login page
            await page.goto('https://shotdeck.com/welcome/login')
            await page.wait_for_load_state('networkidle')
            
            # Wait for login form
            await page.wait_for_selector('input[type="email"], input[name="email"]', timeout=10000)
            
            # Fill in credentials
            email_selector = 'input[type="email"], input[name="email"]'
            password_selector = 'input[type="password"], input[name="password"]'
            
            await page.fill(email_selector, self.email)
            await page.fill(password_selector, self.password)
            
            # Submit form
            submit_button = 'button[type="submit"], input[type="submit"], .login-button'
            await page.click(submit_button)
            
            # Wait for navigation or success indicator
            try:
                time.sleep(10)
                logger.info("before...")
                # await page.wait_for_url('**/browse/**', timeout=15000)
                logger.info("after login..")
                self.is_logged_in = True
                self.session_cookies = await page.context.cookies()
                logger.info("Successfully logged in to Shotdeck")
                return True
            except:
                # Check for error messages
                error_elements = await page.query_selector_all('.error, .alert-danger, .login-error')
                if error_elements:
                    error_text = await error_elements[0].text_content()
                    logger.error(f"Login failed: {error_text}")
                else:
                    logger.error("Login failed: Unknown error")
                return False
                
        except Exception as e:
            logger.error(f"Login error: {e}")
            return False
    
    async def ensure_logged_in(self, page: Page) -> bool:
        """Ensure the page is logged in, attempt login if not"""
        if not self.is_logged_in:
            return await self.login(page)
        
        # Check if still logged in by looking for user-specific elements
        try:
            await page.goto('https://shotdeck.com/browse/stills', wait_until='networkidle')
            
            # Look for login indicators
            user_elements = await page.query_selector_all('.user-menu, .profile, .logout')
            if user_elements:
                return True
            else:
                # Try to re-login
                logger.info("Session expired, attempting re-login")
                self.is_logged_in = False
                return await self.login(page)
                
        except Exception as e:
            logger.error(f"Error checking login status: {e}")
            return await self.login(page)
    
    async def apply_session_cookies(self, context) -> bool:
        """Apply saved session cookies to a new context"""
        if self.session_cookies:
            try:
                await context.add_cookies(self.session_cookies)
                return True
            except Exception as e:
                logger.error(f"Error applying cookies: {e}")
                return False
        return False