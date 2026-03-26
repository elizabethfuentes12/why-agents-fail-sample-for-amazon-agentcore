"""Hotel booking tools backed by DynamoDB.

Used locally (notebook) and as the basis for Lambda functions.
All business rule validation is in validate_booking_rules — the other
tools are pure CRUD operations.

"""

import uuid
from datetime import datetime

from strands import tool

from config import BOOKINGS_TABLE, HOTELS_TABLE, STEERING_RULES_TABLE, get_dynamodb_resource

_dynamodb = get_dynamodb_resource()
_hotels = _dynamodb.Table(HOTELS_TABLE)
_bookings = _dynamodb.Table(BOOKINGS_TABLE)
_steering_rules = _dynamodb.Table(STEERING_RULES_TABLE)


# --- Generic rule evaluator (reads rules from DynamoDB) ---

OPERATORS = {
    "gt": lambda val, thr: val > thr,
    "lt": lambda val, thr: val < thr,
    "gte": lambda val, thr: val >= thr,
    "lte": lambda val, thr: val <= thr,
    "eq": lambda val, thr: val == thr,
    "ne": lambda val, thr: val != thr,
}


def _get_rules_for_action(action: str) -> list[dict]:
    """Fetch enabled steering rules for a given action from DynamoDB."""
    response = _steering_rules.scan(
        FilterExpression="#a = :action AND #e = :enabled",
        ExpressionAttributeNames={"#a": "action", "#e": "enabled"},
        ExpressionAttributeValues={":action": action, ":enabled": True},
    )
    return response.get("Items", [])


def _build_context(action: str, params: dict) -> dict:
    """Build evaluation context from action parameters."""
    ctx = {}
    if action == "book":
        try:
            ci = datetime.fromisoformat(params.get("check_in", ""))
            co = datetime.fromisoformat(params.get("check_out", ""))
            ctx["nights"] = (co - ci).days
            ctx["days_until_checkin"] = (ci - datetime.now()).days
        except (ValueError, TypeError):
            ctx["nights"] = -1
            ctx["days_until_checkin"] = -1
        ctx["guests"] = params.get("guests", 0)
    elif action in ("confirm", "cancel"):
        booking = _bookings.get_item(
            Key={"booking_id": params.get("booking_id", "")}
        ).get("Item")
        if not booking:
            return {"_error": f"Booking '{params.get('booking_id')}' not found."}
        ctx["booking_status"] = booking["status"]
        if action == "cancel":
            try:
                ci = datetime.fromisoformat(booking["check_in"])
                ctx["days_until_checkin"] = (ci - datetime.now()).days
            except (ValueError, TypeError):
                ctx["days_until_checkin"] = 0
    return ctx


def _evaluate_rules(rules: list[dict], context: dict) -> list[dict]:
    """Evaluate rules against context. Returns list of violated rules."""
    violations = []
    for rule in rules:
        field = rule["condition_field"]
        op = rule["operator"]
        threshold = rule["threshold"]
        value = context.get(field)

        if value is None:
            continue

        # Coerce types: DynamoDB stores numbers as Decimal
        if isinstance(threshold, (int, float)) or str(threshold).lstrip("-").isdigit():
            threshold = int(threshold)
            value = int(value) if not isinstance(value, str) else value

        op_fn = OPERATORS.get(op)
        if op_fn and op_fn(value, threshold):
            violations.append(rule)
    return violations


@tool
def search_available_hotels(
    city: str = "",
    country: str = "",
    max_price: int = 0,
    min_stars: int = 0,
) -> str:
    """Search for available hotels. Filter by city, country, max price per night, or minimum stars.
    At least one filter must be provided. Returns only hotels with available rooms.

    Args:
        city: City name to search (e.g. 'Paris', 'Tokyo'). Case-insensitive.
        country: Country name to search (e.g. 'France', 'Japan'). Case-insensitive.
        max_price: Maximum price per night in USD. Use 0 to skip this filter.
        min_stars: Minimum star rating (1-5). Use 0 to skip this filter.
    """
    if not any([city, country, max_price, min_stars]):
        return "Please provide at least one filter (city, country, max_price, or min_stars)."

    filter_parts = []
    expr_values = {}
    expr_names = {}

    if city:
        filter_parts.append("contains(#city, :city)")
        expr_names["#city"] = "city"
        expr_values[":city"] = city.title()

    if country:
        filter_parts.append("contains(#country, :country)")
        expr_names["#country"] = "country"
        expr_values[":country"] = country.title()

    if max_price > 0:
        filter_parts.append("price_per_night <= :max_price")
        expr_values[":max_price"] = max_price

    if min_stars > 0:
        filter_parts.append("stars >= :min_stars")
        expr_values[":min_stars"] = min_stars

    filter_parts.append("available_rooms > :zero")
    expr_values[":zero"] = 0

    scan_kwargs = {
        "FilterExpression": " AND ".join(filter_parts),
        "ExpressionAttributeValues": expr_values,
    }
    if expr_names:
        scan_kwargs["ExpressionAttributeNames"] = expr_names

    response = _hotels.scan(**scan_kwargs)
    hotels = response.get("Items", [])

    if not hotels:
        return "No available hotels found matching your criteria."

    results = []
    for h in hotels:
        results.append(
            f"- {h['name']} ({h['city']}, {h['country']}): "
            f"{h['stars']} stars, ${int(h['price_per_night'])}/night, "
            f"{int(h['available_rooms'])} rooms available | ID: {h['hotel_id']}"
        )
    return f"Found {len(hotels)} available hotel(s):\n" + "\n".join(results)


