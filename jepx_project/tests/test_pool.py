"""§3.7 ConnectionPool のユニットテスト

テスト観点:
- acquire: Idle再利用・新規作成・上限超過・死んだIdle接続の破棄
- release: 生存接続→Idle返却・死んだ接続→close
- close_all: 全接続クローズ
- get_status: active/idle/max
- get_idle_connections: コピー返却
"""
import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import os
import sys

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.dev')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import django
django.setup()

from apps.jepx_client.pool import ConnectionPool
from apps.jepx_client.connection import JepxConnection


def _mock_conn(alive: bool = True) -> MagicMock:
    """モック JepxConnection を作成する"""
    conn = MagicMock(spec=JepxConnection)
    conn.is_alive.return_value = alive
    conn.close = AsyncMock()
    conn.connect = AsyncMock()
    conn.send = AsyncMock()
    conn.receive = AsyncMock()
    conn.last_used = 0.0
    return conn


class TestConnectionPoolAcquire(unittest.IsolatedAsyncioTestCase):
    """acquire() のテスト"""

    def _pool(self, max_connections=5) -> ConnectionPool:
        return ConnectionPool('127.0.0.1', 8888, max_connections)

    async def test_acquire_creates_new_when_idle_empty(self):
        """Idleが空のとき新規接続を作成すること"""
        pool = self._pool()
        mock_conn = _mock_conn()

        with patch('apps.jepx_client.pool.JepxConnection', return_value=mock_conn):
            conn = await pool.acquire()

        self.assertIs(conn, mock_conn)
        mock_conn.connect.assert_awaited_once_with('127.0.0.1', 8888)
        self.assertIn(conn, pool._in_use)
        self.assertEqual(len(pool._idle), 0)

    async def test_acquire_reuses_alive_idle_connection(self):
        """生存中のIdle接続が再利用されること"""
        pool = self._pool()
        conn = _mock_conn(alive=True)
        pool._idle.append(conn)

        result = await pool.acquire()

        self.assertIs(result, conn)
        self.assertEqual(len(pool._idle), 0)
        self.assertIn(conn, pool._in_use)
        # connect は呼ばれない
        conn.connect.assert_not_awaited()

    async def test_acquire_discards_dead_idle_creates_new(self):
        """死んだIdle接続は破棄し, 新規接続を作成すること"""
        pool = self._pool()
        dead = _mock_conn(alive=False)
        pool._idle.append(dead)

        new_conn = _mock_conn(alive=True)
        with patch('apps.jepx_client.pool.JepxConnection', return_value=new_conn):
            result = await pool.acquire()

        dead.close.assert_awaited_once()
        self.assertIs(result, new_conn)

    async def test_acquire_multiple_dead_idle_then_new(self):
        """複数の死んだIdle接続をスキップして新規作成すること"""
        pool = self._pool()
        dead1 = _mock_conn(alive=False)
        dead2 = _mock_conn(alive=False)
        pool._idle = [dead1, dead2]

        new_conn = _mock_conn(alive=True)
        with patch('apps.jepx_client.pool.JepxConnection', return_value=new_conn):
            result = await pool.acquire()

        dead1.close.assert_awaited_once()
        dead2.close.assert_awaited_once()
        self.assertIs(result, new_conn)

    async def test_acquire_raises_at_max_connections(self):
        """使用中接続数が上限に達した場合 RuntimeError が発生すること"""
        pool = self._pool(max_connections=2)
        conn1 = _mock_conn()
        conn2 = _mock_conn()
        pool._in_use = {conn1, conn2}

        with self.assertRaises(RuntimeError) as ctx:
            await pool.acquire()

        self.assertIn('2', str(ctx.exception))

    async def test_acquire_increments_in_use_count(self):
        """acquire 後に in_use カウントが増えること"""
        pool = self._pool()
        mock_conn = _mock_conn()

        with patch('apps.jepx_client.pool.JepxConnection', return_value=mock_conn):
            await pool.acquire()

        self.assertEqual(len(pool._in_use), 1)

    async def test_acquire_at_max_minus_one_succeeds(self):
        """上限の1つ前ならまだ作成できること"""
        pool = self._pool(max_connections=3)
        existing = _mock_conn()
        pool._in_use = {existing}  # 1/3 in use

        new_conn = _mock_conn()
        with patch('apps.jepx_client.pool.JepxConnection', return_value=new_conn):
            result = await pool.acquire()

        self.assertIs(result, new_conn)


