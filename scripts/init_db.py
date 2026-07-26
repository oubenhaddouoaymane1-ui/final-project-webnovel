"""Initialize the database"""
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database import init_database

def main():
    """Initialize database"""
    print("Initializing database...")
    
    # Create database directory
    db_path = Path("./database")
    db_path.mkdir(exist_ok=True)
    
    # Initialize database
    db = init_database(db_path)
    
    print("Database initialized successfully!")
    print(f"Database location: {db_path / 'pipeline.db'}")

if __name__ == "__main__":
    main()