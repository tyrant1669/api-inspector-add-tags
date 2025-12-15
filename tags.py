from sqlalchemy.orm import Session
from database import SessionLocal, Tag, API

def get_or_create_tag(db: Session, name: str) -> Tag:
    tag = db.query(Tag).filter(Tag.name == name).first()
    if not tag:
        tag = Tag(name=name)
        db.add(tag)
        db.commit()
        db.refresh(tag)
    return tag

def add_tags_to_api(db: Session, api_id: int, tag_names: list[str]) -> None:
    api = db.query(API).filter(API.id == api_id).first()
    if not api:
        return
        
    for tag_name in tag_names:
        tag = get_or_create_tag(db, tag_name.strip())
        if tag not in api.tags:
            api.tags.append(tag)
    
    db.commit()

def remove_tag_from_api(db: Session, api_id: int, tag_name: str) -> None:
    api = db.query(API).filter(API.id == api_id).first()
    if not api:
        return
        
    tag = db.query(Tag).filter(Tag.name == tag_name).first()
    if tag and tag in api.tags:
        api.tags.remove(tag)
        db.commit()

def get_apis_by_tag(db: Session, tag_name: str) -> list[API]:
    return db.query(API).join(API.tags).filter(Tag.name == tag_name).all()

def get_all_tags(db: Session) -> list[Tag]:
    return db.query(Tag).all()
