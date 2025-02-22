from typing import Generic, TypeVar, Type
from sqlalchemy.orm import Session
from database.models import Base

ModelType = TypeVar("ModelType", bound=Base)

class BaseRepository(Generic[ModelType]):
    def __init__(self, model: Type[ModelType], db: Session):
        self.model = model
        self.db = db

    def get_by_id(self, id: int):
        return self.db.query(self.model).filter(self.model.id == id).first()

    def create(self, obj_in):
        db_obj = self.model(**obj_in)
        self.db.add(db_obj)
        self.db.commit()
        self.db.refresh(db_obj)
        return db_obj
