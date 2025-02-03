from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Detail, Category, Task, MsgId


############################ Детали ######################################
async def orm_add_detail(session: AsyncSession, data: dict):
    obj = Detail(
        name=data["name"],
        number=(data["number"]),
        category_id=data["category"],
        status=data["status"],
    )
    session.add(obj)
    await session.commit()


async def orm_get_details(session: AsyncSession, category_id):
    query = select(Detail).where(Detail.category_id == int(category_id))
    result = await session.execute(query)
    return result.scalars().all()


async def orm_get_detail_report(session: AsyncSession, name: str):
    query = select(Detail).filter(Detail.name == name)
    result = await session.execute(query)
    return result.scalars().all()


async def orm_get_detail(session: AsyncSession, detail_id: int):
    query = select(Detail).where(Detail.id == detail_id)
    result = await session.execute(query)
    return result.scalar()


async def orm_update_detail(session: AsyncSession, detail_id: int, data):
    query = update(Detail).where(Detail.id == detail_id).values(
        name=data["name"],
        number=(data["number"]),
        category_id=data["category"],
        status=data["status"],)
    await session.execute(query)
    await session.commit()


async def orm_delete_detail(session: AsyncSession, detail_id: int):
    query = delete(Detail).where(Detail.id == detail_id)
    await session.execute(query)
    await session.commit()


############################ Категории изделий ######################################
async def orm_get_categories(session: AsyncSession):
    query = select(Category)
    result = await session.execute(query)
    return result.scalars().all()


async def orm_create_categories(session: AsyncSession, categories: list):
    query = select(Category)
    result = await session.execute(query)
    if result.first():
        return
    session.add_all([Category(name=name) for name in categories])
    await session.commit()


############################ Задачи ######################################

async def orm_add_task(session: AsyncSession, data: dict):
    obj = Task(
        description=data["description"],
        username=data["username"],
        contact_number=data["contact_number"],
        group_message_id=data.get("group_message_id"),
    )
    session.add(obj)
    await session.commit()
async def orm_get_tasks(session: AsyncSession):
    query = select(Task)
    result = await session.execute(query)
    return result.scalars().all()

async def orm_delete_task(session: AsyncSession, task_id: int):
    query = delete(Task).where(Task.id == task_id)
    await session.execute(query)
    await session.commit()

async def orm_get_task_by_id(session: AsyncSession, task_id: int):
    query = select(Task).where(Task.id == task_id)
    result = await session.execute(query)
    return result.scalar_one_or_none()


############################ ID сообщений ######################################
async def update_summary_msg_id(session: AsyncSession, chat_id: int, summary_msg_id: int):
    async with session.begin():
        result = await session.execute(select(MsgId).filter_by(chat_id=chat_id))
        msg = result.scalars().first()

        if msg:
            msg.summary_msg_id = summary_msg_id
        else:
            msg = MsgId(chat_id=chat_id, summary_msg_id=summary_msg_id)
            session.add(msg)

        await session.commit()



async def update_detail_report_msg_id(session: AsyncSession, chat_id: int, msg_id: int):
    # Создаем новую запись для каждого сообщения
    msg = MsgId(chat_id=chat_id, detail_report_msg_id=msg_id)
    session.add(msg)
    await session.commit()


async def update_all_report_msg_id(session: AsyncSession, chat_id: int, new_msg_id: int):
    print(f"Обновляем/добавляем записи для chat_id={chat_id}, new_msg_id={new_msg_id}")
    result = await session.execute(select(MsgId).filter_by(chat_id=chat_id))
    msg_record = result.scalars().first()

    if msg_record:
        print(f"Найдена запись для chat_id={chat_id}")
        msg_ids = msg_record.all_report_msg_id.split(",") if msg_record.all_report_msg_id else []
        msg_ids.append(str(new_msg_id))
        msg_record.all_report_msg_id = ",".join(msg_ids)
    else:
        print(f"Не найдена запись для chat_id={chat_id}, создаем новую")
        msg_record = MsgId(id=chat_id, chat_id=chat_id, all_report_msg_id=str(new_msg_id))
        session.add(msg_record)

    await session.commit()

