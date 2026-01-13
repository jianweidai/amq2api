
import pytest
from unittest.mock import MagicMock, patch
import time
from src.auth.account_distributor import AccountDistributor, NoAccountAvailableError, get_account_distributor

class TestAccountDistributor:
    
    @pytest.fixture
    def distributor(self):
        # 重置单例
        AccountDistributor._instance = None
        return AccountDistributor()

    @pytest.fixture
    def mock_accounts(self):
        return [
            {'id': 'acc_1', 'enabled': True, 'label': 'Account 1', 'weight': 50},
            {'id': 'acc_2', 'enabled': True, 'label': 'Account 2', 'weight': 50},
            {'id': 'acc_3', 'enabled': True, 'label': 'Account 3', 'weight': 100} # 高权重
        ]

    def test_singleton_pattern(self):
        d1 = get_account_distributor()
        d2 = get_account_distributor()
        assert d1 is d2

    def test_calculate_score_new_account(self, distributor):
        account = {'id': 'new_acc', 'weight': 50}
        score = distributor.calculate_score(account)
        # 新账号: success_rate=1.0 * 40, cooldown=30, balance=30 => 100
        assert score == 100.0

    def test_calculate_score_failure_penalty(self, distributor):
        account = {'id': 'fail_acc', 'weight': 50}
        # 模拟失败多次
        for _ in range(15):
            distributor.record_usage('fail_acc', success=False)
        
        # 模拟最近使用过，并且使用了15次
        record = distributor._usage_records['fail_acc']
        record.last_used = time.time() * 1000
        record.recent_usage_count = 15
        
        score = distributor.calculate_score(account)
        # success_rate=0.0 * 20 = 0 (total > 10, low rate penalty)
        # cooldown=5 (recently used < 30s)
        # balance=max(0, 30 - 15*10) = 0
        # total = 5
        assert score == 5.0

    def test_calculate_score_cooldown_penalty(self, distributor):
        account = {'id': 'active_acc', 'weight': 50}
        # 刚刚使用过
        distributor.record_usage('active_acc', success=True)
        # 模拟刚用完
        record = distributor._usage_records['active_acc']
        record.last_used = time.time() * 1000
        # 如果 record_usage 不更新 recent_count，这里需要手动更新以确保测试 balance score
        record.recent_usage_count = 1
        
        score = distributor.calculate_score(account)
        # success_rate=1.0 * 40 = 40
        # cooldown=5 (< 30s)
        # balance=max(0, 30 - 1*10) = 20
        # total = 65
        assert score == 65.0

    @patch('src.auth.account_distributor.list_enabled_accounts')
    @patch('src.auth.account_distributor.is_account_in_cooldown')
    def test_get_best_account_selection(self, mock_is_cooldown, mock_list_accounts, distributor, mock_accounts):
        mock_list_accounts.return_value = mock_accounts
        mock_is_cooldown.return_value = False
        
        # 运行多次，验证是否能选到账号
        selected = distributor.get_best_account()
        assert selected in mock_accounts
        
        # 验证 usage record 是否更新
        record = distributor._usage_records[selected['id']]
        assert record.recent_usage_count == 1
        assert record.last_used > 0

    @patch('src.auth.account_distributor.list_enabled_accounts')
    def test_no_accounts_available(self, mock_list_accounts, distributor):
        mock_list_accounts.return_value = []
        with pytest.raises(NoAccountAvailableError):
            distributor.get_best_account()

    @patch('src.auth.account_distributor.list_enabled_accounts')
    @patch('src.auth.account_distributor.is_account_in_cooldown')
    def test_all_accounts_in_cooldown_fallback(self, mock_is_cooldown, mock_list_accounts, distributor, mock_accounts):
        mock_list_accounts.return_value = mock_accounts
        mock_is_cooldown.return_value = True # 模拟所有账号都在冷却
        
        # 即使所有都在冷却，也应该返回一个（作为兜底）
        selected = distributor.get_best_account()
        assert selected is not None
        assert selected in mock_accounts

    def test_record_usage(self, distributor):
        distributor.record_usage('acc_1', True)
        distributor.record_usage('acc_1', False)
        
        stats = distributor.get_stats()
        acc_stats = stats['accounts']['acc_1']
        
        assert acc_stats['success_count'] == 1
        assert acc_stats['fail_count'] == 1
        assert acc_stats['success_rate'] == 0.5
