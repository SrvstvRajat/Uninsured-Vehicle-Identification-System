"""
Command-line interface for the federated vehicle mediator.

Every lookup is a live federated query. There is no vehicle_master.pkl.
"""

from mediator import query_vehicle


def print_result(result: dict) -> None:
    print("\n" + "=" * 75)
    print("FEDERATED VEHICLE 360° PROFILE")
    print("=" * 75)

    if not result.get("found"):
        print(f"Plate: {result.get('plate')}")
        print(result.get("message", "No result."))
        return

    fields = [
        ("Plate", result.get("plate")),
        ("Vehicle Key", result.get("vehicle_key")),
        ("Make", result.get("make")),
        ("Model", result.get("model")),
        ("Color", result.get("color")),
        ("Owner", result.get("owner")),
        ("Registration Date", result.get("registration_date")),
        ("RTO Office", result.get("rto_office")),
        ("Renewal Date", result.get("renewal_date")),
        ("Insurer", result.get("insurer")),
        ("Policy No.", result.get("policy_no")),
        ("Policy Start", result.get("policy_start_date")),
        ("Policy End", result.get("policy_end_date")),
        ("Theft Date", result.get("theft_date")),
        ("Theft Status", result.get("theft_status")),
        ("Shredded Date", result.get("shredded_date")),
        ("Decision", result.get("decision")),
        ("Trust Score", result.get("trust_score")),
        ("Queried At", result.get("queried_at")),
    ]

    for name, value in fields:
        print(f"{name:20s}: {value if value not in (None, '') else '—'}")

    print("\nFlags:")
    for flag in result.get("flags") or ["None"]:
        print(f"  - {flag}")

    if result.get("source_warnings"):
        print("\nSource warnings:")
        for warning in result["source_warnings"]:
            print(f"  - {warning}")

    print("\nSource status:")
    for source, status in result.get("source_status", {}).items():
        state = "AVAILABLE" if status["available"] else "UNAVAILABLE"
        print(f"  - {source}: {state}")
        if not status["available"]:
            print(f"    error: {status['error']}")

    print("\nIntegration mode:")
    print(f"  {result.get('integration_mode')}")
    print("  Data is integrated at query time; no materialized vehicle master is used.")


if __name__ == "__main__":
    print("Federated Uninsured Vehicle Lookup")
    print("Every lookup queries the independent source databases live.")
    print("Type a plate number or 'quit'.")

    while True:
        q = input("\nEnter plate number: ").strip()

        if q.lower() == "quit":
            break

        if not q:
            print("Please enter a plate number.")
            continue

        print_result(query_vehicle(q))
