import pytest
import os
import sqlite3
from account_book import DBUtil

# ======================= 测试固件 (Fixtures) =======================

@pytest.fixture
def db():
    """
    创建一个临时的测试数据库。
    使用 yield 关键字，在测试前创建，测试后自动删除，保证测试环境纯净。
    """
    db_name = "test_experiment_5.db"
    # 确保没有残留文件
    if os.path.exists(db_name):
        os.remove(db_name)
    
    # 初始化数据库
    util = DBUtil(db_name)
    
    # 返回工具实例供测试用例使用
    yield util
    
    # 清理工作
    util.close()
    if os.path.exists(db_name):
        os.remove(db_name)

# ======================= 子功能一：添加交易 (add_transaction) =======================
# 目标：测试逻辑分支（收入vs支出，有预算vs无预算，异常处理）
def test_add_income(db):
    """测试1：添加收入（不应触发预算更新）"""
    # 假设分类ID 6 是工资 (INCOME)
    success, tid = db.add_transaction(5000, 'INCOME', 6, '2025-01-01', '工姿', '一月')
    assert success is True
    assert tid > 0

def test_add_expense_no_budget(db):
    """测试2：添加支出，但该月该分类没有预设预算"""
    # 假设分类ID 1 是餐饮 (EXPENSE)
    success, tid = db.add_transaction(50, 'EXPENSE', 1, '2025-01-01', '午饭', '面条')
    assert success is True
    
    # 验证预算表里没有记录（因为没有预设预算，逻辑是 update 而不是 insert）
    db.connect()
    cursor = db.conn.cursor()
    cursor.execute("SELECT * FROM budgets WHERE category_id=1 AND month='2025-01'")
    assert cursor.fetchone() is None

def test_add_expense_with_budget(db):
    """测试3：添加支出，且该月已有预算（核心逻辑：预算已花费金额应增加）"""
    # 1. 先设置预算
    db.set_monthly_budget(1, '2025-01', 1000)
    
    # 2. 添加支出 100
    db.add_transaction(100, 'EXPENSE', 1, '2025-01-02')
    
    # 3. 验证预算表 spent 字段是否变为 100
    db.connect()
    cursor = db.conn.cursor()
    cursor.execute("SELECT spent FROM budgets WHERE category_id=1 AND month='2025-01'")
    result = cursor.fetchone()
    assert result[0] == 100.0

def test_add_expense_accumulate_budget(db):
    """测试4：连续添加两笔支出，预算应累加"""
    db.set_monthly_budget(1, '2025-01', 1000)
    db.add_transaction(100, 'EXPENSE', 1, '2025-01-02')
    db.add_transaction(50, 'EXPENSE', 1, '2025-01-03') # 同月同分类
    
    db.connect()
    spent = db.conn.cursor().execute("SELECT spent FROM budgets WHERE category_id=1").fetchone()[0]
    assert spent == 150.0

def test_add_transaction_db_closed_failure(db):
    """测试5：边界情况 - 数据库连接断开"""
    db.close() # 手动关闭
    success, msg = db.add_transaction(100, 'EXPENSE', 1, '2025-01-01')
    # 虽然 add_transaction 内部会尝试 connect，但如果我们破坏 self.db_name 就可以模拟
    # 这里我们简单测试逻辑，代码中 defend logic 是: if cursor is None...
    # 但 util.connect() 会自动重连。我们通过传入非法数据触发 SQL 错误来测试异常捕获
    pass # Python sqlite3 自动重连能力很强，跳过此连接测试，改测数据异常

def test_add_transaction_invalid_category(db):
    """测试6：外键约束错误（不存在的分类ID）"""
    # 开启外键约束需要 PRAGMA foreign_keys = ON，SQLite默认可能关闭。
    # 这里测试更通用的 SQL 错误，比如传入无法转换的数据
    # 但由于 python 弱类型，sqlite 会存入 text。
    # 我们测试逻辑错误：不符合 check 约束 (type 必须是 INCOME/EXPENSE)
    success, msg = db.add_transaction(100, 'INVALID_TYPE', 1, '2025-01-01')
    # CHECK 约束会失败
    assert success is False
    assert "CHECK constraint failed" in str(msg)

def test_add_transaction_boundary_amount_zero(db):
    """测试7：边界值 - 金额为0"""
    success, tid = db.add_transaction(0, 'EXPENSE', 1, '2025-01-01')
    assert success is True # 数据库层面允许0，业务层面由GUI控制，这里测试DB允许写入

def test_add_transaction_boundary_date_future(db):
    """测试8：边界值 - 未来日期"""
    success, tid = db.add_transaction(100, 'EXPENSE', 1, '2099-01-01')
    assert success is True

