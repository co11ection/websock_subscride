from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = "sqlite+aiosqlite:///./test.db"  # Use an async-compatible URL

engine = create_async_engine(DATABASE_URL, echo=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, class_=AsyncSession)
Base = declarative_base()


from sqlalchemy import Column, Integer, String, Table, ForeignKey, Boolean
from sqlalchemy.orm import relationship

from pydantic import BaseModel

class SubscriptionRequest(BaseModel):
    subscriber_username: str
    subscribe_to_username: str



class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True)

    subscribed_to = relationship(
        'User', 
        secondary='subscriptions',
        primaryjoin='User.id==subscriptions.c.subscriber_id',
        secondaryjoin='User.id==subscriptions.c.subscribed_to_id',
        backref='subscribers'
    )

# Subscription table for many-to-many relationship
subscriptions = Table(
    'subscriptions', Base.metadata,
    Column('subscriber_id', ForeignKey('users.id'), primary_key=True),
    Column('subscribed_to_id', ForeignKey('users.id'), primary_key=True),
    Column('is_confirmed', Boolean, default=False)
)

async def create_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)