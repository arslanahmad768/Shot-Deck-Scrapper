#!/usr/bin/env python3
"""
Shotdeck Image Scraper Runner
"""

import asyncio
import os
import sys
from pathlib import Path
from main_scraper import main

def check_requirements():
    """Check if required packages are installed"""
    try:
        import playwright
        import aiohttp
        import aiofiles
        import sqlalchemy
        import tenacity
        print("✅ All required packages are installed")
        return True
    except ImportError as e:
        print(f"❌ Missing required package: {e}")
        print("\nPlease install required packages:")
        print("pip install -r requirements.txt")
        print("playwright install chromium")
        return False

def setup_environment():
    """Setup environment and check configuration"""
    # Check for .env file
    env_file = Path('.env')
    if not env_file.exists():
        print("❌ .env file not found")
        print("Please copy .env.example to .env and configure your credentials:")
        print("cp .env.example .env")
        return False
    
    # Load environment variables
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        print("Note: python-dotenv not installed, using system environment variables")
    
    # Check required environment variables
    required_vars = ['SHOTDECK_EMAIL', 'SHOTDECK_PASSWORD']
    missing_vars = []
    
    for var in required_vars:
        if not os.getenv(var):
            missing_vars.append(var)
    
    if missing_vars:
        print(f"❌ Missing required environment variables: {', '.join(missing_vars)}")
        print("Please set these in your .env file")
        return False
    
    print("✅ Environment configuration looks good")
    return True

def create_directories():
    """Create necessary directories"""
    directories = [
        'downloaded_images',
        'logs',
    ]
    
    for directory in directories:
        Path(directory).mkdir(exist_ok=True)
    
    print("✅ Created necessary directories")

if __name__ == "__main__":
    print("🚀 Starting Shotdeck Image Scraper")
    print("=" * 50)
    
    # Check requirements
    if not check_requirements():
        sys.exit(1)
    
    # Setup environment
    if not setup_environment():
        sys.exit(1)
    
    # Create directories
    create_directories()
    
    print("\n🔄 Starting scraper...")
    print("Press Ctrl+C to stop gracefully")
    print("=" * 50)
    
    # Run the scraper
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⏹️  Scraper stopped by user")
    except Exception as e:
        print(f"\n❌ Scraper failed: {e}")
        sys.exit(1)
    
    print("\n✅ Scraper completed successfully!")