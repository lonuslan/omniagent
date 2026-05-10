"""Tests for FileLockManager."""

import asyncio

import pytest

from omniagent.runtime.filelock import FileLockManager


class TestFileLockManager:
    @pytest.fixture
    def manager(self):
        return FileLockManager(default_timeout=2.0)

    @pytest.mark.asyncio
    async def test_concurrent_reads_allowed(self, manager):
        """Multiple agents can read the same file simultaneously."""
        results = []

        async def reader(agent_id: str):
            async with manager.read_lock("test.txt", agent_id):
                results.append(f"{agent_id}_entered")
                await asyncio.sleep(0.1)
                results.append(f"{agent_id}_done")

        await asyncio.gather(reader("a1"), reader("a2"))
        # Both should have entered before either finished
        assert "a1_entered" in results
        assert "a2_entered" in results

    @pytest.mark.asyncio
    async def test_write_blocks_read(self, manager):
        """A write lock blocks read locks."""
        order = []

        async def writer():
            async with manager.write_lock("test.txt", "w1"):
                order.append("write_start")
                await asyncio.sleep(0.15)
                order.append("write_end")

        async def reader():
            await asyncio.sleep(0.05)  # Let writer start first
            async with manager.read_lock("test.txt", "r1"):
                order.append("read_start")

        await asyncio.gather(writer(), reader())
        # Read must start after write ends
        assert order.index("read_start") > order.index("write_end")

    @pytest.mark.asyncio
    async def test_write_blocks_write(self, manager):
        """Two write locks are exclusive."""
        order = []

        async def writer(agent_id: str, delay: float):
            await asyncio.sleep(delay)
            async with manager.write_lock("test.txt", agent_id):
                order.append(f"{agent_id}_start")
                await asyncio.sleep(0.05)
                order.append(f"{agent_id}_end")

        await asyncio.gather(writer("w1", 0), writer("w2", 0.02))
        # w2 must wait for w1 to finish
        assert order.index("w1_end") < order.index("w2_start")

    @pytest.mark.asyncio
    async def test_read_blocks_write(self, manager):
        """An active read lock blocks write locks."""
        order = []

        async def reader():
            async with manager.read_lock("test.txt", "r1"):
                order.append("read_start")
                await asyncio.sleep(0.15)
                order.append("read_end")

        async def writer():
            await asyncio.sleep(0.05)
            async with manager.write_lock("test.txt", "w1"):
                order.append("write_start")

        await asyncio.gather(reader(), writer())
        assert order.index("write_start") > order.index("read_end")

    @pytest.mark.asyncio
    async def test_different_files_independent(self, manager):
        """Locks on different files don't interfere."""
        entered = []

        async def writer_a():
            async with manager.write_lock("a.txt", "w1"):
                entered.append("a")
                await asyncio.sleep(0.1)

        async def writer_b():
            async with manager.write_lock("b.txt", "w2"):
                entered.append("b")
                await asyncio.sleep(0.1)

        await asyncio.gather(writer_a(), writer_b())
        # Both should run (not blocked by each other)
        assert len(entered) == 2

    @pytest.mark.asyncio
    async def test_timeout_raises(self, manager):
        """Lock acquisition times out if held too long."""
        mgr = FileLockManager(default_timeout=0.3)

        async def hold_write():
            async with mgr.write_lock("test.txt", "w1"):
                await asyncio.sleep(1.0)

        async def try_write():
            await asyncio.sleep(0.05)
            with pytest.raises(TimeoutError):
                async with mgr.write_lock("test.txt", "w2"):
                    pass

        await asyncio.gather(hold_write(), try_write())

    @pytest.mark.asyncio
    async def test_lock_info(self, manager):
        """get_lock_info returns current state."""
        async with manager.read_lock("test.txt", "a1"):
            info = manager.get_lock_info("test.txt")
            assert info is not None
            assert "a1" in info.readers
            assert info.writer is None

    @pytest.mark.asyncio
    async def test_get_all_locked_files(self, manager):
        """get_all_locked_files returns only active locks."""
        async with manager.write_lock("a.txt", "w1"):
            async with manager.read_lock("b.txt", "r1"):
                locked = manager.get_all_locked_files()
                paths = [f.path for f in locked]
                assert any("a.txt" in p for p in paths)
                assert any("b.txt" in p for p in paths)

    @pytest.mark.asyncio
    async def test_lock_released_on_exception(self, manager):
        """Lock is properly released if an exception occurs."""
        with pytest.raises(ValueError):
            async with manager.write_lock("test.txt", "w1"):
                raise ValueError("boom")

        # File should be unlocked now
        info = manager.get_lock_info("test.txt")
        assert info is not None
        assert info.writer is None
