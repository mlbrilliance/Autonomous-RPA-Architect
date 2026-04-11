"""UiPath Orchestrator activity generators for XAML.

Generators for queue items, assets, and credentials.
"""

from __future__ import annotations

from rpa_architect.generators.base import indent, quote_attr, unique_id
from rpa_architect.generators.registry import register_generator


# ---------------------------------------------------------------------------
# Generators
# ---------------------------------------------------------------------------

def gen_add_queue_item(
    queue_name: str,
    item_data: dict[str, str],
    priority: str = "Normal",
    display_name: str = "Add Queue Item",
) -> str:
    """Generate ``<ui:AddQueueItem>`` activity XAML.

    Parameters
    ----------
    queue_name:
        Name of the Orchestrator queue.
    item_data:
        Dictionary of specific-content key/value pairs.
    priority:
        Queue item priority (``Normal``, ``High``, ``Low``).
    """
    ref = unique_id()
    data_parts: list[str] = []
    for key, value in item_data.items():
        data_parts.append(
            f'      <ui:QueueItemData Name="{quote_attr(key)}"'
            f' Value="{quote_attr(value)}" />'
        )
    data_xml = "\n".join(data_parts)
    return (
        f'<ui:AddQueueItem QueueName="{quote_attr(queue_name)}"'
        f' Priority="{quote_attr(priority)}"'
        f' DisplayName="{quote_attr(display_name)}"'
        f' sap2010:WorkflowViewState.IdRef="AddQueueItem_{ref}">\n'
        f'  <ui:AddQueueItem.DictionaryCollection>\n'
        f'    <scg:List x:TypeArguments="ui:QueueItemData">\n'
        f'{data_xml}\n'
        f'    </scg:List>\n'
        f'  </ui:AddQueueItem.DictionaryCollection>\n'
        f'</ui:AddQueueItem>'
    )


def gen_bulk_add_queue_items(
    queue_name: str,
    datatable: str,
    display_name: str = "Bulk Add Queue Items",
) -> str:
    """Generate ``<ui:BulkAddQueueItems>`` activity XAML."""
    ref = unique_id()
    return (
        f'<ui:BulkAddQueueItems QueueName="{quote_attr(queue_name)}"'
        f' DataTable="[{quote_attr(datatable)}]"'
        f' DisplayName="{quote_attr(display_name)}"'
        f' sap2010:WorkflowViewState.IdRef="BulkAddQueueItems_{ref}" />'
    )


def gen_get_queue_item(
    queue_name: str,
    output: str,
    display_name: str = "Get Transaction Item",
) -> str:
    """Generate ``<ui:GetQueueItem>`` (Get Transaction Item) activity XAML."""
    ref = unique_id()
    return (
        f'<ui:GetQueueItem QueueName="{quote_attr(queue_name)}"'
        f' TransactionItem="[{quote_attr(output)}]"'
        f' DisplayName="{quote_attr(display_name)}"'
        f' sap2010:WorkflowViewState.IdRef="GetQueueItem_{ref}" />'
    )


def gen_get_robot_asset(
    asset_name: str,
    output: str,
    display_name: str = "Get Asset",
) -> str:
    """Generate ``<ui:GetRobotAsset>`` activity XAML."""
    ref = unique_id()
    return (
        f'<ui:GetRobotAsset AssetName="{quote_attr(asset_name)}"'
        f' Value="[{quote_attr(output)}]"'
        f' DisplayName="{quote_attr(display_name)}"'
        f' sap2010:WorkflowViewState.IdRef="GetRobotAsset_{ref}" />'
    )


def gen_get_robot_credential(
    asset_name: str,
    username_output: str,
    password_output: str,
    display_name: str = "Get Credential",
) -> str:
    """Generate ``<ui:GetRobotCredential>`` activity XAML."""
    ref = unique_id()
    return (
        f'<ui:GetRobotCredential AssetName="{quote_attr(asset_name)}"'
        f' Username="[{quote_attr(username_output)}]"'
        f' Password="[{quote_attr(password_output)}]"'
        f' DisplayName="{quote_attr(display_name)}"'
        f' sap2010:WorkflowViewState.IdRef="GetRobotCredential_{ref}" />'
    )


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

register_generator("add_queue_item", gen_add_queue_item, "Add Queue Item",
                   "Orchestrator", "Add an item to an Orchestrator queue")
register_generator("bulk_add_queue_items", gen_bulk_add_queue_items,
                   "Bulk Add Queue Items", "Orchestrator",
                   "Bulk-add items from a DataTable to an Orchestrator queue")
register_generator("get_queue_item", gen_get_queue_item, "Get Transaction Item",
                   "Orchestrator", "Get the next transaction item from a queue")
register_generator("get_robot_asset", gen_get_robot_asset, "Get Asset",
                   "Orchestrator", "Retrieve an Orchestrator asset value")
register_generator("get_robot_credential", gen_get_robot_credential, "Get Credential",
                   "Orchestrator", "Retrieve credential (username + password) from Orchestrator")
