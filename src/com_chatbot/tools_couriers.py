"""Tools for courier management (Carrier Operation Manager)."""

from strands import tool

from .pmd_client import PMDClientError, client


@tool
def add_courier(courier_name: str, courier_code: str = "") -> str:
    """Add a new courier/delivery agent to the system.

    This is a modification action - requires explicit user confirmation before executing.

    Args:
        courier_name: The name of the courier company to add (e.g. "DHL", "UPS", "Hermes").
        courier_code: Optional courier code/identifier.

    Returns:
        Confirmation that the courier was added, or an error message.
    """
    name = (courier_name or "").strip()
    if not name:
        return "Error: courier_name is required."

    code = (courier_code or "").strip()

    payload = {"name": name}
    if code:
        payload["code"] = code

    try:
        result = client.post("/api/delivery-agents", json_body=payload)
    except PMDClientError as exc:
        return f"Error: failed to add courier '{name}' (HTTP {exc.status_code})."

    agent_id = ""
    if isinstance(result, dict):
        agent_id = result.get("id") or result.get("deliveryAgentId") or ""

    id_suffix = f" (ID: {agent_id})" if agent_id else ""
    return f"Courier '{name}' has been added successfully{id_suffix}."


@tool
def remove_courier(courier_name: str) -> str:
    """Remove a courier/delivery agent from the system.

    This is a modification action - requires explicit user confirmation before executing.

    Args:
        courier_name: The name of the courier company to remove.

    Returns:
        Confirmation that the courier was removed, or an error message.
    """
    name = (courier_name or "").strip()
    if not name:
        return "Error: courier_name is required."

    # Look up courier by name to find its ID
    try:
        agents = client.get("/api/delivery-agents")
    except PMDClientError as exc:
        return f"Error: unable to retrieve courier list (HTTP {exc.status_code})."

    if isinstance(agents, dict):
        agents = agents.get("items") or agents.get("deliveryAgents") or agents.get("data") or []
    if not isinstance(agents, list):
        return "Error: unexpected response format from delivery agents API."

    # Find matching courier (case-insensitive)
    match = None
    for agent in agents:
        if not isinstance(agent, dict):
            continue
        agent_name = str(agent.get("name") or "").strip()
        if agent_name.lower() == name.lower():
            match = agent
            break

    if not match:
        available = ", ".join(
            str(a.get("name", "?")).strip()
            for a in agents
            if isinstance(a, dict) and a.get("name")
        )
        return f"No courier found with name '{name}'. Available couriers: {available or 'none'}."

    agent_id = match.get("id") or match.get("deliveryAgentId")
    if not agent_id:
        return f"Unable to determine ID for courier '{name}'."

    try:
        client.delete(f"/api/delivery-agents/{agent_id}")
    except PMDClientError as exc:
        return f"Error: failed to remove courier '{name}' (HTTP {exc.status_code})."

    return f"Courier '{name}' has been removed successfully."
