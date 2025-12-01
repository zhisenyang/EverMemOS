import asyncio
import logging
from pymongo import AsyncMongoClient
from pymongo.errors import ServerSelectionTimeoutError

# 开启详细日志
logging.basicConfig(level=logging.DEBUG)


async def detailed_diagnosis():
    configs = [
        {
            'name': '测试 1: 基本连接',
            'uri': 'mongodb://shanda:shanda123@mem-db-dev.dlab.org:27017/mem-dev-zhanghui-opensource?authSource=admin',
        },
        {
            'name': '测试 2: 直连模式',
            'uri': 'mongodb://shanda:shanda123@mem-db-dev.dlab.org:27017/mem-dev-zhanghui-opensource?directConnection=true&authSource=admin',
        },
        {
            'name': '测试 3: 增加超时',
            'uri': 'mongodb://shanda:shanda123@mem-db-dev.dlab.org:27017/mem-dev-zhanghui-opensource?directConnection=true&serverSelectionTimeoutMS=30000&authSource=admin',
        },
        {
            'name': '测试 4: 指定数据库',
            'uri': 'mongodb://shanda:shanda123@mem-db-dev.dlab.org:27017/mem-dev-zhanghui-opensource?directConnection=true&authSource=admin',
        },
    ]

    for config in configs:
        print(f"\n{'='*60}")
        print(config['name'])
        print(f"{'='*60}")

        try:
            print(config['uri'])
            client = AsyncMongoClient(config['uri'])

            # 尝试 ping
            result = await client.admin.command('ping')
            print(f"✅ 成功! Ping 结果: {result}")

            # 获取服务器信息
            server_info = await client.server_info()

            print(f"MongoDB 版本: {server_info.get('version')}")

            # 列出数据库
            dbs = await client.list_database_names()
            print(f"可用数据库: {dbs}")

            await client.close()

        except ServerSelectionTimeoutError as e:
            print(f"❌ 服务器选择超时")
            print(f"详细错误: {e}")
        except asyncio.TimeoutError:
            print(f"❌ 操作超时")
        except Exception as e:
            print(f"❌ 错误: {type(e).__name__}: {e}")


asyncio.run(detailed_diagnosis())