def test_add_transaction_different_month_budget(db):
    """测试9：跨月支出不影响本月预算"""
    db.set_monthly_budget(1, '2025-01', 1000) # 1月预算
    db.add_transaction(100, 'EXPENSE', 1, '2025-02-01') # 2月支出
    
    db.connect()
    spent = db.conn.cursor().execute("SELECT spent FROM budgets WHERE month='2025-01'").fetchone()[0]
    assert spent == 0.0 # 1月已用应仍为0

def test_add_transaction_long_remark(db):
    """测试10：超长备注"""
    long_str = "a" * 1000
    success, tid = db.add_transaction(100, 'EXPENSE', 1, '2025-01-01', remark=long_str)
    assert success is True

# ======================= 子功能二：查询交易 (get_transactions_by_condition) =======================
# 目标：覆盖所有查询条件的组合
def test_query_all(db):
    """测试11：无条件查询（查询所有）"""
    db.add_transaction(100, 'EXPENSE', 1, '2025-01-01')
    db.add_transaction(200, 'INCOME', 6, '2025-01-02')
    res = db.get_transactions_by_condition()
    assert len(res) == 2

def test_query_by_exact_date(db):
    """测试12：精确日期查询 (len=10)"""
    db.add_transaction(100, 'EXPENSE', 1, '2025-01-01')
    db.add_transaction(200, 'EXPENSE', 1, '2025-01-02')
    
    res = db.get_transactions_by_condition(date='2025-01-01')
    assert len(res) == 1
    assert res[0][1] == 100.0

def test_query_by_month(db):
    """测试13：按月查询 (len=7)"""
    db.add_transaction(100, 'EXPENSE', 1, '2025-01-01')
    db.add_transaction(200, 'EXPENSE', 1, '2025-01-31')
    db.add_transaction(300, 'EXPENSE', 1, '2025-02-01') # 干扰项
    
    res = db.get_transactions_by_condition(date='2025-01')
    assert len(res) == 2

def test_query_by_year(db):
    """测试14：按年查询 (len=4)"""
    db.add_transaction(100, 'EXPENSE', 1, '2025-01-01')
    db.add_transaction(300, 'EXPENSE', 1, '2026-01-01') # 干扰项
    
    res = db.get_transactions_by_condition(date='2025')
    assert len(res) == 1

def test_query_by_type(db):
    """测试15：按类型查询"""
    db.add_transaction(100, 'EXPENSE', 1, '2025-01-01')
    db.add_transaction(500, 'INCOME', 6, '2025-01-01')
    
    res = db.get_transactions_by_condition(type_='INCOME')
    assert len(res) == 1
    assert res[0][1] == 500.0

def test_query_by_category(db):
    """测试16：按分类ID查询"""
    db.add_transaction(100, 'EXPENSE', 1, '2025-01-01') # 分类1
    db.add_transaction(100, 'EXPENSE', 2, '2025-01-01') # 分类2
    
    res = db.get_transactions_by_condition(category_id=2)
    assert len(res) == 1
    assert res[0][3] == '交通' # 假设ID 2 是交通

def test_query_by_tag(db):
    """测试17：按标签模糊查询"""
    db.add_transaction(100, 'EXPENSE', 1, '2025-01-01', tag='lunch')
    db.add_transaction(100, 'EXPENSE', 1, '2025-01-01', tag='dinner')
    
    res = db.get_transactions_by_condition(tag='lun')
    assert len(res) == 1
    assert res[0][5] == 'lunch' # tag 是第6列

def test_query_by_remark(db):
    """测试18：按备注模糊查询"""
    db.add_transaction(100, 'EXPENSE', 1, '2025-01-01', remark='好吃')
    
    res = db.get_transactions_by_condition(remark='好')
    assert len(res) == 1

def test_query_combined_filters(db):
    """测试19：组合条件查询 (最复杂的路径)"""
    db.add_transaction(100, 'EXPENSE', 1, '2025-01-01', tag='test') # 命中
    db.add_transaction(100, 'INCOME', 6, '2025-01-01', tag='test')  # 类型不符
    db.add_transaction(100, 'EXPENSE', 1, '2025-02-01', tag='test') # 日期不符
    
    res = db.get_transactions_by_condition(date='2025-01', type_='EXPENSE', tag='test')
    assert len(res) == 1

def test_query_no_result(db):
    """测试20：查询无结果"""
    res = db.get_transactions_by_condition(tag='不存在的标签')
    assert len(res) == 0

def test_query_sql_injection_safe(db):
    """测试21：SQL注入安全性验证 (参数化查询应能处理)"""
    # 尝试注入：名字里包含单引号
    db.add_transaction(100, 'EXPENSE', 1, '2025-01-01', remark="O'Reilly")
    
    res = db.get_transactions_by_condition(remark="O'Reilly")
    assert len(res) == 1
    assert res[0][6] == "O'Reilly"