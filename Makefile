.PHONY: dev stop test test-backend test-frontend install

# Start both servers. Ctrl+C stops everything cleanly.
dev:
	@echo "Starting backend on :5000 and frontend on :5173..."
	@trap 'kill 0' INT; \
	  cd backend && python app.py & \
	  cd frontend && npm run dev & \
	  wait

# Kill anything still holding the ports
stop:
	@echo "Stopping servers..."
	@lsof -ti:5000 | xargs kill -9 2>/dev/null || true
	@lsof -ti:5173 | xargs kill -9 2>/dev/null || true
	@echo "Done."

# Install all dependencies (run once after cloning)
install:
	@echo "Installing Python dependencies..."
	cd backend && pip install -r requirements.txt
	@echo "Installing Node dependencies..."
	cd frontend && npm install
	@echo "All dependencies installed."

# Run all tests
test: test-backend test-frontend

test-backend:
	@echo "Running backend tests..."
	cd backend && python -m pytest tests/ -v

test-frontend:
	@echo "Running frontend tests..."
	cd frontend && npm test