class TestConnectionPoolRelease(unittest.IsolatedAsyncioTestCase):
    """release() のテスト"""

    def _pool(self) -> ConnectionPool:
        return ConnectionPool('127.0.0.1', 8888, 5)

    async def test_release_alive_conn_returns_to_idle(self):
        """生存中の接続は Idle リストに戻ること"""
        pool = self._pool()
        conn = _mock_conn(alive=True)
        pool._in_use.add(conn)

        await pool.release(conn)

        self.assertNotIn(conn, pool._in_use)
        self.assertIn(conn, pool._idle)
        conn.close.assert_not_awaited()

    async def test_release_dead_conn_closes_and_not_in_idle(self):
        """死んだ接続は close され Idle には戻らないこと"""
        pool = self._pool()
        conn = _mock_conn(alive=False)
        pool._in_use.add(conn)

        await pool.release(conn)

        self.assertNotIn(conn, pool._in_use)
        self.assertNotIn(conn, pool._idle)
        conn.close.assert_awaited_once()

    async def test_release_conn_not_in_use_still_works(self):
        """in_use に含まれていない接続のリリースでもエラーにならないこと"""
        pool = self._pool()
        conn = _mock_conn(alive=True)

        # discard は例外を出さない
        await pool.release(conn)
        self.assertIn(conn, pool._idle)


class TestConnectionPoolStatus(unittest.IsolatedAsyncioTestCase):
    """get_status / get_idle_connections のテスト"""

    def _pool(self, max_connections=5) -> ConnectionPool:
        return ConnectionPool('127.0.0.1', 8888, max_connections)

    async def test_get_status_initial(self):
        """初期状態は active=0, idle=0"""
        pool = self._pool(max_connections=5)
        status = pool.get_status()
        self.assertEqual(status['active'], 0)
        self.assertEqual(status['idle'], 0)
        self.assertEqual(status['max'], 5)

    async def test_get_status_after_acquire_and_release(self):
        """acquire → release 後の状態確認"""
        pool = self._pool()
        mock_conn = _mock_conn()

        with patch('apps.jepx_client.pool.JepxConnection', return_value=mock_conn):
            conn = await pool.acquire()

        s = pool.get_status()
        self.assertEqual(s['active'], 1)
        self.assertEqual(s['idle'], 0)

        await pool.release(conn)
        s = pool.get_status()
        self.assertEqual(s['active'], 0)
        self.assertEqual(s['idle'], 1)

    async def test_get_idle_connections_returns_copy(self):
        """get_idle_connections は内部リストのコピーを返すこと"""
        pool = self._pool()
        conn = _mock_conn()
        pool._idle = [conn]

        idle = pool.get_idle_connections()
        self.assertEqual(len(idle), 1)
        self.assertIs(idle[0], conn)
        # 別オブジェクトであることを確認
        self.assertIsNot(idle, pool._idle)

    async def test_get_idle_connections_empty(self):
        """Idle が空の時は空リストを返すこと"""
        pool = self._pool()
        idle = pool.get_idle_connections()
        self.assertEqual(idle, [])


class TestConnectionPoolCloseAll(unittest.IsolatedAsyncioTestCase):
    """close_all() のテスト"""

    async def test_close_all_closes_idle_and_in_use(self):
        """close_all で Idle・使用中の全接続が close されること"""
        pool = ConnectionPool('127.0.0.1', 8888, 5)
        idle_conn = _mock_conn()
        active_conn = _mock_conn()
        pool._idle = [idle_conn]
        pool._in_use = {active_conn}

        await pool.close_all()

        idle_conn.close.assert_awaited_once()
        active_conn.close.assert_awaited_once()
        self.assertEqual(len(pool._idle), 0)
        self.assertEqual(len(pool._in_use), 0)

    async def test_close_all_empty_pool(self):
        """空のプールで close_all を呼んでもエラーにならないこと"""
        pool = ConnectionPool('127.0.0.1', 8888, 5)
        await pool.close_all()  # 例外なし

    async def test_close_all_then_acquire_raises_runtime(self):
        """close_all 後に新規接続を作ることは可能だが、状態がリセットされていること"""
        pool = ConnectionPool('127.0.0.1', 8888, 1)
        conn = _mock_conn()
        pool._in_use = {conn, _mock_conn()}  # 上限超過

        await pool.close_all()

        # close_all 後は in_use が空になるので再び acquire できる
        new_conn = _mock_conn()
        with patch('apps.jepx_client.pool.JepxConnection', return_value=new_conn):
            result = await pool.acquire()
        self.assertIs(result, new_conn)


if __name__ == '__main__':
    unittest.main()
