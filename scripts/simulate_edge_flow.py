"""
Standalone End-to-End Edge Flow Simulator [Person 4 Tool for Persons 1, 2, 3].
Simulates Raspberry Pi calls to FastAPI Cloud Backend:
1. Screenshot Order Registration
2. Shipper Barcode Verification (CV)
3. Parcel Placement & Load Cell Weighing (HX711)
4. OTP Rate-Limiting & Recipient Collection (Keypad)
"""
import sys
import io
import time
import requests

SERVER_URL = "http://localhost:8000"


def run_simulation():
    print("=" * 60)
    print("🚀 STARTING SMART PARCEL LOCKER END-TO-END SIMULATION")
    print("=" * 60)

    # 0. Health check
    try:
        r = requests.get(f"{SERVER_URL}/health", timeout=3.0)
        if r.status_code != 200:
            print("❌ Server is offline! Please start FastAPI server first.")
            return
    except Exception as e:
        print(f"❌ Cannot connect to {SERVER_URL}: {e}")
        return

    print("✅ Server online and reachable.\n")

    # Step 1: User uploads screenshot with telegram_chat_id
    print("1️⃣ [User Web / App] Uploading Shopee Screenshot...")
    dummy_image = io.BytesIO(b"fake-shopee-screenshot-binary-content-12345")
    files = {"image": ("SPXVN048291048_screenshot.png", dummy_image, "image/png")}
    data = {
        "telegram_chat_id": 123456789,
        "expected_weight": 520,
    }
    reg_res = requests.post(f"{SERVER_URL}/api/v1/orders/register-screenshot", files=files, data=data)
    print(f"   Response Status: {reg_res.status_code}")
    reg_json = reg_res.json()
    print(f"   Payload: {reg_json}")
    assert reg_res.status_code == 201, "Failed to register screenshot"
    order_data = reg_json["data"]
    order_id = order_data["order_id"]
    tracking_number = order_data["tracking_number"]
    print(f"   Order #{order_id} Registered! Tracking: {tracking_number}\n")

    # Step 2: Shipper arrives at Pi -> Camera Scans Barcode
    print("2️⃣ [Raspberry Pi CV] Shipper arrives, camera reads waybill...")
    verify_payload = {
        "tracking_number": tracking_number,
        "ocr_weight": 520,
        "recipient_phone_last4": "3456",
    }
    v_res = requests.post(f"{SERVER_URL}/api/v1/pi/verify-package", json=verify_payload)
    print(f"   Response Status: {v_res.status_code}")
    v_json = v_res.json()
    print(f"   Payload: {v_json}")
    assert v_json["action"] == "UNLOCK_DOOR", "Failed to unlock door"
    locker_num = v_json["locker_number"]
    print(f"   Door Solenoid #{locker_num} Unlocked! Customer: {v_json['customer_name']}\n")

    # Step 3: Shipper places parcel -> HX711 Load Cell measures weight delta
    print(f"3️⃣ [Raspberry Pi Hardware] Parcel placed in Locker #{locker_num}. Measuring HX711...")
    deposit_payload = {
        "order_id": order_id,
        "locker_number": locker_num,
        "delta_weight": 495,  # 495g vs expected 520g (deviation = 25g, within 150g tolerance)
        "image_base64": None,
    }
    dep_res = requests.post(f"{SERVER_URL}/api/v1/pi/confirm-deposit", json=deposit_payload)
    print(f"   Response Status: {dep_res.status_code}")
    dep_json = dep_res.json()
    print(f"   Payload: {dep_json}")
    assert dep_json["success"] is True, "Deposit confirmation failed"
    otp_code = dep_json["otp_generated"]
    print(f"   Deposit Confirmed! Weight Matched: {dep_json['weight_matched']}. OTP dispatched: {otp_code}\n")

    # Step 4: Recipient arrives -> Inputs WRONG OTP (testing rate-limiter)
    print("4️⃣ [Raspberry Pi Keypad] Recipient arrives and inputs WRONG OTP...")
    wrong_res = requests.post(f"{SERVER_URL}/api/v1/pi/verify-otp", json={"otp_code": "000000"})
    print(f"   Response Status: {wrong_res.status_code} (Expected 401)")
    wrong_json = wrong_res.json()
    print(f"   Payload: {wrong_json}")
    assert wrong_res.status_code == 401
    assert wrong_json["valid"] is False
    print(f"   Rate Limiter recorded failure. Remaining attempts: {wrong_json['remaining_attempts']}\n")

    # Step 5: Recipient inputs CORRECT OTP
    print(f"5️⃣ [Raspberry Pi Keypad] Recipient enters CORRECT OTP: {otp_code}...")
    correct_res = requests.post(f"{SERVER_URL}/api/v1/pi/verify-otp", json={"otp_code": otp_code})
    print(f"   Response Status: {correct_res.status_code}")
    correct_json = correct_res.json()
    print(f"   Payload: {correct_json}")
    assert correct_res.status_code == 200
    assert correct_json["valid"] is True
    assert correct_json["locker_number"] == locker_num
    print(f"   Access Granted! Opening Locker #{locker_num}. Parcel collected!\n")

    print("=" * 60)
    print("🎉 FULL END-TO-END FLOW COMPLETED SUCCESSFULLY!")
    print("=" * 60)


if __name__ == "__main__":
    run_simulation()

