import asyncio
import time
import inspect
import logging
from enum import Enum
from typing import Callable, Any, Optional

logger = logging.getLogger("quant.engine.circuit_breaker")


class CircuitState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreaker:
    """
    Defensive In-Process Circuit Breaker for low-latency resilient microservice execution.
    - CLOSED: Normal operation. Errors/timeouts increment failure counter.
    - OPEN: Fast 0ms fallback return without executing target function for recovery_timeout seconds.
    - HALF_OPEN: Probe request allowed after recovery_timeout. Success resets to CLOSED; failure trips back to OPEN.
    """

    def __init__(self, failure_threshold: int = 3, recovery_timeout: float = 30.0):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_state_change = time.monotonic()
        self._lock = asyncio.Lock()

    async def _resolve_fallback(self, fallback: Any) -> Any:
        if callable(fallback):
            if inspect.iscoroutinefunction(fallback):
                return await fallback()
            res = fallback()
            if inspect.isawaitable(res):
                return await res
            return res
        return fallback

    async def call(
        self,
        func: Callable,
        *args,
        fallback: Any = None,
        timeout: float = 4.5,
        **kwargs
    ) -> Any:
        """
        Executes func(*args, **kwargs) guarded by timeout and circuit state transitions.
        """
        now = time.monotonic()

        # 1. State check & transitions
        async with self._lock:
            if self.state == CircuitState.OPEN:
                if (now - self.last_state_change) < self.recovery_timeout:
                    logger.warning(
                        f"[CircuitBreaker OPEN] Bypassing call to {getattr(func, '__name__', str(func))} "
                        f"(cooldown remaining: {self.recovery_timeout - (now - self.last_state_change):.1f}s)"
                    )
                    return await self._resolve_fallback(fallback)
                else:
                    self.state = CircuitState.HALF_OPEN
                    self.last_state_change = now
                    logger.info(f"[CircuitBreaker HALF_OPEN] Probing {getattr(func, '__name__', str(func))}")

        # 2. Execute target function with timeout
        try:
            if inspect.iscoroutinefunction(func):
                coro = func(*args, **kwargs)
            else:
                coro = asyncio.to_thread(func, *args, **kwargs)

            result = await asyncio.wait_for(coro, timeout=timeout)

            # 3. Handle success
            async with self._lock:
                if self.state == CircuitState.HALF_OPEN:
                    logger.info("[CircuitBreaker CLOSED] Probe succeeded. Resetting circuit to CLOSED.")
                    self.state = CircuitState.CLOSED
                    self.failure_count = 0
                    self.last_state_change = time.monotonic()
                elif self.state == CircuitState.CLOSED:
                    self.failure_count = 0

            return result

        except Exception as ex:
            # 4. Handle failure or timeout
            async with self._lock:
                self.failure_count += 1
                logger.warning(
                    f"[CircuitBreaker FAILURE] Call to {getattr(func, '__name__', str(func))} failed "
                    f"({type(ex).__name__}: {ex}). Failure count: {self.failure_count}/{self.failure_threshold}, State: {self.state.value}"
                )

                if self.state == CircuitState.HALF_OPEN or self.failure_count >= self.failure_threshold:
                    self.state = CircuitState.OPEN
                    self.last_state_change = time.monotonic()
                    logger.error(
                        f"[CircuitBreaker OPEN] Circuit tripped to OPEN for {self.recovery_timeout}s "
                        f"due to failure/timeout."
                    )

            return await self._resolve_fallback(fallback)
