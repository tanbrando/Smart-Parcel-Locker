# Web Dashboard [Person 4]

A lightweight, responsive web interface for:
- Users to upload e-commerce screenshots (Shopee/Lazada) to register incoming parcels.
- Admins/Recipients to monitor physical locker compartment availability and weight measurements.
- Real-time order status tracking (PENDING, DEPOSITED, RETRIEVED).

## Running Locally
Simply open `index.html` in any web browser, or serve via Python:
```bash
cd web
python -m http.server 3000
```
Open `http://localhost:3000` in your browser.
Ensure the FastAPI server is running on `http://localhost:8000`.

