#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试租户上下文功能

本测试演示如何在租户模式下使用 ConversationStatusRawRepository：
1. 测试设置租户上下文后的数据库操作
2. 测试没有租户上下文时使用默认客户端
3. 测试在不同租户之间切换
4. 测试非租户模式（TENANT_NON_TENANT_MODE=true）

使用的 MongoDB 配置：
- MONGODB_HOST=mem-db-dev.dlab.org
- MONGODB_PORT=27017
- MONGODB_USERNAME=shanda
- MONGODB_PASSWORD=shanda123
- MONGODB_DATABASE=mem-dev-zhanghui-t1
- MONGODB_URI_PARAMS="authSource=admin"
"""

import asyncio
import os
from datetime import datetime

from core.di import get_bean_by_type
from common_utils.datetime_utils import get_now_with_timezone
from infra_layer.adapters.out.persistence.repository.conversation_status_raw_repository import (
    ConversationStatusRawRepository,
)
from core.tenants.tenant_contextvar import (
    set_current_tenant,
    get_current_tenant_id,
    clear_current_tenant,
)
from core.tenants.tenant_models import TenantInfo, TenantDetail
from core.tenants.tenant_config import get_tenant_config
from core.observation.logger import get_logger

logger = get_logger(__name__)


def compare_datetime(dt1: datetime, dt2: datetime) -> bool:
    """比较两个datetime对象，只比较到秒级精度

    注意: 比较前会将两个datetime都转换为时间戳，避免时区差异导致的比较失败
    """
    # 将两个datetime转换为秒级时间戳进行比较，避免时区差异
    timestamp1 = int(dt1.timestamp())
    timestamp2 = int(dt2.timestamp())
    return timestamp1 == timestamp2


async def test_with_tenant_context():
    """
    测试：在设置租户上下文的情况下进行数据库操作

    此测试会：
    1. 创建一个租户信息，包含 MongoDB 配置
    2. 设置租户上下文
    3. 执行数据库操作
    4. 清理租户上下文
    """
    logger.info("=" * 80)
    logger.info("🧪 测试1: 在租户上下文下进行数据库操作")
    logger.info("=" * 80)

    # 步骤1: 创建租户信息
    tenant_info = TenantInfo(
        tenant_id="tenant_test_001",
        tenant_detail=TenantDetail(
            storage_info={
                "mongodb": {
                    "host": "mem-db-dev.dlab.org",
                    "port": 27017,
                    "username": "shanda",
                    "password": "shanda123",
                    "database": "mem-dev-zhanghui-t1",
                }
            }
        ),
        origin_tenant_data={
            "tenant_name": "测试租户001",
            "description": "这是一个用于测试的租户",
        },
    )

    logger.info("📋 创建租户信息: tenant_id=%s", tenant_info.tenant_id)
    logger.info("📋 MongoDB 配置: %s", tenant_info.get_storage_info("mongodb"))

    try:
        # 步骤2: 设置租户上下文
        set_current_tenant(tenant_info)
        logger.info("✅ 已设置租户上下文: %s", get_current_tenant_id())

        # 步骤3: 获取 Repository 并进行数据库操作
        repo = get_bean_by_type(ConversationStatusRawRepository)
        group_id = "test_tenant_group_001"
        current_time = get_now_with_timezone()

        # 创建测试数据
        update_data = {
            "old_msg_start_time": current_time,
            "new_msg_start_time": current_time,
            "last_memcell_time": current_time,
        }

        logger.info("📝 正在创建对话状态记录...")
        result = await repo.upsert_by_group_id(group_id, update_data)
        assert result is not None, "创建记录失败"
        assert result.group_id == group_id, "group_id 不匹配"
        logger.info("✅ 成功创建对话状态记录: group_id=%s", group_id)

        # 查询测试数据
        logger.info("🔍 正在查询对话状态记录...")
        queried = await repo.get_by_group_id(group_id)
        assert queried is not None, "查询记录失败"
        assert queried.group_id == group_id, "查询的 group_id 不匹配"
        assert compare_datetime(
            queried.old_msg_start_time, current_time
        ), "old_msg_start_time 不匹配"
        logger.info("✅ 成功查询对话状态记录")
        logger.info("   - group_id: %s", queried.group_id)
        logger.info("   - old_msg_start_time: %s", queried.old_msg_start_time)
        logger.info("   - new_msg_start_time: %s", queried.new_msg_start_time)

        # 更新测试数据
        new_time = get_now_with_timezone()
        update_data = {"old_msg_start_time": new_time, "new_msg_start_time": new_time}

        logger.info("📝 正在更新对话状态记录...")
        updated = await repo.upsert_by_group_id(group_id, update_data)
        assert updated is not None, "更新记录失败"
        assert compare_datetime(
            updated.old_msg_start_time, new_time
        ), "更新后的时间不匹配"
        logger.info("✅ 成功更新对话状态记录")

        # 清理测试数据
        logger.info("🧹 正在清理测试数据...")
        await updated.delete()
        logger.info("✅ 成功清理测试数据")

        # 验证删除
        final_check = await repo.get_by_group_id(group_id)
        assert final_check is None, "记录应该已被删除"
        logger.info("✅ 验证删除成功")

    except Exception as e:
        logger.error("❌ 测试失败: %s", e)
        raise

    finally:
        # 步骤4: 清理租户上下文
        clear_current_tenant()
        logger.info("✅ 已清理租户上下文")

    logger.info("✅ 测试1完成: 租户上下文测试通过")


async def test_without_tenant_context():
    """
    测试：在没有租户上下文的情况下进行数据库操作

    此测试会：
    1. 不设置租户上下文（或清除租户上下文）
    2. 执行数据库操作（应该使用默认客户端）
    3. 验证操作是否成功
    """
    logger.info("=" * 80)
    logger.info("🧪 测试2: 在没有租户上下文下使用默认客户端")
    logger.info("=" * 80)

    try:
        # 确保没有租户上下文
        clear_current_tenant()
        logger.info("⚠️  当前没有租户上下文，将使用默认客户端")
        logger.info("⚠️  默认客户端配置从环境变量 MONGODB_* 读取")

        # 获取 Repository 并进行数据库操作
        repo = get_bean_by_type(ConversationStatusRawRepository)
        group_id = "test_default_group_001"
        current_time = get_now_with_timezone()

        # 创建测试数据
        update_data = {
            "old_msg_start_time": current_time,
            "new_msg_start_time": current_time,
            "last_memcell_time": current_time,
        }

        logger.info("📝 正在使用默认客户端创建对话状态记录...")
        result = await repo.upsert_by_group_id(group_id, update_data)
        assert result is not None, "创建记录失败"
        assert result.group_id == group_id, "group_id 不匹配"
        logger.info("✅ 成功使用默认客户端创建对话状态记录: group_id=%s", group_id)

        # 查询测试数据
        logger.info("🔍 正在使用默认客户端查询对话状态记录...")
        queried = await repo.get_by_group_id(group_id)
        assert queried is not None, "查询记录失败"
        assert queried.group_id == group_id, "查询的 group_id 不匹配"
        logger.info("✅ 成功使用默认客户端查询对话状态记录")

        # 清理测试数据
        logger.info("🧹 正在清理测试数据...")
        await queried.delete()
        logger.info("✅ 成功清理测试数据")

    except Exception as e:
        logger.error("❌ 测试失败: %s", e)
        raise

    logger.info("✅ 测试2完成: 默认客户端测试通过")


async def test_switch_between_tenants():
    """
    测试：在不同租户之间切换

    此测试会：
    1. 设置租户A的上下文，创建数据
    2. 切换到租户B的上下文，创建数据
    3. 验证数据隔离（租户A的数据在租户B的上下文中不可见）
    4. 清理测试数据
    """
    logger.info("=" * 80)
    logger.info("🧪 测试3: 在不同租户之间切换")
    logger.info("=" * 80)

    # 创建两个租户信息
    tenant_a = TenantInfo(
        tenant_id="tenant_a",
        tenant_detail=TenantDetail(
            storage_info={
                "mongodb": {
                    "host": "mem-db-dev.dlab.org",
                    "port": 27017,
                    "username": "shanda",
                    "password": "shanda123",
                    "database": "mem-dev-zhanghui-t1",
                }
            }
        ),
        origin_tenant_data={"tenant_name": "租户A"},
    )

    tenant_b = TenantInfo(
        tenant_id="tenant_b",
        tenant_detail=TenantDetail(
            storage_info={
                "mongodb": {
                    "host": "mem-db-dev.dlab.org",
                    "port": 27017,
                    "username": "shanda",
                    "password": "shanda123",
                    "database": "mem-dev-zhanghui-t2",
                }
            }
        ),
        origin_tenant_data={"tenant_name": "租户B"},
    )

    try:
        # 场景1: 在租户A的上下文中操作
        logger.info("📋 切换到租户A的上下文")
        set_current_tenant(tenant_a)
        logger.info("✅ 当前租户: %s", get_current_tenant_id())

        repo = get_bean_by_type(ConversationStatusRawRepository)
        group_id_a = "test_switch_group_a"
        current_time_a = get_now_with_timezone()

        result_a = await repo.upsert_by_group_id(
            group_id_a,
            {
                "old_msg_start_time": current_time_a,
                "new_msg_start_time": current_time_a,
                "last_memcell_time": current_time_a,
            },
        )
        assert result_a is not None, "租户A创建记录失败"
        logger.info("✅ 租户A创建记录成功: group_id=%s", group_id_a)

        # 场景2: 切换到租户B的上下文中操作
        logger.info("📋 切换到租户B的上下文")
        set_current_tenant(tenant_b)
        logger.info("✅ 当前租户: %s", get_current_tenant_id())

        group_id_b = "test_switch_group_b"
        current_time_b = get_now_with_timezone()

        result_b = await repo.upsert_by_group_id(
            group_id_b,
            {
                "old_msg_start_time": current_time_b,
                "new_msg_start_time": current_time_b,
                "last_memcell_time": current_time_b,
            },
        )
        assert result_b is not None, "租户B创建记录失败"
        logger.info("✅ 租户B创建记录成功: group_id=%s", group_id_b)

        # 场景3: 验证租户隔离（两个租户使用不同的数据库）
        # 注意：因为两个租户使用的是不同的数据库，所以数据是完全隔离的
        # 租户B的上下文中应该查询不到租户A创建的数据
        logger.info("📋 验证数据隔离性")

        # 在租户B的上下文中查询租户A创建的数据
        queried_a_in_b = await repo.get_by_group_id(group_id_a)
        assert queried_a_in_b is None, "租户B不应该看到租户A的数据（数据应该隔离）"
        logger.info("✅ 租户隔离验证成功：租户B无法看到租户A的数据")
        logger.info("✅ 这是因为两个租户使用的是不同的数据库（t1和t2）")

        # 清理租户B的数据
        logger.info("🧹 清理租户B的测试数据...")
        await result_b.delete()
        logger.info("✅ 清理租户B的数据成功")

        # 切换回租户A并清理数据
        logger.info("📋 切换回租户A的上下文")
        set_current_tenant(tenant_a)

        logger.info("🧹 清理租户A的测试数据...")
        await result_a.delete()
        logger.info("✅ 清理租户A的数据成功")

    except Exception as e:
        logger.error("❌ 测试失败: %s", e)
        raise

    finally:
        # 清理租户上下文
        clear_current_tenant()
        logger.info("✅ 已清理租户上下文")

    logger.info("✅ 测试3完成: 租户切换测试通过")


async def test_non_tenant_mode():
    """
    测试：非租户模式

    此测试会：
    1. 启用非租户模式（设置环境变量 TENANT_NON_TENANT_MODE=true）
    2. 设置租户上下文
    3. 验证即使设置了租户上下文，也会使用默认客户端
    4. 恢复原来的环境变量
    """
    logger.info("=" * 80)
    logger.info("🧪 测试4: 非租户模式")
    logger.info("=" * 80)

    # 保存原始环境变量
    original_env = os.getenv("TENANT_NON_TENANT_MODE")

    try:
        # 步骤1: 启用非租户模式
        os.environ["TENANT_NON_TENANT_MODE"] = "true"

        # 重新加载租户配置
        config = get_tenant_config()
        config.reload()

        logger.info("🔧 已启用非租户模式: TENANT_NON_TENANT_MODE=true")
        logger.info("⚠️  在非租户模式下，即使设置了租户上下文，也会使用默认客户端")

        # 步骤2: 设置租户上下文
        tenant_info = TenantInfo(
            tenant_id="tenant_non_mode_test",
            tenant_detail=TenantDetail(
                storage_info={
                    "mongodb": {
                        "host": "mem-db-dev.dlab.org",
                        "port": 27017,
                        "username": "shanda",
                        "password": "shanda123",
                        "database": "mem-dev-zhanghui-t2",  # 注意：这个配置会被忽略
                    }
                }
            ),
            origin_tenant_data={"tenant_name": "非租户模式测试"},
        )

        set_current_tenant(tenant_info)
        logger.info("📋 已设置租户上下文: tenant_id=%s", get_current_tenant_id())
        logger.info("⚠️  但是系统会忽略租户配置，使用默认客户端")

        # 步骤3: 执行数据库操作
        repo = get_bean_by_type(ConversationStatusRawRepository)
        group_id = "test_non_tenant_mode_001"
        current_time = get_now_with_timezone()

        # 创建测试数据
        update_data = {
            "old_msg_start_time": current_time,
            "new_msg_start_time": current_time,
            "last_memcell_time": current_time,
        }

        logger.info("📝 正在创建对话状态记录...")
        logger.info("⚠️  数据将写入默认数据库（从环境变量 MONGODB_DATABASE 读取）")
        result = await repo.upsert_by_group_id(group_id, update_data)
        assert result is not None, "创建记录失败"
        assert result.group_id == group_id, "group_id 不匹配"
        logger.info("✅ 成功创建对话状态记录: group_id=%s", group_id)

        # 查询测试数据
        logger.info("🔍 正在查询对话状态记录...")
        queried = await repo.get_by_group_id(group_id)
        assert queried is not None, "查询记录失败"
        assert queried.group_id == group_id, "查询的 group_id 不匹配"
        logger.info("✅ 成功查询对话状态记录")
        logger.info("✅ 验证：非租户模式下使用默认客户端成功")

        # 清理测试数据
        logger.info("🧹 正在清理测试数据...")
        await queried.delete()
        logger.info("✅ 成功清理测试数据")

    except Exception as e:
        logger.error("❌ 测试失败: %s", e)
        raise

    finally:
        # 步骤4: 恢复原始环境变量
        if original_env is None:
            if "TENANT_NON_TENANT_MODE" in os.environ:
                del os.environ["TENANT_NON_TENANT_MODE"]
            logger.info("🔧 已删除环境变量 TENANT_NON_TENANT_MODE")
        else:
            os.environ["TENANT_NON_TENANT_MODE"] = original_env
            logger.info("🔧 已恢复环境变量 TENANT_NON_TENANT_MODE=%s", original_env)

        # 重新加载租户配置
        config = get_tenant_config()
        config.reload()
        logger.info("🔄 已重新加载租户配置")

        # 清理租户上下文
        clear_current_tenant()
        logger.info("✅ 已清理租户上下文")

    logger.info("✅ 测试4完成: 非租户模式测试通过")


async def run_all_tests():
    """运行所有租户上下文测试"""
    logger.info("🚀 开始运行租户上下文测试套件...")
    logger.info("")

    try:
        # 测试1: 有租户上下文
        await test_with_tenant_context()
        logger.info("")

        # 测试2: 没有租户上下文（使用默认客户端）
        await test_without_tenant_context()
        logger.info("")

        # 测试3: 在不同租户之间切换
        await test_switch_between_tenants()
        logger.info("")

        # 测试4: 非租户模式
        await test_non_tenant_mode()
        logger.info("")

        logger.info("=" * 80)
        logger.info("✅ 所有租户上下文测试完成")
        logger.info("=" * 80)

    except Exception as e:
        logger.error("❌ 测试过程中出现错误: %s", e)
        raise


if __name__ == "__main__":
    asyncio.run(run_all_tests())
