import asyncio

from temporalio.worker import Worker

from .core.config import get_settings
from .core.temporal import get_temporal_client
from .sandboxes import activities
from .sandboxes.workflows import SandboxLifecycle


async def main() -> None:
    settings = get_settings()
    client = await get_temporal_client()
    worker = Worker(
        client,
        task_queue=settings.task_queue,
        workflows=[SandboxLifecycle],
        activities=[
            activities.create_sandbox_claim,
            activities.check_sandbox_ready,
            activities.delete_sandbox_claim,
        ],
    )
    print(f"worker started on task queue '{settings.task_queue}'")
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
