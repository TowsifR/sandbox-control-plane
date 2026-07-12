from temporalio.client import Client
from temporalio.contrib.pydantic import pydantic_data_converter

from .config import get_settings


async def get_temporal_client() -> Client:
    settings = get_settings()
    # pydantic_data_converter lets pydantic models pass as workflow/activity args.
    return await Client.connect(
        settings.temporal_address,
        namespace=settings.temporal_namespace,
        data_converter=pydantic_data_converter,
    )
