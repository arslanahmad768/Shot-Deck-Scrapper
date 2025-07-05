import asyncio
import sqlite3
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, JSON
from datetime import datetime
from typing import List, Dict, Any
import json
import aiosqlite

Base = declarative_base()

class ImageRecord(Base):
    __tablename__ = 'images'
    
    id = Column(Integer, primary_key=True)
    shotdeck_id = Column(String(100), unique=True, index=True)
    title = Column(String(500))
    description = Column(Text)
    image_url = Column(String(1000))
    thumbnail_url = Column(String(1000))
    local_path = Column(String(1000))
    tags = Column(JSON)
    image_metadata = Column(JSON)  # Renamed from 'metadata' to avoid conflict
    film_title = Column(String(500))
    director = Column(String(200))
    cinematographer = Column(String(200))
    year = Column(Integer)
    genre = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)
    downloaded = Column(Boolean, default=False)
    download_attempts = Column(Integer, default=0)

class DatabaseManager:
    def __init__(self, database_url: str):
        self.database_url = database_url
        self.engine = None
        self.async_session = None
        self.is_sqlite = database_url.startswith('sqlite')
    
    async def initialize(self):
        """Initialize database connection and create tables"""
        if self.is_sqlite:
            # For SQLite, use aiosqlite
            db_path = self.database_url.replace('sqlite:///', '').replace('sqlite:', '')
            self.db_path = db_path
            await self._create_sqlite_tables()
        else:
            # For PostgreSQL
            self.engine = create_async_engine(
                self.database_url,
                echo=False,
                pool_size=10,
                max_overflow=20
            )
            
            self.async_session = sessionmaker(
                self.engine, class_=AsyncSession, expire_on_commit=False
            )
            
            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
    
    async def _create_sqlite_tables(self):
        """Create SQLite tables manually"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                CREATE TABLE IF NOT EXISTS images (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    shotdeck_id TEXT UNIQUE,
                    title TEXT,
                    description TEXT,
                    image_url TEXT,
                    thumbnail_url TEXT,
                    local_path TEXT,
                    tags TEXT,
                    image_metadata TEXT,
                    film_title TEXT,
                    director TEXT,
                    cinematographer TEXT,
                    year INTEGER,
                    genre TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    downloaded BOOLEAN DEFAULT 0,
                    download_attempts INTEGER DEFAULT 0
                )
            ''')
            await db.execute('CREATE INDEX IF NOT EXISTS idx_shotdeck_id ON images(shotdeck_id)')
            await db.commit()
    
    async def save_image_record(self, image_data: Dict[str, Any]) -> bool:
        """Save image record to database"""
        try:
            if self.is_sqlite:
                return await self._save_sqlite_record(image_data)
            else:
                return await self._save_postgres_record(image_data)
        except Exception as e:
            print(f"Error saving record: {e}")
            return False
    
    async def _save_sqlite_record(self, image_data: Dict[str, Any]) -> bool:
        """Save record to SQLite"""
        try:
            # Convert lists/dicts to JSON strings
            tags_json = json.dumps(image_data.get('tags', []))
            metadata_json = json.dumps(image_data.get('image_metadata', {}))
            
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute('''
                    INSERT OR IGNORE INTO images 
                    (shotdeck_id, title, description, image_url, thumbnail_url, 
                     tags, image_metadata, film_title, director, cinematographer, 
                     year, genre, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    image_data.get('shotdeck_id'),
                    image_data.get('title'),
                    image_data.get('description'),
                    image_data.get('image_url'),
                    image_data.get('thumbnail_url'),
                    tags_json,
                    metadata_json,
                    image_data.get('film_title'),
                    image_data.get('director'),
                    image_data.get('cinematographer'),
                    image_data.get('year'),
                    image_data.get('genre'),
                    datetime.utcnow().isoformat()
                ))
                await db.commit()
                return True
        except Exception as e:
            print(f"SQLite save error: {e}")
            return False
    
    async def _save_postgres_record(self, image_data: Dict[str, Any]) -> bool:
        """Save record to PostgreSQL"""
        try:
            async with self.async_session() as session:
                # Rename metadata key to avoid conflict
                data_copy = image_data.copy()
                if 'metadata' in data_copy:
                    data_copy['image_metadata'] = data_copy.pop('metadata')
                
                record = ImageRecord(**data_copy)
                session.add(record)
                await session.commit()
                return True
        except Exception as e:
            print(f"PostgreSQL save error: {e}")
            return False
    
    async def get_existing_ids(self) -> set:
        """Get all existing shotdeck IDs to avoid duplicates"""
        try:
            if self.is_sqlite:
                async with aiosqlite.connect(self.db_path) as db:
                    cursor = await db.execute("SELECT shotdeck_id FROM images")
                    rows = await cursor.fetchall()
                    return {row[0] for row in rows if row[0]}
            else:
                async with self.async_session() as session:
                    result = await session.execute("SELECT shotdeck_id FROM images")
                    return {row[0] for row in result.fetchall() if row[0]}
        except Exception as e:
            print(f"Error fetching existing IDs: {e}")
            return set()
    
    async def update_download_status(self, shotdeck_id: str, local_path: str = None, success: bool = True):
        """Update download status for an image"""
        try:
            if self.is_sqlite:
                async with aiosqlite.connect(self.db_path) as db:
                    await db.execute('''
                        UPDATE images 
                        SET downloaded = ?, local_path = ?, download_attempts = download_attempts + 1
                        WHERE shotdeck_id = ?
                    ''', (1 if success else 0, local_path, shotdeck_id))
                    await db.commit()
            else:
                async with self.async_session() as session:
                    query = """
                        UPDATE images 
                        SET downloaded = $1, local_path = $2, download_attempts = download_attempts + 1
                        WHERE shotdeck_id = $3
                    """
                    await session.execute(query, success, local_path, shotdeck_id)
                    await session.commit()
        except Exception as e:
            print(f"Error updating download status: {e}")
    
    async def get_stats(self) -> Dict[str, int]:
        """Get database statistics"""
        try:
            if self.is_sqlite:
                async with aiosqlite.connect(self.db_path) as db:
                    cursor = await db.execute("SELECT COUNT(*) FROM images")
                    total = (await cursor.fetchone())[0]
                    
                    cursor = await db.execute("SELECT COUNT(*) FROM images WHERE downloaded = 1")
                    downloaded = (await cursor.fetchone())[0]
                    
                    return {'total': total, 'downloaded': downloaded}
            else:
                async with self.async_session() as session:
                    total_result = await session.execute("SELECT COUNT(*) FROM images")
                    total = total_result.scalar()
                    
                    downloaded_result = await session.execute("SELECT COUNT(*) FROM images WHERE downloaded = true")
                    downloaded = downloaded_result.scalar()
                    
                    return {'total': total, 'downloaded': downloaded}
        except Exception as e:
            print(f"Error getting stats: {e}")
            return {'total': 0, 'downloaded': 0}
    
    async def close(self):
        """Close database connection"""
        if self.engine:
            await self.engine.dispose()