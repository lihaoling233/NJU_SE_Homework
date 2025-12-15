import pytest
import os
import datetime
from account_book import DBUtil, StatisticsManager

# ======================= 集成测试环境准备 =======================

@pytest.fixture
def env():
    """
    集成测试环境初始化：
    同时准备 DBUtil 和 StatisticsManager 实例，模拟真实运行环境。
    """
    db_name = "test_integration.db"
    if os.path.exists(db_name):
        os.remove(db_name)
    
    # 1. 初始化数据库层
    db_util = DBUtil(db_name)
    
    # 2. 初始化统计业务层 (依赖数据库层)
    stat_mgr = StatisticsManager(db_util)
    
    yield db_util, stat_mgr
    
    # 清理环境
    db_util.close()
    if os.path.exists(db_name):
        os.remove(db_name)

# ======================= 集成场景一：预算控制流 =======================

def test_integration_budget_flow(env):
    """
    测试场景：用户设定预算 -> 消费 -> 查看剩余金额
    验证 DBUtil 中 set_budget, add_transaction 和 get_budget_status 的协同工作
    """
    db, _ = env
    
    # 1. [设置] 设定本月 '餐饮'(ID=1) 预算为 1000 元
    current_month = datetime.datetime.now().strftime('%Y-%m')
    db.set_monthly_budget(1, current_month, 1000.0)
    
    # 2. [动作] 记录第一笔支出：吃午饭 200 元
    # add_transaction 内部逻辑应该自动更新 budgets 表的 spent 字段
    today = datetime.datetime.now().strftime('%Y-%m-%d')
    db.add_transaction(200.0, 'EXPENSE', 1, today, 'lunch')
    
    # 3. [动作] 记录第二笔支出：请客 900 元 (导致超支)
    db.add_transaction(900.0, 'EXPENSE', 1, today, 'dinner')
    
    # 4. [查询] 获取预算状态报表
    # get_monthly_budget_status 涉及多表联查 (Left Join)
    status_list = db.get_monthly_budget_status(current_month)
    
    # 5. [验证] 寻找 '餐饮' 这一项的集成结果
    # 结果格式: (category_name, budget, spent, remain)
    food_status = None
    for item in status_list:
        if item[0] == '餐饮':
            food_status = item
            break
            
    assert food_status is not None, "未找到餐饮分类的预算状态"
    
    # 验证总预算是否保持 1000
    assert food_status[1] == 1000.0 
    # 验证总支出是否累加正确 (200 + 900 = 1100)
    assert food_status[2] == 1100.0
    # 验证剩余金额是否正确计算为负数 (1000 - 1100 = -100)
    assert food_status[3] == -100.0

# ======================= 集成场景二：统计报表流 =======================

def test_integration_statistics_flow(env):
    """
    测试场景：记录多笔收支 -> 生成月度统计 -> 生成对比报表
    验证 StatisticsManager 如何调用 DBUtil 并处理数据
    """
    db, stat_mgr = env
    today = datetime.datetime.now().strftime('%Y-%m-%d')
    
    # 1. [准备数据] 模拟用户的一系列操作
    # 收入: 工资 10000
    db.add_transaction(10000, 'INCOME', 6, today, 'salary')
    # 支出: 餐饮 500
    db.add_transaction(500, 'EXPENSE', 1, today, 'food')
    # 支出: 交通 100
    db.add_transaction(100, 'EXPENSE', 2, today, 'bus')
    
    # 2. [调用上层业务] 获取当月统计概览
    # StatisticsManager 会调用 DBUtil.get_monthly_statistics
    current_stat = stat_mgr.get_current_month_stat()
    
    # 3. [验证] 验证数据聚合结果
    assert current_stat['total_income'] == 10000.0
    assert current_stat['total_expense'] == 600.0  # 500 + 100
    assert current_stat['balance'] == 9400.0       # 10000 - 600
    
    # 4. [调用上层业务] 获取支出对比 (本月 vs 上月)
    # 这是一个典型的集成点：它需要计算变化率，需要处理上月无数据的情况
    comp_stat = stat_mgr.get_expense_comparison()
    
    # 5. [验证] 验证业务逻辑处理
    assert comp_stat['current_expense'] == 600.0
    assert comp_stat['last_expense'] == 0.0  # 新环境上月无数据
    # 根据代码逻辑，如果上月为0且本月>0，变化率应为 100.0
    assert comp_stat['change_rate'] == 100.0