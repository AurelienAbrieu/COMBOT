"""Tools for report generation (Carrier Operation Manager)."""

from strands import tool

from .pmd_client import PMDClientError, client


@tool
def generate_report(report_type: str, email: str, period: str = "last_month") -> str:
    """Launch a report generation and send it by email.

    Generates a report of the specified type and sends it to the provided email address.
    This is an action that triggers an asynchronous process on the server.

    Args:
        report_type: Type of report to generate. Examples: "parcel_drop", "occupation_rate",
                     "activity_summary", "carrier_performance".
        email: Email address to send the report to.
        period: Time period for the report. Examples: "last_week", "last_month",
                "last_quarter", "since_beginning_of_month", or a custom range like
                "2026-04-01 to 2026-04-30".

    Returns:
        Confirmation that the report generation was launched, or an error message.
    """
    rtype = (report_type or "").strip()
    target_email = (email or "").strip()
    report_period = (period or "last_month").strip()

    if not rtype:
        return "Error: report_type is required. Available types: parcel_drop, occupation_rate, activity_summary, carrier_performance."
    if not target_email:
        return "Error: email address is required to send the report."
    if "@" not in target_email:
        return f"Error: '{target_email}' does not look like a valid email address."

    payload = {
        "reportType": rtype,
        "email": target_email,
        "period": report_period,
    }

    try:
        result = client.post("/api/reports/generate", json_body=payload)
    except PMDClientError as exc:
        return f"Error: failed to launch report generation (HTTP {exc.status_code})."

    report_id = ""
    if isinstance(result, dict):
        report_id = result.get("id") or result.get("reportId") or ""

    id_suffix = f" (Report ID: {report_id})" if report_id else ""
    return (
        f"Report '{rtype}' for period '{report_period}' has been launched. "
        f"It will be sent to {target_email} once generated{id_suffix}."
    )
