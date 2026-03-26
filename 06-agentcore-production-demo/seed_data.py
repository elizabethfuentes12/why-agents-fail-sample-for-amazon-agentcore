"""Seed DynamoDB Hotels table with sample data.

Prerequisites:
    - DynamoDB tables must exist (run 'cdk deploy' first)
    - AWS credentials configured

Usage:
    uv run python seed_data.py
"""

from config import HOTELS_TABLE, STEERING_RULES_TABLE, get_dynamodb_resource

HOTELS = [
    {
        "hotel_id": "grand-hotel-paris",
        "name": "Grand Hotel Paris",
        "city": "Paris",
        "country": "France",
        "stars": 5,
        "price_per_night": 350,
        "max_guests_per_room": 4,
        "total_rooms": 50,
        "available_rooms": 12,
    },
    {
        "hotel_id": "budget-inn-barcelona",
        "name": "Budget Inn Barcelona",
        "city": "Barcelona",
        "country": "Spain",
        "stars": 2,
        "price_per_night": 65,
        "max_guests_per_room": 2,
        "total_rooms": 30,
        "available_rooms": 8,
    },
    {
        "hotel_id": "tokyo-tower-hotel",
        "name": "Tokyo Tower Hotel",
        "city": "Tokyo",
        "country": "Japan",
        "stars": 4,
        "price_per_night": 280,
        "max_guests_per_room": 3,
        "total_rooms": 120,
        "available_rooms": 25,
    },
    {
        "hotel_id": "manhattan-suites",
        "name": "Manhattan Suites",
        "city": "New York",
        "country": "USA",
        "stars": 4,
        "price_per_night": 420,
        "max_guests_per_room": 4,
        "total_rooms": 80,
        "available_rooms": 5,
    },
    {
        "hotel_id": "costa-del-sol-resort",
        "name": "Costa del Sol Resort",
        "city": "Malaga",
        "country": "Spain",
        "stars": 5,
        "price_per_night": 300,
        "max_guests_per_room": 6,
        "total_rooms": 200,
        "available_rooms": 45,
    },
    {
        "hotel_id": "berlin-central-hotel",
        "name": "Berlin Central Hotel",
        "city": "Berlin",
        "country": "Germany",
        "stars": 3,
        "price_per_night": 110,
        "max_guests_per_room": 3,
        "total_rooms": 60,
        "available_rooms": 18,
    },
    {
        "hotel_id": "sydney-harbour-inn",
        "name": "Sydney Harbour Inn",
        "city": "Sydney",
        "country": "Australia",
        "stars": 4,
        "price_per_night": 250,
        "max_guests_per_room": 3,
        "total_rooms": 40,
        "available_rooms": 10,
    },
    {
        "hotel_id": "roma-classic-hotel",
        "name": "Roma Classic Hotel",
        "city": "Rome",
        "country": "Italy",
        "stars": 3,
        "price_per_night": 130,
        "max_guests_per_room": 2,
        "total_rooms": 35,
        "available_rooms": 0,  # No availability - tests "sold out" scenario
    },
    {
        "hotel_id": "dubai-palace",
        "name": "Dubai Palace Hotel",
        "city": "Dubai",
        "country": "UAE",
        "stars": 5,
        "price_per_night": 600,
        "max_guests_per_room": 4,
        "total_rooms": 150,
        "available_rooms": 30,
    },
    {
        "hotel_id": "london-bridge-hotel",
        "name": "London Bridge Hotel",
        "city": "London",
        "country": "UK",
        "stars": 4,
        "price_per_night": 220,
        "max_guests_per_room": 3,
        "total_rooms": 70,
        "available_rooms": 15,
    },
    {
        "hotel_id": "eko-hotel-lagos",
        "name": "Eko Hotel Lagos",
        "city": "Lagos",
        "country": "Nigeria",
        "stars": 4,
        "price_per_night": 140,
        "max_guests_per_room": 3,
        "total_rooms": 90,
        "available_rooms": 22,
    },
    {
        "hotel_id": "jardins-inn-sao-paulo",
        "name": "Jardins Inn São Paulo",
        "city": "São Paulo",
        "country": "Brazil",
        "stars": 3,
        "price_per_night": 95,
        "max_guests_per_room": 2,
        "total_rooms": 45,
        "available_rooms": 14,
    },
    {
        "hotel_id": "grand-hyatt-jakarta",
        "name": "Grand Hyatt Jakarta",
        "city": "Jakarta",
        "country": "Indonesia",
        "stars": 5,
        "price_per_night": 180,
        "max_guests_per_room": 4,
        "total_rooms": 100,
        "available_rooms": 20,
    },
    {
        "hotel_id": "taj-gateway-mumbai",
        "name": "Taj Gateway Mumbai",
        "city": "Mumbai",
        "country": "India",
        "stars": 4,
        "price_per_night": 160,
        "max_guests_per_room": 3,
        "total_rooms": 75,
        "available_rooms": 18,
    },
    {
        "hotel_id": "safari-lodge-nairobi",
        "name": "Safari Lodge Nairobi",
        "city": "Nairobi",
        "country": "Kenya",
        "stars": 3,
        "price_per_night": 105,
        "max_guests_per_room": 2,
        "total_rooms": 30,
        "available_rooms": 9,
    },
    {
        "hotel_id": "hanoi-old-quarter-inn",
        "name": "Old Quarter Inn Hanoi",
        "city": "Hanoi",
        "country": "Vietnam",
        "stars": 2,
        "price_per_night": 35,
        "max_guests_per_room": 2,
        "total_rooms": 20,
        "available_rooms": 8,
    },
    {
        "hotel_id": "cairo-nile-hostel",
        "name": "Nile View Hostel Cairo",
        "city": "Cairo",
        "country": "Egypt",
        "stars": 1,
        "price_per_night": 25,
        "max_guests_per_room": 4,
        "total_rooms": 40,
        "available_rooms": 15,
    },
    {
        "hotel_id": "lima-backpackers-lodge",
        "name": "Backpackers Lodge Lima",
        "city": "Lima",
        "country": "Peru",
        "stars": 2,
        "price_per_night": 30,
        "max_guests_per_room": 3,
        "total_rooms": 25,
        "available_rooms": 12,
    },
]


