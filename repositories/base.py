from typing import TypeVar, Generic, Type, Optional, List
from sqlalchemy.orm import Session
from datetime import datetime
from database.models import Base

T = TypeVar("T", bound=Base)

class BaseRepository(Generic[T]):
    def __init__(self, model: Type[T], db: Session):
        self.model = model
        self.db = db
    
    def get_by_id(self, id: int) -> Optional[T]:
        """Get a record by ID"""
        return self.db.query(self.model).filter(self.model.id == id).first()
    
    def get_all(self) -> List[T]:
        """Get all records"""
        return self.db.query(self.model).all()
    
    def create(self, data: dict) -> T:
        """Create a new record"""
        # Add timestamps if model has them
        if hasattr(self.model, 'created_at'):
            data['created_at'] = datetime.utcnow()
        if hasattr(self.model, 'updated_at'):
            data['updated_at'] = datetime.utcnow()
            
        # Create model instance
        db_item = self.model(**data)
        self.db.add(db_item)
        self.db.commit()
        self.db.refresh(db_item)
        return db_item
    
    def update(self, id: int, data: dict) -> Optional[T]:
        """Update a record by ID"""
        db_item = self.get_by_id(id)
        if not db_item:
            return None
            
        # Update timestamps if model has them
        if hasattr(self.model, 'updated_at'):
            data['updated_at'] = datetime.utcnow()
            
        # Update fields
        for key, value in data.items():
            setattr(db_item, key, value)
            
        self.db.commit()
        self.db.refresh(db_item)
        return db_item
    
    def delete(self, id: int) -> bool:
        """Delete a record by ID"""
        db_item = self.get_by_id(id)
        if not db_item:
            return False
            
        self.db.delete(db_item)
        self.db.commit()
        return True
