
import os
import json
from contextlib import contextmanager
from sqlalchemy import create_engine, Column, Integer, Text, String, ForeignKey, Table
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

# Use SQLite database by default if DATABASE_URL is not set
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./api_inspector.db")

# For SQLite, we need to set check_same_thread=False for SQLite in-memory databases
if DATABASE_URL.startswith('sqlite'):
    engine = create_engine(
        DATABASE_URL, connect_args={"check_same_thread": False}, pool_pre_ping=True
    )
else:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Association table for many-to-many relationship between API and Tag
api_tags = Table('api_tags', Base.metadata,
    Column('api_id', Integer, ForeignKey('api.id'), primary_key=True),
    Column('tag_id', Integer, ForeignKey('tags.id'), primary_key=True)
)

class API(Base):
    __tablename__ = "api"
    id = Column(Integer, primary_key=True, autoincrement=True)
    api = Column(Text, nullable=False)
    response = Column(Text, nullable=False)

    mappings = relationship("Mapper", back_populates="api")
    tags = relationship("Tag", secondary=api_tags, backref="apis")


class Tag(Base):
    __tablename__ = "tags"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), unique=True, nullable=False)


class Data(Base):
    __tablename__ = "data"
    id = Column(Integer, primary_key=True, autoincrement=True)
    mode = Column(String, nullable=False)
    keys = Column(Text, nullable=False)
    mapping = Column(Text, nullable=False)

    mappings = relationship("Mapper", back_populates="data")


class Mapper(Base):
    __tablename__ = "mapper"
    api_id = Column(Integer, ForeignKey("api.id"), primary_key=True)
    data_id = Column(Integer, ForeignKey("data.id"), primary_key=True)

    api = relationship("API", back_populates="mappings")
    data = relationship("Data", back_populates="mappings")

@contextmanager
def db_session():
    """Create a new database session with proper cleanup."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
