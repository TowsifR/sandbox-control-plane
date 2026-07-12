import asyncio
from datetime import timedelta

from temporalio import workflow
from temporalio.exceptions import ApplicationError

with workflow.unsafe.imports_passed_through():
    from .activities import check_sandbox_ready, create_sandbox_claim, delete_sandbox_claim
    from .models import LifecycleParams

_ACTIVITY_TIMEOUT = timedelta(seconds=30)


@workflow.defn
class SandboxLifecycle:
    def __init__(self) -> None:
        self._phase = "provisioning"
        self._delete_requested = False

    @workflow.run
    async def run(self, params: LifecycleParams) -> None:
        await workflow.execute_activity(
            create_sandbox_claim, params, start_to_close_timeout=_ACTIVITY_TIMEOUT
        )
        # Cleanup must run on every exit past this point (TTL, delete, or ready-timeout).
        try:
            # bounded so a stuck provision can't hang forever
            for _ in range(60):
                if await workflow.execute_activity(
                    check_sandbox_ready, params.name, start_to_close_timeout=_ACTIVITY_TIMEOUT
                ):
                    break
                await workflow.sleep(timedelta(seconds=3))
            else:
                raise ApplicationError("sandbox never became ready")

            self._phase = "running"
            # Live until the TTL elapses or a delete is requested, whichever comes first.
            try:
                await workflow.wait_condition(lambda: self._delete_requested, timeout=params.ttl)
            except asyncio.TimeoutError:
                pass  # TTL elapsed
        finally:
            self._phase = "deleting"
            await workflow.execute_activity(
                delete_sandbox_claim, params.name, start_to_close_timeout=_ACTIVITY_TIMEOUT
            )
            self._phase = "deleted"

    @workflow.signal
    def request_delete(self) -> None:
        self._delete_requested = True

    @workflow.query
    def phase(self) -> str:
        return self._phase