STEERING_RULES = [
    {
        "rule_id": "max-guests",
        "action": "book",
        "condition_field": "guests",
        "operator": "gt",
        "threshold": 10,
        "fail_message": "Guest count exceeds maximum of 10",
        "steer_message": "Booking for {guests} guests is not available, but you CAN book for up to 10 guests. Adjust to 10 guests, proceed with the booking, and tell the user: 'I adjusted your reservation to 10 guests (our maximum). Would you like to proceed or make separate bookings for the remaining guests?'",
        "enabled": True,
    },
    {
        "rule_id": "valid-dates",
        "action": "book",
        "condition_field": "nights",
        "operator": "lt",
        "threshold": 1,
        "fail_message": "Check-in date must be before check-out date",
        "steer_message": "The dates appear reversed. Swap check-in and check-out, proceed with the booking, and tell the user: 'I noticed the dates were swapped, so I corrected them to check-in {check_out} and check-out {check_in}. Does that look right?'",
        "enabled": True,
    },
    {
        "rule_id": "advance-booking",
        "action": "book",
        "condition_field": "days_until_checkin",
        "operator": "lt",
        "threshold": 1,
        "fail_message": "Booking must be made at least 1 day in advance",
        "steer_message": "Same-day bookings are not available, but you CAN book starting tomorrow. Adjust the check-in to tomorrow's date, proceed with the booking, and tell the user: 'Same-day bookings are not available. I moved your check-in to tomorrow. Would you like to confirm?'",
        "enabled": True,
    },
    {
        "rule_id": "payment-before-confirm",
        "action": "confirm",
        "condition_field": "booking_status",
        "operator": "ne",
        "threshold": "PAID",
        "fail_message": "Payment must be processed before confirmation",
        "steer_message": "Confirmation requires payment first. Process the payment using process_payment with the booking total, then confirm. Tell the user: 'I need to process your payment of ${total} before confirming. Shall I proceed?'",
        "enabled": True,
    },
    {
        "rule_id": "cancellation-window",
        "action": "cancel",
        "condition_field": "days_until_checkin",
        "operator": "lt",
        "threshold": 2,
        "fail_message": "Cannot cancel within 48 hours of check-in",
        "steer_message": "Cancellation within 48 hours is not available, but you CAN modify your reservation. Tell the user: 'Cancellation is not possible within 48 hours of check-in. However, I can help you modify the dates or contact support for special exceptions. What would you prefer?'",
        "enabled": True,
    },
    {
        "rule_id": "already-cancelled",
        "action": "cancel",
        "condition_field": "booking_status",
        "operator": "eq",
        "threshold": "CANCELLED",
        "fail_message": "Booking is already cancelled",
        "steer_message": "This booking is already cancelled, but you CAN make a new reservation. Tell the user: 'This booking was already cancelled. Would you like me to search for available hotels to make a new reservation?'",
        "enabled": True,
    },
]


def seed_hotels():
    dynamodb = get_dynamodb_resource()
    table = dynamodb.Table(HOTELS_TABLE)

    for hotel in HOTELS:
        table.put_item(Item=hotel)
        print(f"  {hotel['name']} ({hotel['city']}) - ${hotel['price_per_night']}/night")

    print(f"\n{len(HOTELS)} hotels seeded in {HOTELS_TABLE}")


def seed_steering_rules():
    dynamodb = get_dynamodb_resource()
    table = dynamodb.Table(STEERING_RULES_TABLE)

    for rule in STEERING_RULES:
        table.put_item(Item=rule)
        print(f"  [{rule['action']}] {rule['rule_id']}: {rule['fail_message']}")

    print(f"\n{len(STEERING_RULES)} steering rules seeded in {STEERING_RULES_TABLE}")


if __name__ == "__main__":
    seed_hotels()
    print()
    seed_steering_rules()
