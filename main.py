from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from models import SessionLocal, subscriptions, User,SubscriptionRequest, create_tables
app = FastAPI()

async def get_db():
    await create_tables()
    async with SessionLocal() as session:
        yield session

@app.get("/users/")
async def get_users(db: AsyncSession = Depends(get_db)):
    async with db as session:
        result = await session.execute(select(User))
        users = result.scalars().all()
        return {"data": [user for user in users]}

@app.post("/users/")
async def create_user(username: str, db: AsyncSession = Depends(get_db)):
    async with db as session:
        result = await session.execute(select(User).filter(User.username == username))
        db_user = result.scalars().first()
        if db_user:
            raise HTTPException(status_code=400, detail="Username already registered")
        new_user = User(username=username)
        session.add(new_user)
        await session.commit()
        return {"username": username}

class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, user_id: str):
        await websocket.accept()
        self.active_connections[user_id] = websocket

    async def disconnect(self, user_id: str):
        if user_id in self.active_connections:
            del self.active_connections[user_id]

    async def send_personal_message(self, message: str, user_id: str):
        if user_id in self.active_connections:
            await self.active_connections[user_id].send_text(message)

manager = ConnectionManager()

@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    await manager.connect(websocket, user_id)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(user_id)



@app.post("/subscribe/")
async def subscribe(request: SubscriptionRequest, db: AsyncSession = Depends(get_db)):
    async with db as session:
        subscriber_query =  select(User).filter(User.username == request.subscriber_username)
        subscribe_to_query =  select(User).filter(User.username == request.subscribe_to_username)
        subscriber_result = await session.execute(subscriber_query)
        subscribe_to_result = await session.execute(subscribe_to_query)
        subscriber =  subscriber_result.scalars().first()
        subscribe_to =  subscribe_to_result.scalars().first()

        if not subscriber or not subscribe_to:
            raise HTTPException(status_code=404, detail="User not found")

        subscription_check_query =  select(subscriptions).filter_by(
            subscriber_id=subscriber.id,
            subscribed_to_id=subscribe_to.id
        )
        subscription_check_result = await session.execute(subscription_check_query)
        subscription =  subscription_check_result.scalars().first()

        if subscription:
            raise HTTPException(status_code=400, detail="Already subscribed or pending confirmation")

        await session.execute(
            subscriptions.insert().values(
                subscriber_id=subscriber.id,
                subscribed_to_id=subscribe_to.id,
                is_confirmed=False  
            )
        )
        # await session.commit()

        # Optionally, notify the subscribed-to user via WebSocket if online
        await manager.send_personal_message(
            f"User {subscriber.username} subscribed to you. Waiting for confirmation.",
            str(subscribe_to.id)
        )

        return {"message": f"Subscription request sent from {subscriber.username} to {subscribe_to.username}."}

@app.post("/confirm_subscription/")
async def confirm_subscription(subscriber_id: int, subscribed_to_id: int, db: AsyncSession = Depends(get_db)):
    async with db as session:
        subscription_query = select(subscriptions).filter_by(
            subscriber_id=subscriber_id,
            subscribed_to_id=subscribed_to_id
        )
        result = await session.execute(subscription_query)
        subscription = result.scalars().first()

        if not subscription:
            raise HTTPException(status_code=404, detail="Subscription not found")

        if subscription.is_confirmed:
            raise HTTPException(status_code=400, detail="Subscription already confirmed")

        await session.execute(
            subscriptions.update().where(
                subscriptions.c.subscriber_id == subscriber_id,
                subscriptions.c.subscribed_to_id == subscribed_to_id
            ).values(is_confirmed=True)
        )
        await session.commit()

        # Optionally, notify both users via WebSocket if online
        await manager.send_personal_message(
            "Your subscription has been confirmed.",
            str(subscriber_id)
        )
        await manager.send_personal_message(
            f"User {subscriber_id} confirmed your subscription.",
            str(subscribed_to_id)
        )

        return {"message": "Subscription confirmed."}
