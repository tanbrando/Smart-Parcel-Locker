"""
Main Entry Point for Raspberry Pi 4B Edge Controller.
Runs the Smart Parcel Locker loop and manages system events.
"""
import sys
import time
import signal
import logging

from edge.config import MOCK_HARDWARE, SERVER_API_URL
from edge.core.fsm import LockerStateMachine
from edge.core.api_client import EdgeApiClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] (%(name)s) %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("edge.main")


def setup_signal_handlers(fsm: LockerStateMachine):
    def handle_exit(sig, frame):
        logger.info("\nReceived exit signal (%s). Cleaning up hardware...", sig)
        try:
            fsm.indicators.clear()
            if not MOCK_HARDWARE:
                import RPi.GPIO as GPIO
                GPIO.cleanup()
        except Exception as exc:
            logger.warning("Error during GPIO cleanup: %s", exc)
        logger.info("Edge system shutdown complete.")
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)


def main():
    logger.info("==========================================")
    logger.info("🚀 Starting Smart Parcel Locker Edge Node")
    logger.info("Mode: %s", "MOCK (Emulation)" if MOCK_HARDWARE else "PHYSICAL (Raspberry Pi 4B)")
    logger.info("Target Server: %s", SERVER_API_URL)
    logger.info("==========================================")

    fsm = LockerStateMachine()
    setup_signal_handlers(fsm)

    # Check connection to backend
    if fsm.api_client.check_health():
        logger.info(" Connected to Backend Server successfully.")
    else:
        logger.warning("⚠️ Backend server is currently offline or unreachable. Offline/mock flow active.")

    fsm.reset_to_idle()

    logger.info("\n--- Demonstration / Interactive Edge Menu ---")
    logger.info("1: Trigger Courier Deposit Workflow (Scan -> Verify -> Unlock -> Weigh -> Confirm)")
    logger.info("2: Trigger Recipient Pickup Workflow (Keypad OTP -> Verify -> Unlock)")
    logger.info("3: Health check server")
    logger.info("q: Exit\n")

    if MOCK_HARDWARE:
        logger.info("Running in interactive emulation mode. Enter option [1/2/3/q]:")
        while True:
            try:
                choice = input("Edge Command > ").strip().lower()
                if choice == "1":
                    fsm.handle_courier_deposit()
                elif choice == "2":
                    otp = input("Enter 6-digit OTP (press Enter for default mock '582194'): ").strip()
                    fsm.handle_recipient_pickup(otp_input=otp if otp else None)
                elif choice == "3":
                    alive = fsm.api_client.check_health()
                    print(f"Server health: {'ONLINE' if alive else 'OFFLINE'}")
                elif choice in ("q", "quit", "exit"):
                    break
                else:
                    print("Unknown command. Enter 1, 2, 3, or q.")
                fsm.reset_to_idle()
            except (KeyboardInterrupt, EOFError):
                break
    else:
        # On physical Pi, run main event loop
        logger.info("Listening for physical button / keypad events...")
        while True:
            time.sleep(0.5)


if __name__ == "__main__":
    main()
