import asyncio
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        # Launch the browser (headless by default)
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        # Navigate to a webpage
        await page.goto("https://shotdeck.com/welcome/login")

        # Take a screenshot
        await page.screenshot(path="example_screenshot.png")
        print("Screenshot saved as example_screenshot.png")

        # Close the browser
        await browser.close()

# Run the script
asyncio.run(run())