@tool
def book_hotel(
    hotel_id: str,
    guest_name: str,
    check_in: str,
    check_out: str,
    guests: int = 1,
) -> str:
    """Book a hotel room. Creates a reservation with status PENDING.

    Args:
        hotel_id: The hotel ID from search results (e.g. 'grand-hotel-paris').
        guest_name: Full name of the guest making the reservation.
        check_in: Check-in date in ISO format (YYYY-MM-DD).
        check_out: Check-out date in ISO format (YYYY-MM-DD).
        guests: Number of guests (default 1).
    """
    hotel = _hotels.get_item(Key={"hotel_id": hotel_id}).get("Item")
    if not hotel:
        return f"Could not find hotel with ID '{hotel_id}'. Check the ID from search results."

    if int(hotel.get("available_rooms", 0)) <= 0:
        return f"No rooms available at {hotel['name']} right now."

    max_guests = int(hotel.get("max_guests_per_room", 2))
    if guests > max_guests:
        return f"{hotel['name']} accommodates up to {max_guests} guests per room. You requested {guests}."

    try:
        ci = datetime.fromisoformat(check_in)
        co = datetime.fromisoformat(check_out)
        nights = (co - ci).days
    except (ValueError, TypeError):
        return "Invalid date format. Dates must follow YYYY-MM-DD."

    if nights <= 0:
        return "Check-out date must be after check-in date."

    price_per_night = int(hotel["price_per_night"])
    total_amount = price_per_night * nights
    booking_id = f"BK-{uuid.uuid4().hex[:8].upper()}"
    now = datetime.now().isoformat()

    _bookings.put_item(
        Item={
            "booking_id": booking_id,
            "hotel_id": hotel_id,
            "hotel_name": hotel["name"],
            "guest_name": guest_name,
            "check_in": check_in,
            "check_out": check_out,
            "guests": guests,
            "nights": nights,
            "price_per_night": price_per_night,
            "total_amount": total_amount,
            "status": "PENDING",
            "created_at": now,
            "updated_at": now,
        }
    )

    _hotels.update_item(
        Key={"hotel_id": hotel_id},
        UpdateExpression="SET available_rooms = available_rooms - :one",
        ExpressionAttributeValues={":one": 1},
    )

    return (
        f"SUCCESS: Booking created.\n"
        f"  Booking ID: {booking_id}\n"
        f"  Hotel: {hotel['name']}\n"
        f"  Guest: {guest_name}\n"
        f"  Dates: {check_in} to {check_out} ({nights} nights)\n"
        f"  Guests: {guests}\n"
        f"  Total: ${total_amount}\n"
        f"  Status: PENDING\n"
        f"  Next step: process payment with process_payment."
    )


@tool
def get_booking(booking_id: str) -> str:
    """Retrieve the current status and details of a booking.

    Args:
        booking_id: The booking ID (e.g. 'BK-A1B2C3D4').
    """
    booking = _bookings.get_item(Key={"booking_id": booking_id}).get("Item")
    if not booking:
        return f"No booking matches ID '{booking_id}'."

    return (
        f"Booking {booking['booking_id']}:\n"
        f"  Hotel: {booking['hotel_name']}\n"
        f"  Guest: {booking['guest_name']}\n"
        f"  Dates: {booking['check_in']} to {booking['check_out']} ({int(booking['nights'])} nights)\n"
        f"  Guests: {int(booking['guests'])}\n"
        f"  Total: ${int(booking['total_amount'])}\n"
        f"  Status: {booking['status']}\n"
        f"  Created: {booking['created_at']}"
    )


