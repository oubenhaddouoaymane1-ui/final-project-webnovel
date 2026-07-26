"""Database initialization and management"""
from pathlib import Path
from typing import Optional

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session

from .models import Base

class Database:
    """Database manager"""
    
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.engine = create_engine(f"sqlite:///{db_path}/pipeline.db")
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        
    def create_tables(self):
        """Create all database tables"""
        Base.metadata.create_all(bind=self.engine)
        
    def get_session(self) -> Session:
        """Get database session"""
        return self.SessionLocal()
        
    def close(self):
        """Close database connection"""
        self.engine.dispose()

def init_database(db_path: Path) -> Database:
    """Initialize database"""
    db = Database(db_path)
    db.create_tables()
    return db