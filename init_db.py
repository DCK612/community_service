"""
数据库初始化脚本 — 建表 + 插入测试数据。

运行方式：
    python init_db.py

测试数据：
- 3 位居民：张居民、李居民、王居民
- 5 位服务者：赵师傅（维修）、钱阿姨（保洁）、孙师傅（搬家）、
               周老师（家教）、吴护理（养老）
- 若干模拟订单（覆盖各状态）
"""

import asyncio
from datetime import datetime, timedelta

from models.database import async_session_factory, engine, Base
from models.order import Order, OrderCategory, OrderStatus
from models.price_guide import PriceGuide
from models.review import Review, ReviewType
from models.user import (
    ProviderProfile,
    ProviderStatus,
    ResidentProfile,
    UserRole,
    UserBase,
)


# ==================== 测试数据生成 ====================

async def init_database():
    """创建表结构并填充测试数据。"""
    print("=" * 60)
    print("[初始化] 社区服务平台数据库")
    print("=" * 60)

    # 1. 创建表
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    print("[OK] 表结构创建完成")

    # 初始化超级管理员
    from service.auth_service import init_super_admin
    async with async_session_factory() as db:
        await init_super_admin(db)
    print("[OK] 超级管理员 DDD 已就绪")

    async with async_session_factory() as db:
        # 2. 创建居民
        residents_data = [
            {
                "phone": "13800001001",
                "nickname": "张居民",
                "address": "幸福小区 1 栋 101",
                "latitude": 30.5728,
                "longitude": 104.0668,
            },
            {
                "phone": "13800001002",
                "nickname": "李居民",
                "address": "幸福小区 2 栋 203",
                "latitude": 30.5740,
                "longitude": 104.0680,
            },
            {
                "phone": "13800001003",
                "nickname": "王居民",
                "address": "幸福小区 3 栋 305",
                "latitude": 30.5715,
                "longitude": 104.0655,
            },
        ]

        residents = []
        for data in residents_data:
            user = UserBase(
                phone=data["phone"],
                nickname=data["nickname"],
                role=UserRole.RESIDENT,
            )
            db.add(user)
            await db.flush()

            profile = ResidentProfile(
                user_id=user.id,
                address=data["address"],
                latitude=data["latitude"],
                longitude=data["longitude"],
            )
            db.add(profile)
            residents.append(user)
            print(f"[居民] {user.nickname} (ID={user.id})")

        # 3. 创建服务者
        providers_data = [
            {
                "phone": "13900002001",
                "nickname": "赵师傅",
                "skills": "维修,修水管,修电器,通下水道",
                "latitude": 30.5730,
                "longitude": 104.0670,
                "credit_score": 92,
            },
            {
                "phone": "13900002002",
                "nickname": "钱阿姨",
                "skills": "保洁,清洁,打扫,擦窗",
                "latitude": 30.5720,
                "longitude": 104.0660,
                "credit_score": 88,
            },
            {
                "phone": "13900002003",
                "nickname": "孙师傅",
                "skills": "搬家,搬运,货运",
                "latitude": 30.5750,
                "longitude": 104.0690,
                "credit_score": 75,
            },
            {
                "phone": "13900002004",
                "nickname": "周老师",
                "skills": "家教,辅导,教学,数学,英语",
                "latitude": 30.5710,
                "longitude": 104.0640,
                "credit_score": 95,
            },
            {
                "phone": "13900002005",
                "nickname": "吴护理",
                "skills": "护理,陪护,养老,照顾老人",
                "latitude": 30.5745,
                "longitude": 104.0675,
                "credit_score": 25,
                "blacklisted": True,
                "blacklist_type": "permanent",
            },
        ]

        providers = []
        for data in providers_data:
            user = UserBase(
                phone=data["phone"],
                nickname=data["nickname"],
                role=UserRole.PROVIDER,
            )
            db.add(user)
            await db.flush()

            profile = ProviderProfile(
                user_id=user.id,
                skills=data["skills"],
                latitude=data["latitude"],
                longitude=data["longitude"],
                credit_score=data.get("credit_score", 80),
                blacklisted=data.get("blacklisted", False),
                blacklist_type=data.get("blacklist_type"),
                status=ProviderStatus.ONLINE,
            )
            # 吴护理设为已拉黑
            if data.get("blacklisted"):
                profile.blacklisted_at = datetime.now()
                profile.status = ProviderStatus.OFFLINE

            db.add(profile)
            providers.append(user)
            tag = " [已拉黑]" if data.get("blacklisted") else ""
            print(f"[服务者] {user.nickname} (ID={user.id}) 信用分={profile.credit_score}{tag}")

        await db.flush()

        # 4. 创建模拟订单
        now = datetime.now()

        # 4.1 PENDING 订单（待接单）
        pending_order = Order(
            order_no="CS20260702001",
            title="水龙头维修",
            resident_id=residents[0].id,
            category=OrderCategory.REPAIR,
            description="厨房水龙头漏水，需要师傅上门维修",
            address="幸福小区 1 栋 101",
            latitude=30.5728,
            longitude=104.0668,
            status=OrderStatus.PENDING,
            amount=150.00,
            created_at=now,
        )
        db.add(pending_order)
        print(f"[订单] PENDING  #{pending_order.order_no} — 水龙头维修")

        # 4.2 ACCEPTED 订单（已接单，待开始）
        accepted_order = Order(
            order_no="CS20260702002",
            title="全屋保洁",
            resident_id=residents[1].id,
            provider_id=providers[1].id,  # 钱阿姨
            category=OrderCategory.CLEANING,
            description="全屋打扫，2室1厅，需要擦窗",
            address="幸福小区 2 栋 203",
            latitude=30.5740,
            longitude=104.0680,
            status=OrderStatus.ACCEPTED,
            amount=200.00,
            created_at=now - timedelta(hours=2),
            accepted_at=now - timedelta(hours=1),
        )
        db.add(accepted_order)
        print(f"[订单] ACCEPTED #{accepted_order.order_no} — 全屋保洁")

        # 4.3 IN_PROGRESS 订单（服务中）
        in_progress_order = Order(
            order_no="CS20260702003",
            title="热水器检修",
            resident_id=residents[0].id,
            provider_id=providers[0].id,  # 赵师傅
            category=OrderCategory.REPAIR,
            description="热水器不制热，需要检修",
            address="幸福小区 1 栋 101",
            latitude=30.5728,
            longitude=104.0668,
            status=OrderStatus.IN_PROGRESS,
            amount=300.00,
            created_at=now - timedelta(hours=5),
            accepted_at=now - timedelta(hours=4),
            service_started_at=now - timedelta(hours=3),
        )
        db.add(in_progress_order)
        print(f"[订单] IN_PROGRESS #{in_progress_order.order_no} — 热水器检修")

        # 4.4 WAITING_CONFIRM 订单（服务完成，待确认）
        waiting_confirm_order = Order(
            order_no="CS20260702004",
            title="初中数学辅导",
            resident_id=residents[2].id,
            provider_id=providers[3].id,  # 周老师
            category=OrderCategory.TUTORING,
            description="初中数学辅导，每周两次",
            address="幸福小区 3 栋 305",
            latitude=30.5715,
            longitude=104.0655,
            status=OrderStatus.WAITING_CONFIRM,
            amount=500.00,
            created_at=now - timedelta(days=1),
            accepted_at=now - timedelta(days=1, hours=1),
            service_started_at=now - timedelta(hours=20),
            service_ended_at=now - timedelta(hours=18),
        )
        db.add(waiting_confirm_order)
        print(f"[订单] WAITING_CONFIRM #{waiting_confirm_order.order_no} — 数学辅导")

        # 4.5 WAITING_REVIEW 订单（已确认，待评价）
        waiting_review_order = Order(
            order_no="CS20260702005",
            title="英语一对一辅导",
            resident_id=residents[0].id,
            provider_id=providers[3].id,  # 周老师
            category=OrderCategory.TUTORING,
            description="英语一对一辅导",
            address="幸福小区 1 栋 101",
            latitude=30.5728,
            longitude=104.0668,
            status=OrderStatus.WAITING_REVIEW,
            amount=400.00,
            created_at=now - timedelta(days=3),
            accepted_at=now - timedelta(days=3, hours=1),
            service_started_at=now - timedelta(days=3, hours=2),
            service_ended_at=now - timedelta(days=3, hours=4),
            confirmed_at=now - timedelta(days=3, hours=5),
        )
        db.add(waiting_review_order)
        print(f"[订单] WAITING_REVIEW #{waiting_review_order.order_no} — 英语辅导")

        # 4.6 COMPLETED 订单（已完成）
        completed_order = Order(
            order_no="CS20260702006",
            title="深度保洁",
            resident_id=residents[1].id,
            provider_id=providers[1].id,  # 钱阿姨
            category=OrderCategory.CLEANING,
            description="入住前深度保洁，3室2厅",
            address="幸福小区 2 栋 203",
            latitude=30.5740,
            longitude=104.0680,
            status=OrderStatus.COMPLETED,
            amount=350.00,
            created_at=now - timedelta(days=7),
            accepted_at=now - timedelta(days=7, hours=1),
            service_started_at=now - timedelta(days=7, hours=2),
            service_ended_at=now - timedelta(days=7, hours=6),
            confirmed_at=now - timedelta(days=7, hours=7),
            completed_at=now - timedelta(days=7, hours=8),
        )
        db.add(completed_order)
        await db.flush()
        print(f"[订单] COMPLETED  #{completed_order.order_no} — 深度保洁")

        # 4.7 为已完成订单创建互评记录
        review_resident = Review(
            order_id=completed_order.id,
            review_type=ReviewType.RESIDENT_TO_PROVIDER,
            reviewer_id=residents[1].id,
            reviewed_id=providers[1].id,
            resident_attitude=5,
            professionalism=4,
            punctuality=5,
            cost=4,
            after_sale=4,
            comment="钱阿姨打扫很干净，守时专业！",
        )
        db.add(review_resident)

        review_provider = Review(
            order_id=completed_order.id,
            review_type=ReviewType.PROVIDER_TO_RESIDENT,
            reviewer_id=providers[1].id,
            reviewed_id=residents[1].id,
            provider_accuracy=5,
            cooperation=5,
            payment=5,
            comment="李居民很配合，付款及时",
        )
        db.add(review_provider)
        print(f"[评价] 已完成订单互评 #{completed_order.order_no}")

        # ---------- 定价参考测试数据 ----------
        price_data = [
            # 维修类
            PriceGuide(category=OrderCategory.REPAIR, name="水管漏水维修", description="水龙头、水管、接头漏水修补", price_min=80, price_max=200, unit="次"),
            PriceGuide(category=OrderCategory.REPAIR, name="电路故障排查", description="跳闸、插座损坏、线路老化检测与维修", price_min=100, price_max=300, unit="次"),
            PriceGuide(category=OrderCategory.REPAIR, name="空调维修", description="不制冷、异响、漏水等常见故障维修", price_min=150, price_max=500, unit="台"),
            PriceGuide(category=OrderCategory.REPAIR, name="门锁更换", description="入户门/室内门锁具更换与安装", price_min=50, price_max=150, unit="把"),
            PriceGuide(category=OrderCategory.REPAIR, name="墙面修补粉刷", description="裂缝填补、局部刷漆、墙皮脱落修复", price_min=30, price_max=80, unit="平方米"),
            # 保洁类
            PriceGuide(category=OrderCategory.CLEANING, name="日常保洁", description="地面清扫、家具擦拭、卫生间清洁", price_min=40, price_max=80, unit="小时"),
            PriceGuide(category=OrderCategory.CLEANING, name="深度保洁", description="厨房油烟机、死角、玻璃、全屋深度清洁", price_min=60, price_max=120, unit="小时"),
            PriceGuide(category=OrderCategory.CLEANING, name="开荒保洁", description="新房装修后首次全面清洁", price_min=8, price_max=15, unit="平方米"),
            PriceGuide(category=OrderCategory.CLEANING, name="擦窗服务", description="内外窗玻璃清洁", price_min=3, price_max=8, unit="平方米"),
            # 搬家类
            PriceGuide(category=OrderCategory.MOVING, name="小型搬家", description="面包车搬运，适合单身/情侣", price_min=200, price_max=400, unit="车"),
            PriceGuide(category=OrderCategory.MOVING, name="家庭搬家", description="厢式货车搬运，适合2-3人家庭", price_min=500, price_max=1200, unit="车"),
            PriceGuide(category=OrderCategory.MOVING, name="家具拆装", description="床/衣柜/书桌等大件家具拆装", price_min=80, price_max=300, unit="件"),
            PriceGuide(category=OrderCategory.MOVING, name="空调移机", description="空调拆卸+运输+重新安装", price_min=300, price_max=600, unit="台"),
            # 家教类
            PriceGuide(category=OrderCategory.TUTORING, name="小学辅导", description="语数英全科作业辅导", price_min=60, price_max=120, unit="小时"),
            PriceGuide(category=OrderCategory.TUTORING, name="初中辅导", description="数理化/英语单科辅导", price_min=80, price_max=180, unit="小时"),
            PriceGuide(category=OrderCategory.TUTORING, name="高中辅导", description="高考科目冲刺辅导", price_min=120, price_max=250, unit="小时"),
            PriceGuide(category=OrderCategory.TUTORING, name="艺体特长", description="钢琴/绘画/书法/舞蹈等兴趣培养", price_min=100, price_max=200, unit="小时"),
            # 养老类
            PriceGuide(category=OrderCategory.ELDERLY_CARE, name="日常陪护", description="陪伴散步、聊天、简单家务协助", price_min=30, price_max=60, unit="小时"),
            PriceGuide(category=OrderCategory.ELDERLY_CARE, name="康复理疗", description="术后恢复、按摩推拿、康复训练指导", price_min=80, price_max=150, unit="次"),
            PriceGuide(category=OrderCategory.ELDERLY_CARE, name="上门助浴", description="协助行动不便老人洗澡", price_min=60, price_max=120, unit="次"),
            # 其他类
            PriceGuide(category=OrderCategory.OTHER, name="宠物代遛", description="遛狗、喂食、铲屎", price_min=20, price_max=50, unit="次"),
            PriceGuide(category=OrderCategory.OTHER, name="代取快递", description="小区周边快递代取并送货上门", price_min=5, price_max=10, unit="件"),
        ]
        db.add_all(price_data)
        print(f"[定价] 已插入 {len(price_data)} 条定价参考数据")

        await db.commit()

    print("-" * 60)
    print("[完成] 测试数据初始化成功！")
    print(f"[统计] 居民 {len(residents)} 人，服务者 {len(providers)} 人")
    print(f"[启动] uvicorn main:app --reload")
    print("=" * 60)


# ==================== 入口 ====================

if __name__ == "__main__":
    asyncio.run(init_database())