@tool
def process_payment(booking_id: str, amount: int) -> str:
    """Process payment for a PENDING booking. Updates status to PAID.

    Args:
        booking_id: The booking ID to pay for (e.g. 'BK-A1B2C3D4').
        amount: Payment amount in USD. Must match the booking total.
    """
    booking = _bookings.get_item(Key={"booking_id": booking_id}).get("Item")
    if not booking:
        return f"Unable to find booking '{booking_id}' for payment."

    if booking["status"] != "PENDING":
        return f"Booking status is '{booking['status']}' — payment requires PENDING status."

    expected = int(booking["total_amount"])
    if amount != expected:
        return f"Payment amount ${amount} does not match the booking total of ${expected}."

    _bookings.update_item(
        Key={"booking_id": booking_id},
        UpdateExpression="SET #s = :paid, updated_at = :now",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={
            ":paid": "PAID",
            ":now": datetime.now().isoformat(),
        },
    )

    return f"SUCCESS: Payment of ${amount} processed for {booking_id}. Status: PAID."


@tool
def confirm_booking(booking_id: str) -> str:
    """Confirm a booking after payment. Updates status from PAID to CONFIRMED.

    Args:
        booking_id: The booking ID to confirm (e.g. 'BK-A1B2C3D4').
    """
    booking = _bookings.get_item(Key={"booking_id": booking_id}).get("Item")
    if not booking:
        return f"The requested booking '{booking_id}' does not exist."

    if booking["status"] != "PAID":
        return f"Cannot confirm — booking status is '{booking['status']}'. Payment must be completed first."

    _bookings.update_item(
        Key={"booking_id": booking_id},
        UpdateExpression="SET #s = :confirmed, updated_at = :now",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={
            ":confirmed": "CONFIRMED",
            ":now": datetime.now().isoformat(),
        },
    )

    return f"SUCCESS: Booking {booking_id} is now CONFIRMED."


@tool
def cancel_booking(booking_id: str) -> str:
    """Cancel a booking and return the room to inventory.

    Args:
        booking_id: The booking ID to cancel (e.g. 'BK-A1B2C3D4').
    """
    booking = _bookings.get_item(Key={"booking_id": booking_id}).get("Item")
    if not booking:
        return f"Could not locate booking '{booking_id}' for cancellation."

    if booking["status"] == "CANCELLED":
        return f"Booking {booking_id} was already cancelled previously."

    _bookings.update_item(
        Key={"booking_id": booking_id},
        UpdateExpression="SET #s = :cancelled, updated_at = :now",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={
            ":cancelled": "CANCELLED",
            ":now": datetime.now().isoformat(),
        },
    )

    _hotels.update_item(
        Key={"hotel_id": booking["hotel_id"]},
        UpdateExpression="SET available_rooms = available_rooms + :one",
        ExpressionAttributeValues={":one": 1},
    )

    return f"SUCCESS: Booking {booking_id} cancelled. Room returned to {booking['hotel_name']}."


@tool
def validate_booking_rules(
    action: str,
    guests: int = 0,
    check_in: str = "",
    check_out: str = "",
    booking_id: str = "",
) -> str:
    """Validate business rules BEFORE executing a booking action.
    ALWAYS call this before book_hotel, confirm_booking, or cancel_booking.
    Rules are loaded from the SteeringRules database and can be changed without redeploying.

    Args:
        action: The action to validate. One of: 'book', 'confirm', 'cancel'.
        guests: Number of guests (required for 'book' action).
        check_in: Check-in date YYYY-MM-DD (required for 'book' action).
        check_out: Check-out date YYYY-MM-DD (required for 'book' action).
        booking_id: Booking ID (required for 'confirm' and 'cancel' actions).
    """
    if action not in ("book", "confirm", "cancel"):
        return f"FAIL: Unrecognized action '{action}'. Valid actions are 'book', 'confirm', or 'cancel'."

    rules = _get_rules_for_action(action)
    if not rules:
        return f"PASS: No rules configured for '{action}'. Proceed."

    params = {
        "guests": guests,
        "check_in": check_in,
        "check_out": check_out,
        "booking_id": booking_id,
    }
    context = _build_context(action, params)

    if "_error" in context:
        return f"FAIL: {context['_error']}"

    violated = _evaluate_rules(rules, context)

    if not violated:
        return f"PASS: All {len(rules)} rules passed for '{action}'. Proceed."

    lines = []
    for v in violated:
        lines.append(f"- {v['fail_message']}\n  STEER: {v['steer_message']}")
    return f"FAIL: {len(violated)} rule(s) violated for '{action}':\n" + "\n".join(lines)


ALL_TOOLS = [
    search_available_hotels,
    book_hotel,
    get_booking,
    process_payment,
    confirm_booking,
    cancel_booking,
    validate_booking_rules,
]
